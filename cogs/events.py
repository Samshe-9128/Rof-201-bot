# cogs/events.py
import uuid
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from core.config import (
    DEFAULT_TZ_OFFSET,
    EVENT_CHANNEL_ID,
    ROFColors,
    format_dual_timestamps,
    get_game_tz,
)
from core.database import db
from core.permissions import ensure_admin, is_admin_interaction
from core.ui import PaginatedEmbedView, rof_embed


def parse_event_datetime(date_str: str, time_str: str, tz_offset: float = None) -> datetime:
    """Parse YYYY-MM-DD and HH:MM in Game Time (default UTC-2) and return timezone-aware datetime."""
    game_tz = get_game_tz(tz_offset)
    clean_date = date_str.strip()
    clean_time = time_str.strip()
    dt = datetime.strptime(f"{clean_date} {clean_time}", "%Y-%m-%d %H:%M")
    return dt.replace(tzinfo=game_tz)


def build_event_detail_embed(ev: dict, title_prefix: str = "📅 ROF EVENT DETAILS") -> discord.Embed:
    tz_off = float(db.get_config("game_tz_offset", str(DEFAULT_TZ_OFFSET)))
    start_dt = datetime.fromisoformat(ev["start_time_utc"])
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    dual = format_dual_timestamps(start_dt, tz_off)
    rem_mins = ev.get("reminder_minutes", 10)
    dur_mins = ev.get("duration_minutes", 60)
    status = ev.get("status", "scheduled").upper()

    desc = (
        f"**Event:** {ev['name']}\n"
        f"**Event ID:** `{ev['id']}`\n"
        f"**Date:** {dual['short_date']} ({dual['date_str']})\n"
        f"**Game Time:** `{dual['game_time']}`\n"
        f"**India Time:** `{dual['india_time']}`\n"
        f"**Your Local Time:** {dual['discord_full']} ({dual['discord_relative']})\n"
        f"**Duration:** `{dur_mins} mins` | **Status:** `{status}`\n"
        f"**Reminder:** `{rem_mins} minutes before`"
    )
    if ev.get("description"):
        desc += f"\n\n**Description:**\n{ev['description']}"

    color = ROFColors.SUCCESS if status == "SCHEDULED" else ROFColors.ERROR
    return rof_embed(title=title_prefix, description=desc, color=color, footer_extra=f"Event ID: {ev['id']}")


# ---------- MODALS & VIEWS ----------

