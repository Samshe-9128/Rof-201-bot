# cogs/events.py
import uuid
import traceback
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


# ==============================================================================
# HELPERS
# ==============================================================================

def _parse_iso_utc(raw_value) -> Optional[datetime]:
    """
    fix J: normalize trailing `Z` (which fails on Python ≤ 3.10) and
    assume UTC for naive datetimes. Returns None on malformed input.
    """
    if not raw_value:
        return None
    s = str(raw_value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception as e:
        print(f"[EVENTS] invalid ISO datetime '{raw_value}': {e}")
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _safe_tz_off() -> float:
    # fix D + others: single fallback helper for the tz offset.
    try:
        return float(db.get_config("game_tz_offset", str(DEFAULT_TZ_OFFSET)))
    except Exception as e:
        print(f"[EVENTS] tz config read failed: {e}")
        return float(DEFAULT_TZ_OFFSET)


def parse_event_datetime(
    date_str: str,
    time_str: str,
    tz_offset: Optional[float] = None,
) -> datetime:
    """Parse YYYY-MM-DD and HH:MM in Game Time (default UTC-2) and return timezone-aware datetime."""
    game_tz = get_game_tz(tz_offset)
    clean_date = date_str.strip()
    clean_time = time_str.strip()
    dt = datetime.strptime(f"{clean_date} {clean_time}", "%Y-%m-%d %H:%M")
    return dt.replace(tzinfo=game_tz)


def build_event_detail_embed(ev: dict, title_prefix: str = "📅 ROF EVENT DETAILS") -> discord.Embed:
    # fix D: entire render is guarded.
    try:
        tz_off = _safe_tz_off()
        start_dt = _parse_iso_utc(ev.get("start_time_utc"))
        if start_dt is None:
            raise ValueError("missing or invalid start_time_utc")

        try:
            dual = format_dual_timestamps(start_dt, tz_off)
        except Exception as e:
            print(f"[EVENTS] format_dual_timestamps failed: {e}")
            # Degrade gracefully — show the raw UTC time.
            raw = ev.get("start_time_utc", "?")
            dual = {
                "short_date": "?",
                "date_str": raw,
                "game_time": "?",
                "india_time": "?",
                "discord_full": raw,
                "discord_relative": "?",
            }

        rem_mins = ev.get("reminder_minutes", 10)
        dur_mins = ev.get("duration_minutes", 60)
        status = str(ev.get("status", "scheduled")).upper()

        desc = (
            f"**Event:** {ev.get('name', '?')}\n"
            f"**Event ID:** `{ev.get('id', '?')}`\n"
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
        return rof_embed(
            title=title_prefix,
            description=desc,
            color=color,
            footer_extra=f"Event ID: {ev.get('id', '?')}",
        )
    except Exception as e:
        print(f"[EVENTS] build_event_detail_embed failed: {type(e).__name__}: {e}")
        return rof_embed(
            title=title_prefix,
            description="⚠️ This event has malformed data and cannot be displayed correctly.",
            color=ROFColors.ERROR,
            footer_extra=f"Event ID: {ev.get('id', '?') if isinstance(ev, dict) else '?'}",
        )


# ==============================================================================
# MODALS & VIEWS
# ==============================================================================

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
        title = (
            f"Edit Event ({existing_event.get('id', '?')})"
            if existing_event
            else "Create ROF Alliance Event"
        )
        super().__init__(title=title)
        self.cog = cog
        self.channel_id = channel_id
        self.existing_event = existing_event

        # fix E: guard the prefill path.
        if existing_event:
            try:
                tz_off = _safe_tz_off()
                start_dt = _parse_iso_utc(existing_event.get("start_time_utc"))
                if start_dt is None:
                    start_dt = datetime.now(timezone.utc)
                try:
                    local_dt = start_dt.astimezone(get_game_tz(tz_off))
                except Exception as e:
                    print(f"[EVENTS] modal prefill astimezone failed: {e}")
                    local_dt = start_dt
                self.event_name.default = existing_event.get("name", "")
                self.event_date.default = local_dt.strftime("%Y-%m-%d")
                self.event_time.default = local_dt.strftime("%H:%M")
                self.description.default = existing_event.get("description", "")
                self.duration_minutes.default = str(
                    existing_event.get("duration_minutes", 60)
                )
            except Exception as e:
                print(f"[EVENTS] modal prefill failed: {type(e).__name__}: {e}")
                # Leave the fields blank so the admin can retype.

    async def on_submit(self, interaction: discord.Interaction):
        if not await ensure_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True)

        # fix B: top-level try/except so the user always gets a followup.
        try:
            await self._handle_submit(interaction)
        except Exception as e:
            print(f"[EVENTS] modal on_submit failed: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                await interaction.followup.send(
                    "⚠️ Could not save the event. Please try again.",
                    ephemeral=True,
                )
            except Exception:
                pass

    async def _handle_submit(self, interaction: discord.Interaction):
        tz_off = _safe_tz_off()

        try:
            event_dt = parse_event_datetime(self.event_date.value, self.event_time.value, tz_off)
        except ValueError:
            return await interaction.followup.send(
                "❌ **Invalid Date or Time Format!** Use `YYYY-MM-DD` (e.g., `2026-11-12`) "
                "and 24-hour `HH:MM` (e.g., `16:00`).",
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

        try:
            default_chan = int(
                db.get_config("event_channel_id", str(EVENT_CHANNEL_ID or 0)) or 0
            )
        except Exception as e:
            print(f"[EVENTS] event_channel_id read failed: {e}")
            default_chan = int(EVENT_CHANNEL_ID or 0)

        target_chan_id = (
            self.channel_id
            or (self.existing_event["channel_id"] if self.existing_event else default_chan)
            or (interaction.channel.id if interaction.channel else 0)
        )

        try:
            rem_default = int(db.get_config("default_reminder_minutes", "10") or 10)
        except Exception as e:
            print(f"[EVENTS] default_reminder_minutes read failed: {e}")
            rem_default = 10

        # ---------------- EDIT PATH ----------------
        if self.existing_event:
            try:
                updated = db.update_event(
                    event_id=self.existing_event["id"],
                    name=self.event_name.value,
                    description=self.description.value or "",
                    start_time_utc=event_dt,
                    duration_minutes=dur_val,
                    channel_id=target_chan_id,
                )
            except Exception as e:
                print(f"[EVENTS] update_event failed: {type(e).__name__}: {e}")
                return await interaction.followup.send(
                    "⚠️ Could not update the event in the database. Please try again.",
                    ephemeral=True,
                )

            # fix C: audit log is fire-and-forget.
            try:
                db.log_audit(
                    interaction.user.id,
                    "event_edit",
                    f"Edited event {updated['id']} ({updated['name']})",
                )
            except Exception as e:
                print(f"[EVENTS] log_audit failed (edit): {e}")

            embed = build_event_detail_embed(updated, title_prefix="✅ EVENT UPDATED")
            view = EventConfirmationView(self.cog, updated["id"])
            return await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        # ---------------- CREATE PATH ----------------
        event_id = str(uuid.uuid4())[:6]
        try:
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
        except Exception as e:
            print(f"[EVENTS] create_event failed: {type(e).__name__}: {e}")
            return await interaction.followup.send(
                "⚠️ Could not save the event to the database. Please try again.",
                ephemeral=True,
            )

        # fix C: audit log is fire-and-forget.
        try:
            db.log_audit(
                interaction.user.id,
                "event_create",
                f"Created event {event_id} ({created['name']})",
            )
        except Exception as e:
            print(f"[EVENTS] log_audit failed (create): {e}")

        # Announcement (best-effort)
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
                print(
                    f"[EVENTS] Notice: could not post announcement to channel "
                    f"{target_chan_id}: {e}"
                )

        # Confirmation screen
        try:
            dual = format_dual_timestamps(event_dt, tz_off)
        except Exception as e:
            print(f"[EVENTS] confirmation format_dual_timestamps failed: {e}")
            dual = {
                "short_date": event_dt.strftime("%Y-%m-%d"),
                "game_time_short": event_dt.strftime("%H:%M"),
                "india_time_short": "?",
            }

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
        # fix G: guard DB read.
        try:
            ev = db.get_event(self.event_id)
        except Exception as e:
            print(f"[EVENTS] get_event failed (edit btn): {e}")
            return await interaction.response.send_message(
                "⚠️ Could not load the event right now.", ephemeral=True
            )
        if not ev:
            return await interaction.response.send_message(
                "❌ Event no longer exists.", ephemeral=True
            )
        try:
            await interaction.response.send_modal(
                EventCreateOrEditModal(self.cog, existing_event=ev)
            )
        except Exception as e:
            print(f"[EVENTS] send_modal failed (edit btn): {e}")

    @discord.ui.button(label="View Event", style=discord.ButtonStyle.secondary, emoji="👁️")
    async def view_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            ev = db.get_event(self.event_id)
        except Exception as e:
            print(f"[EVENTS] get_event failed (view btn): {e}")
            return await interaction.response.send_message(
                "⚠️ Could not load the event right now.", ephemeral=True
            )
        if not ev:
            return await interaction.response.send_message(
                "❌ Event not found.", ephemeral=True
            )
        await interaction.response.send_message(
            embed=build_event_detail_embed(ev), ephemeral=True
        )

    async def on_timeout(self):
        for child in self.children:
            try:
                child.disabled = True
            except Exception:
                pass


class EventSetupView(discord.ui.View):
    def __init__(self, cog: "Events"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Create Event", style=discord.ButtonStyle.success, emoji="➕")
    async def create_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_admin(interaction):
            return
        try:
            await interaction.response.send_modal(EventCreateOrEditModal(self.cog))
        except Exception as e:
            print(f"[EVENTS] send_modal failed (setup): {e}")


# ==============================================================================
# COG
# ==============================================================================

class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminder_task.start()

    def cog_unload(self):
        self.reminder_task.cancel()

    @tasks.loop(seconds=20)
    async def reminder_task(self):
        # fix A: keep the loop alive across transient failures.
        try:
            await self.process_due_reminders()
        except Exception as e:
            print(f"[EVENTS] reminder loop iteration failed: {type(e).__name__}: {e}")
            traceback.print_exc()

    async def process_due_reminders(self) -> int:
        """Check and send all due event reminders, persisting status to prevent duplicates."""
        # fix I: outer DB read guarded.
        try:
            due_events = db.get_due_reminders() or []
        except Exception as e:
            print(f"[EVENTS] get_due_reminders failed: {e}")
            return 0

        sent_count = 0
        tz_off = _safe_tz_off()

        for ev in due_events:
            # fix I: each event's processing is fully guarded.
            try:
                ev_id = ev.get("id")
                if not ev_id:
                    print(f"[EVENTS] skipping reminder with no id: {ev}")
                    continue

                # Best-effort mark-sent to avoid duplicate posts.
                try:
                    db.mark_reminder_sent(ev_id)
                except Exception as e:
                    print(f"[EVENTS] mark_reminder_sent failed for {ev_id}: {e}")
                    # Continue anyway — better to send than to skip entirely.

                # Resolve channel.
                try:
                    fallback = db.get_config("event_channel_id", str(EVENT_CHANNEL_ID or 0))
                except Exception as e:
                    print(f"[EVENTS] event_channel_id read failed: {e}")
                    fallback = str(EVENT_CHANNEL_ID or 0)

                chan_id = int(ev.get("channel_id") or fallback or 0)

                # fix K: log why we're skipping.
                if not chan_id:
                    print(f"[EVENTS] skipping reminder {ev_id}: no channel configured")
                    continue

                channel = self.bot.get_channel(chan_id)
                if not channel:
                    try:
                        channel = await self.bot.fetch_channel(chan_id)
                    except Exception as e:
                        print(f"[EVENTS] fetch_channel({chan_id}) failed: {e}")
                        channel = None

                if not channel:
                    print(f"[EVENTS] reminder {ev_id}: channel {chan_id} not found")
                    continue

                start_dt = _parse_iso_utc(ev.get("start_time_utc"))
                if start_dt is None:
                    print(f"[EVENTS] reminder {ev_id}: invalid start_time_utc")
                    continue

                try:
                    dual = format_dual_timestamps(start_dt, tz_off)
                except Exception as e:
                    print(f"[EVENTS] reminder {ev_id}: format_dual_timestamps failed: {e}")
                    continue

                rem_mins = ev.get("reminder_minutes", 10)
                ev_name = ev.get("name", "Event")

                embed = rof_embed(
                    title=f"🔔 ROF EVENT REMINDER — {ev_name.upper()}",
                    description=(
                        f"⚔️ **{ev_name}** starts in **{rem_mins} minutes**!\n"
                        + (f"\n{ev['description']}\n\n" if ev.get("description") else "\n")
                        + f"🕒 **Game Time:** `{dual['game_time']}`\n"
                        f"🇮🇳 **India Time:** `{dual['india_time']}`\n"
                        f"🌍 **Discord Timestamp:** {dual['discord_full']} ({dual['discord_relative']})"
                    ),
                    color=ROFColors.WARNING,
                    footer_extra=f"Event ID: {ev_id}",
                )
                await channel.send(
                    content="@everyone 🔔 **ROF Alliance Event Reminder!**",
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(everyone=True),
                )
                sent_count += 1
            except Exception as e:
                print(f"[EVENTS] reminder processing error: {type(e).__name__}: {e}")
                traceback.print_exc()
                continue

        return sent_count

    @reminder_task.before_loop
    async def before_reminder(self):
        await self.bot.wait_for("ready") if False else await self.bot.wait_until_ready()

    # ---------- COMMANDS ----------

    @app_commands.command(name="events", description="View upcoming ROF alliance events in Game Time & India Time")
    async def list_events(self, interaction: discord.Interaction):
        try:
            upcoming = db.get_upcoming_events(include_cancelled=False) or []
        except Exception as e:
            print(f"[EVENTS] get_upcoming_events failed: {e}")
            return await interaction.response.send_message(
                "⚠️ Could not load events right now. Please try again.", ephemeral=True
            )

        if not upcoming:
            embed = rof_embed(
                title="📅 ROF UPCOMING EVENTS",
                description="No upcoming events are currently scheduled. ⚔️",
                color=ROFColors.INFO,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        tz_off = _safe_tz_off()
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
                # fix F: skip malformed rows instead of killing the whole list.
                try:
                    dt = _parse_iso_utc(ev.get("start_time_utc"))
                    if dt is None:
                        continue
                    try:
                        dual = format_dual_timestamps(dt, tz_off)
                    except Exception as e:
                        print(f"[EVENTS] list format_dual_timestamps failed: {e}")
                        continue
                    desc_line = f"📝 *{ev['description']}*\n" if ev.get("description") else ""
                    val = (
                        f"{desc_line}"
                        f"📅 **Date:** {dual['short_date']} | "
                        f"**Status:** `{str(ev.get('status', 'unknown')).upper()}`\n"
                        f"🕒 **Game Time:** `{dual['game_time']}`\n"
                        f"🇮🇳 **India Time:** `{dual['india_time']}`\n"
                        f"⏳ **Countdown:** {dual['discord_relative']} ({dual['discord_short']})"
                    )
                    embed.add_field(
                        name=f"⚔️ {ev.get('name', '?')} (ID: `{ev.get('id', '?')}`)",
                        value=val,
                        inline=False,
                    )
                except Exception as e:
                    print(f"[EVENTS] list row render failed: {e}")
                    continue

            # If all rows in a chunk were malformed, skip the page.
            if embed.fields:
                pages.append(embed)

        if not pages:
            return await interaction.response.send_message(
                "⚠️ Events exist but could not be displayed (malformed data).",
                ephemeral=True,
            )

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0], ephemeral=True)
        else:
            view = PaginatedEmbedView(interaction.user.id, pages)
            await interaction.response.send_message(embed=pages[0], view=view, ephemeral=True)

    # Structured /event command group
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
        try:
            await interaction.response.send_modal(
                EventCreateOrEditModal(self, channel_id=chan_id)
            )
        except Exception as e:
            print(f"[EVENTS] send_modal failed (create): {e}")

    @event_group.command(name="edit", description="Edit an existing alliance event (Admin/Owner only)")
    @app_commands.describe(event_id="The 6-character ID of the event to edit")
    async def event_edit_cmd(self, interaction: discord.Interaction, event_id: str):
        if not await ensure_admin(interaction):
            return
        # fix H: guard DB read.
        try:
            ev = db.get_event(event_id)
        except Exception as e:
            print(f"[EVENTS] get_event failed (edit cmd): {e}")
            return await interaction.response.send_message(
                "⚠️ Could not load that event right now.", ephemeral=True
            )
        if not ev:
            return await interaction.response.send_message(
                f"❌ Event ID `{event_id}` not found.", ephemeral=True
            )
        try:
            await interaction.response.send_modal(
                EventCreateOrEditModal(self, existing_event=ev)
            )
        except Exception as e:
            print(f"[EVENTS] send_modal failed (edit cmd): {e}")

    @event_group.command(name="cancel", description="Cancel a scheduled alliance event (Admin/Owner only)")
    @app_commands.describe(event_id="The 6-character ID of the event to cancel")
    async def event_cancel_cmd(self, interaction: discord.Interaction, event_id: str):
        if not await ensure_admin(interaction):
            return
        try:
            ev = db.cancel_or_delete_event(event_id, delete_permanently=False)
        except Exception as e:
            print(f"[EVENTS] cancel_or_delete_event failed (cancel): {e}")
            return await interaction.response.send_message(
                "⚠️ Could not cancel that event right now.", ephemeral=True
            )
        if not ev:
            return await interaction.response.send_message(
                f"❌ Event ID `{event_id}` not found.", ephemeral=True
            )
        # fix C: audit log is fire-and-forget.
        try:
            db.log_audit(
                interaction.user.id,
                "event_cancel",
                f"Cancelled event {event_id} ({ev['name']})",
            )
        except Exception as e:
            print(f"[EVENTS] log_audit failed (cancel): {e}")
        embed = rof_embed(
            title="🚫 EVENT CANCELLED",
            description=(
                f"Event **{ev.get('name', '?')}** (`{ev.get('id', event_id)}`) "
                f"has been cancelled and its pending reminder has been cleared."
            ),
            color=ROFColors.WARNING,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @event_group.command(name="delete", description="Permanently delete an alliance event (Admin/Owner only)")
    @app_commands.describe(event_id="The 6-character ID of the event to delete")
    async def event_delete_cmd(self, interaction: discord.Interaction, event_id: str):
        if not await ensure_admin(interaction):
            return
        try:
            ev = db.cancel_or_delete_event(event_id, delete_permanently=True)
        except Exception as e:
            print(f"[EVENTS] cancel_or_delete_event failed (delete): {e}")
            return await interaction.response.send_message(
                "⚠️ Could not delete that event right now.", ephemeral=True
            )
        if not ev:
            return await interaction.response.send_message(
                f"❌ Event ID `{event_id}` not found.", ephemeral=True
            )
        try:
            db.log_audit(
                interaction.user.id,
                "event_delete",
                f"Deleted event {event_id} ({ev['name']})",
            )
        except Exception as e:
            print(f"[EVENTS] log_audit failed (delete): {e}")
        await interaction.response.send_message(
            f"🗑️ Event **{ev.get('name', '?')}** (`{ev.get('id', event_id)}`) "
            f"has been permanently deleted.",
            ephemeral=True,
        )

    @event_group.command(name="view", description="View full details and timezone conversions for an event")
    @app_commands.describe(event_id="The 6-character ID of the event")
    async def event_view_cmd(self, interaction: discord.Interaction, event_id: str):
        try:
            ev = db.get_event(event_id)
        except Exception as e:
            print(f"[EVENTS] get_event failed (view): {e}")
            return await interaction.response.send_message(
                "⚠️ Could not load that event right now.", ephemeral=True
            )
        if not ev:
            return await interaction.response.send_message(
                f"❌ Event ID `{event_id}` not found. Use `/events` to see all upcoming event IDs.",
                ephemeral=True,
            )
        await interaction.response.send_message(
            embed=build_event_detail_embed(ev), ephemeral=True
        )

    # Preserved legacy /event_cancel command
    @app_commands.command(name="event_cancel", description="Cancel an event by ID (Admin/Owner)")
    @app_commands.describe(event_id="The short ID of the event (e.g. a1b2c3)")
    async def cancel_event_legacy(self, interaction: discord.Interaction, event_id: str):
        await self.event_cancel_cmd.callback(self, interaction, event_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))