class EventCreateOrEditModal(discord.ui.Modal):
    event_name = discord.ui.TextInput(
        label="Event Name",
        placeholder="e.g., Surge / Alliance Brawl",
        max_length=60,
        required=True,
    )
    event_date = discord.ui.TextInput(
        label="Date (YYYY-MM-DD)",
        placeholder="e.g., 2026-11-12",
        min_length=10,
        max_length=10,
        required=True,
    )
    event_time = discord.ui.TextInput(
        label="Game Time (HH:MM in UTC-2)",
        placeholder="e.g., 16:00",
        min_length=5,
        max_length=5,
        required=True,
    )
    description = discord.ui.TextInput(
        label="Event Description (Optional)",
        style=discord.TextStyle.paragraph,
        placeholder="Rally instructions, requirements, or special notes...",
        max_length=500,
        required=False,
    )
    duration_minutes = discord.ui.TextInput(
        label="Duration in Minutes (Optional, default 60)",
        placeholder="60",
        max_length=4,
        required=False,
    )

    def __init__(
        self,
        cog: "Events",
        channel_id: Optional[int] = None,
        existing_event: Optional[dict] = None,
    ):
        title = f"Edit Event ({existing_event['id']})" if existing_event else "Create ROF Alliance Event"
        super().__init__(title=title)
        self.cog = cog
        self.channel_id = channel_id
        self.existing_event = existing_event

        if existing_event:
            tz_off = float(db.get_config("game_tz_offset", str(DEFAULT_TZ_OFFSET)))
            dt = datetime.fromisoformat(existing_event["start_time_utc"]).astimezone(get_game_tz(tz_off))
            self.event_name.default = existing_event["name"]
            self.event_date.default = dt.strftime("%Y-%m-%d")
            self.event_time.default = dt.strftime("%H:%M")
            self.description.default = existing_event.get("description", "")
            self.duration_minutes.default = str(existing_event.get("duration_minutes", 60))

    async def on_submit(self, interaction: discord.Interaction):
        if not await ensure_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        tz_off = float(db.get_config("game_tz_offset", str(DEFAULT_TZ_OFFSET)))
        try:
            event_dt = parse_event_datetime(self.event_date.value, self.event_time.value, tz_off)
        except ValueError:
            return await interaction.followup.send(
                "❌ **Invalid Date or Time Format!** Use `YYYY-MM-DD` (e.g., `2026-11-12`) and 24-hour `HH:MM` (e.g., `16:00`).",
                ephemeral=True,
            )

        if event_dt <= datetime.now(timezone.utc):
            return await interaction.followup.send(
                "❌ **Past Time Rejected!** Please schedule the event for a future time.",
                ephemeral=True,
            )

        dur_raw = (self.duration_minutes.value or "60").strip()
        if not dur_raw.isdigit() or int(dur_raw) <= 0 or int(dur_raw) > 1440:
            return await interaction.followup.send(
                "❌ **Invalid Duration!** Duration must be between `1` and `1440` minutes.",
                ephemeral=True,
            )
        dur_val = int(dur_raw)

        default_chan = int(db.get_config("event_channel_id", str(EVENT_CHANNEL_ID or 0)) or 0)
        target_chan_id = self.channel_id or (
            self.existing_event["channel_id"] if self.existing_event else default_chan
        ) or (interaction.channel.id if interaction.channel else 0)

        rem_default = int(db.get_config("default_reminder_minutes", "10") or 10)

        if self.existing_event:
            updated = db.update_event(
                event_id=self.existing_event["id"],
                name=self.event_name.value,
                description=self.description.value or "",
                start_time_utc=event_dt,
                duration_minutes=dur_val,
                channel_id=target_chan_id,
            )
            db.log_audit(interaction.user.id, "event_edit", f"Edited event {updated['id']} ({updated['name']})")
            embed = build_event_detail_embed(updated, title_prefix="✅ EVENT UPDATED")
            view = EventConfirmationView(self.cog, updated["id"])
            return await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        event_id = str(uuid.uuid4())[:6]
        created = db.create_event(
            event_id=event_id,
            name=self.event_name.value,
            description=self.description.value or "",
            start_time_utc=event_dt,
            duration_minutes=dur_val,
            channel_id=target_chan_id,
            creator_id=interaction.user.id,
            reminder_minutes=rem_default,
        )
        db.log_audit(interaction.user.id, "event_create", f"Created event {event_id} ({created['name']})")

        # Send announcement to configured channel if reachable
        target_channel = self.cog.bot.get_channel(target_chan_id)
        if target_channel:
            try:
                dual = format_dual_timestamps(event_dt, tz_off)
                ann_embed = rof_embed(
                    title=f"📢 ROF EVENT SCHEDULED — {created['name'].upper()}",
                    description=(
                        f"{created['description']}\n\n" if created.get("description") else ""
                    )
                    + (
                        f"📅 **Date:** {dual['short_date']}\n"
                        f"🕒 **Game Time:** `{dual['game_time']}`\n"
                        f"🇮🇳 **India Time:** `{dual['india_time']}`\n"
                        f"🌍 **Your Time:** {dual['discord_full']} ({dual['discord_relative']})\n"
                        f"🔔 **Reminder:** {rem_default} minutes before start"
                    ),
                    color=ROFColors.GOLD,
                    footer_extra=f"Event ID: {event_id}",
                )
                await target_channel.send(embed=ann_embed)
            except Exception as e:
                print(f"[EVENTS] Notice: could not post announcement to channel {target_chan_id}: {e}")

        # Build Part 6.1 Confirmation Screen
        dual = format_dual_timestamps(event_dt, tz_off)
        confirm_embed = rof_embed(
            title="✅ EVENT CREATED",
            description=(
                f"**Event:** {created['name']}\n"
                f"**Event ID:** `{created['id']}`\n"
                f"**Date:** {dual['short_date']}\n"
                f"**Game Time:** `{dual['game_time_short']}` (`UTC-02:00`)\n"
                f"**India Time:** `{dual['india_time_short']}` (`Asia/Kolkata`)\n"
                f"**Reminder:** {created['reminder_minutes']} minutes before."
            ),
            color=ROFColors.SUCCESS,
            footer_extra=f"Event ID: {created['id']}",
        )
        view = EventConfirmationView(self.cog, created["id"])
        await interaction.followup.send(embed=confirm_embed, view=view, ephemeral=True)


class EventConfirmationView(discord.ui.View):
    """Part 6.1 Confirmation buttons: [Edit Event] [View Event]."""

    def __init__(self, cog: "Events", event_id: str):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.event_id = event_id

    @discord.ui.button(label="Edit Event", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_admin(interaction):
            return
        ev = db.get_event(self.event_id)
        if not ev:
            return await interaction.response.send_message("❌ Event no longer exists.", ephemeral=True)
        await interaction.response.send_modal(EventCreateOrEditModal(self.cog, existing_event=ev))

    @discord.ui.button(label="View Event", style=discord.ButtonStyle.secondary, emoji="👁️")
    async def view_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ev = db.get_event(self.event_id)
        if not ev:
            return await interaction.response.send_message("❌ Event not found.", ephemeral=True)
        await interaction.response.send_message(embed=build_event_detail_embed(ev), ephemeral=True)


class EventSetupView(discord.ui.View):
    def __init__(self, cog: "Events"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Create Event", style=discord.ButtonStyle.success, emoji="➕")
    async def create_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_admin(interaction):
            return
        await interaction.response.send_modal(EventCreateOrEditModal(self.cog))


# ---------- COG ----------

class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminder_task.start()

    def cog_unload(self):
        self.reminder_task.cancel()

    @tasks.loop(seconds=20)
    async def reminder_task(self):
        await self.process_due_reminders()

    async def process_due_reminders(self) -> int:
        """Check and send all due event reminders, persisting status to prevent duplicates."""
        due_events = db.get_due_reminders()
        sent_count = 0
        tz_off = float(db.get_config("game_tz_offset", str(DEFAULT_TZ_OFFSET)))

        for ev in due_events:
            # Mark as sent first or immediately upon processing to prevent duplicate notifications
            db.mark_reminder_sent(ev["id"])
            chan_id = int(ev.get("channel_id") or db.get_config("event_channel_id", str(EVENT_CHANNEL_ID or 0)) or 0)
            if not chan_id:
                continue

            channel = self.bot.get_channel(chan_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(chan_id)
                except Exception:
                    channel = None

            if not channel:
                continue

            try:
                start_dt = datetime.fromisoformat(ev["start_time_utc"])
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                dual = format_dual_timestamps(start_dt, tz_off)
                rem_mins = ev.get("reminder_minutes", 10)

                embed = rof_embed(
                    title=f"🔔 ROF EVENT REMINDER — {ev['name'].upper()}",
                    description=(
                        f"⚔️ **{ev['name']}** starts in **{rem_mins} minutes**!\n"
                        + (f"\n{ev['description']}\n\n" if ev.get("description") else "\n")
                        + f"🕒 **Game Time:** `{dual['game_time']}`\n"
                        f"🇮🇳 **India Time:** `{dual['india_time']}`\n"
                        f"🌍 **Discord Timestamp:** {dual['discord_full']} ({dual['discord_relative']})"
                    ),
                    color=ROFColors.WARNING,
                    footer_extra=f"Event ID: {ev['id']}",
                )
                await channel.send(
                    content="@everyone 🔔 **ROF Alliance Event Reminder!**",
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(everyone=True),
                )
                sent_count += 1
            except Exception as e:
                print(f"[EVENTS] Reminder send error for {ev['id']}: {e}")

        return sent_count

    @reminder_task.before_loop
    async def before_reminder(self):
        await self.bot.wait_until_ready()

    # ---------- COMMANDS ----------

    @app_commands.command(name="events", description="View upcoming ROF alliance events in Game Time & India Time")
    async def list_events(self, interaction: discord.Interaction):
        upcoming = db.get_upcoming_events(include_cancelled=False)
        if not upcoming:
            embed = rof_embed(
                title="📅 ROF UPCOMING EVENTS",
                description="No upcoming events are currently scheduled. ⚔️",
                color=ROFColors.INFO,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        tz_off = float(db.get_config("game_tz_offset", str(DEFAULT_TZ_OFFSET)))
        per_page = 4
        pages: List[discord.Embed] = []

        for idx in range(0, len(upcoming), per_page):
            chunk = upcoming[idx : idx + per_page]
            embed = rof_embed(
                title="⚔️ ROF UPCOMING ALLIANCE EVENTS",
                description="All times shown in **Game Time (`UTC-2`)**, **India Time (`IST`)**, and your local time:",
                color=ROFColors.ARENA,
            )
            for ev in chunk:
                dt = datetime.fromisoformat(ev["start_time_utc"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dual = format_dual_timestamps(dt, tz_off)
                desc_line = f"📝 *{ev['description']}*\n" if ev.get("description") else ""
                val = (
                    f"{desc_line}"
                    f"📅 **Date:** {dual['short_date']} | **Status:** `{ev['status'].upper()}`\n"
                    f"🕒 **Game Time:** `{dual['game_time']}`\n"
                    f"🇮🇳 **India Time:** `{dual['india_time']}`\n"
                    f"⏳ **Countdown:** {dual['discord_relative']} ({dual['discord_short']})"
                )
                embed.add_field(
                    name=f"⚔️ {ev['name']} (ID: `{ev['id']}`)",
                    value=val,
                    inline=False,
                )
            pages.append(embed)

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0], ephemeral=True)
        else:
            view = PaginatedEmbedView(interaction.user.id, pages)
            await interaction.response.send_message(embed=pages[0], view=view, ephemeral=True)

    # Structured /event command group (Part 6 & Part 11: create, edit, cancel, delete, view)
    event_group = app_commands.Group(name="event", description="ROF Alliance Event Management & Viewing")

    @event_group.command(name="create", description="Create a new ROF alliance event (Admin/Owner only)")
    @app_commands.describe(channel="Optional announcement channel (defaults to configured Event Channel)")
    async def event_create_cmd(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ):
        if not await ensure_admin(interaction):
            return
        chan_id = channel.id if channel else None
        await interaction.response.send_modal(EventCreateOrEditModal(self, channel_id=chan_id))

    @event_group.command(name="edit", description="Edit an existing alliance event (Admin/Owner only)")
    @app_commands.describe(event_id="The 6-character ID of the event to edit")
    async def event_edit_cmd(self, interaction: discord.Interaction, event_id: str):
        if not await ensure_admin(interaction):
            return
        ev = db.get_event(event_id)
        if not ev:
            return await interaction.response.send_message(
                f"❌ Event ID `{event_id}` not found.", ephemeral=True
            )
        await interaction.response.send_modal(EventCreateOrEditModal(self, existing_event=ev))

    @event_group.command(name="cancel", description="Cancel a scheduled alliance event (Admin/Owner only)")
    @app_commands.describe(event_id="The 6-character ID of the event to cancel")
    async def event_cancel_cmd(self, interaction: discord.Interaction, event_id: str):
        if not await ensure_admin(interaction):
            return
        ev = db.cancel_or_delete_event(event_id, delete_permanently=False)
        if not ev:
            return await interaction.response.send_message(
                f"❌ Event ID `{event_id}` not found.", ephemeral=True
            )
        db.log_audit(interaction.user.id, "event_cancel", f"Cancelled event {event_id} ({ev['name']})")
        embed = rof_embed(
            title="🚫 EVENT CANCELLED",
            description=f"Event **{ev['name']}** (`{ev['id']}`) has been cancelled and its pending reminder has been cleared.",
            color=ROFColors.WARNING,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @event_group.command(name="delete", description="Permanently delete an alliance event (Admin/Owner only)")
    @app_commands.describe(event_id="The 6-character ID of the event to delete")
    async def event_delete_cmd(self, interaction: discord.Interaction, event_id: str):
        if not await ensure_admin(interaction):
            return
        ev = db.cancel_or_delete_event(event_id, delete_permanently=True)
        if not ev:
            return await interaction.response.send_message(
                f"❌ Event ID `{event_id}` not found.", ephemeral=True
            )
        db.log_audit(interaction.user.id, "event_delete", f"Deleted event {event_id} ({ev['name']})")
        await interaction.response.send_message(
            f"🗑️ Event **{ev['name']}** (`{ev['id']}`) has been permanently deleted.", ephemeral=True
        )

    @event_group.command(name="view", description="View full details and timezone conversions for an event")
    @app_commands.describe(event_id="The 6-character ID of the event")
    async def event_view_cmd(self, interaction: discord.Interaction, event_id: str):
        ev = db.get_event(event_id)
        if not ev:
            return await interaction.response.send_message(
                f"❌ Event ID `{event_id}` not found. Use `/events` to see all upcoming event IDs.",
                ephemeral=True,
            )
        await interaction.response.send_message(embed=build_event_detail_embed(ev), ephemeral=True)

    # Preserved legacy /event_cancel command
    @app_commands.command(name="event_cancel", description="Cancel an event by ID (Admin/Owner)")
    @app_commands.describe(event_id="The short ID of the event (e.g. a1b2c3)")
    async def cancel_event_legacy(self, interaction: discord.Interaction, event_id: str):
        await self.event_cancel_cmd.callback(self, interaction, event_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))