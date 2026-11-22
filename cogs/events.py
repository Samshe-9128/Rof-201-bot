# cogs/events.py
import uuid
import traceback
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone
from typing import List, Optional

from core.config import (
    DEFAULT_TZ_OFFSET, EVENT_CHANNEL_ID, ROFColors,
    format_dual_timestamps, format_tz_label, get_game_tz,
)
from core.database import db
from core.permissions import ensure_admin, is_admin_interaction
from core.ui import get_alliance_short, safe_reply_error, PaginatedEmbedView, rof_embed


# ==============================================================================
# MODULE-LEVEL HELPERS
# ==============================================================================

def _parse_iso_utc(raw_value) -> Optional[datetime]:
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
    try:
        return float(db.get_config("game_tz_offset", str(DEFAULT_TZ_OFFSET)))
    except Exception as e:
        print(f"[EVENTS] tz config read failed: {e}")
        return float(DEFAULT_TZ_OFFSET)


def _default_reminder_minutes() -> int:
    try:
        return int(db.get_config("default_reminder_minutes", "10") or 10)
    except Exception as e:
        print(f"[EVENTS] default_reminder_minutes read failed: {e}")
        return 10


def _format_reminder(minutes: int) -> str:
    try:
        m = int(minutes)
    except Exception:
        return "10 minutes before start"
    if m <= 0:
        return "No reminder (starts immediately)"
    if m == 60:
        return "1 hour before start"
    if m == 120:
        return "2 hours before start"
    if m == 1440:
        return "24 hours before start"
    return f"{m} minutes before start"


def _format_repeat(repeat_days: int) -> str:
    try:
        d = int(repeat_days or 0)
    except Exception:
        d = 0
    if d <= 0:
        return "One-time"
    if d == 1:
        return "🔁 Every day"
    if d == 7:
        return "🔁 Every 7 days (Weekly)"
    return f"🔁 Every {d} days"


def _format_announce(announce_enabled) -> str:
    on = int(announce_enabled) if announce_enabled is not None else 1
    return "🔔 ON" if on == 1 else "🔕 OFF (Muted)"


def parse_event_datetime(date_str: str, time_str: str,
                          tz_offset: Optional[float] = None) -> datetime:
    game_tz = get_game_tz(tz_offset)
    dt = datetime.strptime(
        f"{date_str.strip()} {time_str.strip()}", "%Y-%m-%d %H:%M"
    )
    return dt.replace(tzinfo=game_tz)


# >>> MODULE-LEVEL AUTOCOMPLETE (the fix) <<<
async def event_id_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    try:
        upcoming = db.get_upcoming_events(include_cancelled=False) or []
    except Exception as e:
        print(f"[EVENTS] autocomplete fetch failed: {e}")
        return []
    current_l = (current or "").lower()
    choices: List[app_commands.Choice[str]] = []
    for ev in upcoming:
        try:
            eid = str(ev.get("id", ""))
            name = str(ev.get("name", "?"))
            label = f"{name} ({eid})"[:100]
            if current_l in label.lower() or current_l in eid.lower():
                choices.append(app_commands.Choice(name=label, value=eid))
            if len(choices) >= 25:
                break
        except Exception:
            continue
    return choices


async def _save_reminder_with_fallback(event_id: str, minutes: int,
                                        base_kwargs: dict) -> bool:
    """Persist event updates including reminder_minutes."""
    try:
        db.update_event(reminder_minutes=minutes, **base_kwargs)
        return True
    except Exception as e:
        print(f"[EVENTS] update_event failed: {e}")
        return False


def build_event_detail_embed(ev: dict,
                             title_prefix: Optional[str] = None) -> discord.Embed:
    if title_prefix is None:
        title_prefix = f"📅 {get_alliance_short()} EVENT DETAILS"
    try:
        tz_off = _safe_tz_off()
        start_dt = _parse_iso_utc(ev.get("start_time_utc"))
        if start_dt is None:
            raise ValueError("missing or invalid start_time_utc")
        try:
            dual = format_dual_timestamps(start_dt, tz_off)
        except Exception as e:
            print(f"[EVENTS] format_dual_timestamps failed: {e}")
            raw = ev.get("start_time_utc", "?")
            dual = {"short_date": "?", "date_str": raw, "game_time": "?",
                    "india_time": "?", "discord_full": raw, "discord_relative": "?"}

        rem = int(ev.get("reminder_minutes", 10) or 0)
        dur = int(ev.get("duration_minutes", 60) or 60)
        rep = int(ev.get("repeat_days", 0) or 0)
        ann = ev.get("announce_enabled", 1)
        status = str(ev.get("status", "scheduled")).upper()

        desc = (
            f"**Event:** {ev.get('name', '?')}\n"
            f"**Event ID:** `{ev.get('id', '?')}`\n"
            f"**Date:** {dual['short_date']} ({dual['date_str']})\n"
            f"**Game Time:** `{dual['game_time']}`\n"
            f"**India Time:** `{dual['india_time']}`\n"
            f"**Your Local Time:** {dual['discord_full']} ({dual['discord_relative']})\n"
            f"**Duration:** `{dur} mins` | **Status:** `{status}`\n"
            f"**Reminder:** {_format_reminder(rem)}\n"
            f"**Repeat:** {_format_repeat(rep)} | **Announcements:** {_format_announce(ann)}"
        )
        if ev.get("description"):
            desc += f"\n\n**Description:**\n{ev['description']}"
        color = ROFColors.SUCCESS if status == "SCHEDULED" else ROFColors.ERROR
        return rof_embed(title=title_prefix, description=desc, color=color,
                         footer_extra=f"Event ID: {ev.get('id', '?')}")
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
        label="Event Name", placeholder="e.g., Surge / Alliance Brawl",
        max_length=60, required=True)
    event_date = discord.ui.TextInput(
        label="Date (YYYY-MM-DD)", placeholder="e.g., 2026-11-12",
        min_length=10, max_length=10, required=True)
    event_time = discord.ui.TextInput(
        label="Game Time (HH:MM in UTC-2)", placeholder="e.g., 16:00",
        min_length=4, max_length=5, required=True)
    reminder_minutes = discord.ui.TextInput(
        label="Reminder (minutes before start)",
        placeholder="Leave blank for default (10). Use 0 for no reminder.",
        max_length=4, required=False)
    repeat_days = discord.ui.TextInput(
        label="Repeat Every N Days (optional)",
        placeholder="Blank or 0 = once, e.g. 2 = every 2 days, 7 = weekly",
        max_length=3, required=False)

    def __init__(self, cog: "Events", channel_id: Optional[int] = None,
                 existing_event: Optional[dict] = None,
                 duration_minutes: int = 60,
                 default_repeat_days: Optional[int] = None,
                 announce_enabled: bool = True):
        short = get_alliance_short()
        title = (f"Edit Event ({existing_event.get('id', '?')})"[:45]
                 if existing_event else f"Create {short} Event"[:45])
        super().__init__(title=title)
        self.cog = cog
        self.channel_id = channel_id
        self.existing_event = existing_event
        self.duration_val = max(1, min(1440, int(duration_minutes or 60)))
        self.announce_enabled = bool(announce_enabled)
        try:
            tz_label = format_tz_label(_safe_tz_off())
            self.event_time.label = f"Game Time (HH:MM in {tz_label})"[:45]
        except Exception:
            pass

        if existing_event:
            try:
                tz_off = _safe_tz_off()
                start_dt = _parse_iso_utc(existing_event.get("start_time_utc")) \
                          or datetime.now(timezone.utc)
                try:
                    local_dt = start_dt.astimezone(get_game_tz(tz_off))
                except Exception:
                    local_dt = start_dt
                self.event_name.default = existing_event.get("name", "")
                self.event_date.default = local_dt.strftime("%Y-%m-%d")
                self.event_time.default = local_dt.strftime("%H:%M")
                self.duration_val = int(existing_event.get("duration_minutes", 60) or 60)
                self.reminder_minutes.default = str(
                    existing_event.get("reminder_minutes", _default_reminder_minutes()))
                self.repeat_days.default = str(int(existing_event.get("repeat_days", 0) or 0))
            except Exception as e:
                print(f"[EVENTS] modal prefill failed: {type(e).__name__}: {e}")
        else:
            try:
                d = _default_reminder_minutes()
                self.reminder_minutes.placeholder = f"Blank = default {d} min. 0 = no reminder."
                if default_repeat_days is not None and default_repeat_days >= 0:
                    self.repeat_days.default = str(int(default_repeat_days))
            except Exception:
                pass

    async def on_submit(self, interaction: discord.Interaction):
        if not await ensure_admin(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self._handle_submit(interaction)
        except Exception as e:
            print(f"[EVENTS] modal on_submit failed: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                await interaction.followup.send(
                    "⚠️ Could not save the event. Please try again.", ephemeral=True)
            except Exception:
                pass

    async def _handle_submit(self, interaction: discord.Interaction):
        clean_name = (self.event_name.value or "").strip()
        if not clean_name:
            return await interaction.followup.send(
                "❌ **Event Name cannot be empty!**", ephemeral=True)
        tz_off = _safe_tz_off()
        try:
            event_dt = parse_event_datetime(
                self.event_date.value, self.event_time.value, tz_off)
        except ValueError:
            return await interaction.followup.send(
                "❌ **Invalid Date or Time Format!** Use `YYYY-MM-DD` and 24-hour `HH:MM`.",
                ephemeral=True)

        now = datetime.now(timezone.utc)
        time_unchanged = False
        if self.existing_event:
            old_dt = _parse_iso_utc(self.existing_event.get("start_time_utc"))
            time_unchanged = old_dt is not None and event_dt == old_dt
        if not time_unchanged and event_dt <= now:
            return await interaction.followup.send(
                "❌ **Past Time Rejected!** Please schedule the event for a future time.",
                ephemeral=True)

        dur_val = self.duration_val

        rem_default = _default_reminder_minutes()
        rem_raw = (self.reminder_minutes.value or "").strip()
        if not rem_raw:
            rem_val = rem_default
        else:
            if not rem_raw.isdigit():
                return await interaction.followup.send(
                    f"❌ **Invalid Reminder!** Whole number of minutes "
                    f"(0–1440), or leave blank for default ({rem_default}).",
                    ephemeral=True)
            rem_val = int(rem_raw)
            if rem_val < 0 or rem_val > 1440:
                return await interaction.followup.send(
                    "❌ **Invalid Reminder!** Must be `0`–`1440` minutes.", ephemeral=True)

        rep_raw = (self.repeat_days.value or "").strip()
        if not rep_raw:
            rep_val = 0
        else:
            if not rep_raw.isdigit():
                return await interaction.followup.send(
                    "❌ **Invalid Repeat Days!** Enter a whole number (e.g. `2` for every 2 days, or `0` for one-time).",
                    ephemeral=True)
            rep_val = int(rep_raw)
            if rep_val < 0 or rep_val > 365:
                return await interaction.followup.send(
                    "❌ **Invalid Repeat Days!** Must be between `0` and `365`.", ephemeral=True)

        try:
            default_chan = int(db.get_config("event_channel_id",
                                             str(EVENT_CHANNEL_ID or 0)) or 0)
        except Exception as e:
            print(f"[EVENTS] event_channel_id read failed: {e}")
            default_chan = int(EVENT_CHANNEL_ID or 0)

        target_chan_id = (
            self.channel_id
            or (self.existing_event["channel_id"] if self.existing_event else default_chan)
            or (interaction.channel.id if interaction.channel else 0)
        )

        # ---------- EDIT ----------
        if self.existing_event:
            base_kwargs = dict(
                event_id=self.existing_event["id"],
                name=self.event_name.value,
                description=self.existing_event.get("description", ""),
                start_time_utc=event_dt,
                duration_minutes=dur_val,
                channel_id=target_chan_id,
                repeat_days=rep_val,
            )
            if not await _save_reminder_with_fallback(
                    self.existing_event["id"], rem_val, base_kwargs):
                return await interaction.followup.send(
                    "⚠️ Could not update the event in the database. Please try again.",
                    ephemeral=True)
            try:
                updated = db.get_event(self.existing_event["id"])
            except Exception as e:
                print(f"[EVENTS] post-update get_event failed: {e}")
                updated = None
            if updated is None:
                updated = {**self.existing_event, "reminder_minutes": rem_val}
            try:
                db.log_audit(interaction.user.id, "event_edit",
                             f"Edited event {updated['id']} ({updated.get('name', '?')}), reminder={rem_val}m")
            except Exception as e:
                print(f"[EVENTS] log_audit failed (edit): {e}")

            embed = build_event_detail_embed(updated, title_prefix="✅ EVENT UPDATED")
            view = EventConfirmationView(self.cog, updated["id"])
            return await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        # ---------- CREATE ----------
        event_id = str(uuid.uuid4())[:6]
        try:
            created = db.create_event(
                event_id=event_id, name=clean_name,
                description="",
                start_time_utc=event_dt, duration_minutes=dur_val,
                channel_id=target_chan_id, creator_id=interaction.user.id,
                reminder_minutes=rem_val,
                repeat_days=rep_val,
                announce_enabled=(1 if self.announce_enabled else 0),
            )
        except Exception as e:
            print(f"[EVENTS] create_event failed: {type(e).__name__}: {e}")
            return await interaction.followup.send(
                "⚠️ Could not save the event to the database. Please try again.",
                ephemeral=True)
        try:
            db.log_audit(interaction.user.id, "event_create",
                         f"Created event {event_id} ({created['name']}), reminder={rem_val}m")
        except Exception as e:
            print(f"[EVENTS] log_audit failed (create): {e}")

        target_channel = self.cog.bot.get_channel(target_chan_id)
        if not target_channel and target_chan_id:
            try:
                target_channel = await self.cog.bot.fetch_channel(target_chan_id)
            except Exception:
                target_channel = None
        ann_status = "🔕 Created silently (announcements muted)."
        if not self.announce_enabled:
            pass
        elif target_channel:
            try:
                dual = format_dual_timestamps(event_dt, tz_off)
                ann_embed = rof_embed(
                    title=f"📢 {get_alliance_short()} EVENT SCHEDULED — {created['name'].upper()}",
                    description=(
                        (f"{created['description']}\n\n" if created.get("description") else "")
                        + f"📅 **Date:** {dual['short_date']}\n"
                          f"🕒 **Game Time:** `{dual['game_time']}`\n"
                          f"🇮🇳 **India Time:** `{dual['india_time']}`\n"
                          f"🌍 **Your Time:** {dual['discord_full']} ({dual['discord_relative']})\n"
                          f"🔔 **Reminder:** {_format_reminder(rem_val)}\n"
                          f"🔁 **Schedule:** {_format_repeat(rep_val)}"),
                    color=ROFColors.GOLD, footer_extra=f"Event ID: {event_id}")
                await target_channel.send(embed=ann_embed)
                ann_status = f"📢 Announced in <#{target_channel.id}>"
            except Exception as e:
                print(f"[EVENTS] could not post announcement to {target_chan_id}: {e}")
                ann_status = f"⚠️ Saved, but could not post to <#{target_chan_id}> (check bot channel permissions)."
        elif target_chan_id:
            ann_status = f"⚠️ Saved, but could not access channel `{target_chan_id}`."
        else:
            ann_status = "⚠️ No announcement channel configured (set one with `/admin channels`)."

        try:
            dual = format_dual_timestamps(event_dt, tz_off)
        except Exception:
            dual = {"short_date": event_dt.strftime("%Y-%m-%d"),
                    "game_time_short": event_dt.strftime("%H:%M"),
                    "india_time_short": "?"}

        confirm_embed = rof_embed(
            title="✅ EVENT CREATED",
            description=(
                f"**Event:** {created['name']}\n"
                f"**Event ID:** `{created['id']}`\n"
                f"**Date:** {dual['short_date']}\n"
                f"**Game Time:** `{dual['game_time']}`\n"
                f"**India Time:** `{dual['india_time']}`\n"
                f"**Reminder:** {_format_reminder(rem_val)}\n"
                f"**Repeat:** {_format_repeat(rep_val)} | **Announcements:** {_format_announce(1 if self.announce_enabled else 0)}\n"
                f"{ann_status}"),
            color=ROFColors.SUCCESS, footer_extra=f"Event ID: {created['id']}")
        view = EventConfirmationView(self.cog, created["id"])
        await interaction.followup.send(embed=confirm_embed, view=view, ephemeral=True)


class EventConfirmationView(discord.ui.View):
    def __init__(self, cog: "Events", event_id: str):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.event_id = event_id

    @discord.ui.button(label="Edit Event", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_admin(interaction):
            return
        try:
            ev = db.get_event(self.event_id)
        except Exception as e:
            print(f"[EVENTS] get_event failed (edit btn): {e}")
            return await interaction.response.send_message(
                "⚠️ Could not load the event right now.", ephemeral=True)
        if not ev:
            return await interaction.response.send_message(
                "❌ Event no longer exists.", ephemeral=True)
        try:
            await interaction.response.send_modal(
                EventCreateOrEditModal(self.cog, existing_event=ev))
        except Exception as e:
            print(f"[EVENTS] send_modal failed (edit btn): {e}")
            await safe_reply_error(interaction, "⚠️ Could not open the form right now. Please try again.")

    @discord.ui.button(label="View Event", style=discord.ButtonStyle.secondary, emoji="👁️")
    async def view_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            ev = db.get_event(self.event_id)
        except Exception as e:
            print(f"[EVENTS] get_event failed (view btn): {e}")
            return await interaction.response.send_message(
                "⚠️ Could not load the event right now.", ephemeral=True)
        if not ev:
            return await interaction.response.send_message(
                "❌ Event not found.", ephemeral=True)
        await interaction.response.send_message(
            embed=build_event_detail_embed(ev), ephemeral=True)

    @discord.ui.button(label="Mute / Unmute Alerts", style=discord.ButtonStyle.secondary, emoji="🔕")
    async def toggle_ann_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_admin(interaction):
            return
        ev = db.get_event(self.event_id)
        if not ev:
            return await interaction.response.send_message("❌ Event not found.", ephemeral=True)
        cur = int(ev.get("announce_enabled") if ev.get("announce_enabled") is not None else 1)
        new_state = (cur == 0)
        updated = db.set_event_announce(self.event_id, new_state)
        state_lbl = "🔔 **ON**" if new_state else "🔕 **OFF (Muted)**"
        await interaction.response.send_message(
            f"Announcements for **{ev.get('name', '?')}** (`{self.event_id}`) are now {state_lbl}.",
            ephemeral=True,
        )

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_admin(interaction):
            return
        ev = db.get_event(self.event_id)
        if not ev:
            return await interaction.response.send_message("❌ Event not found.", ephemeral=True)
        await interaction.response.send_message(
            f"⚠️ Permanently delete **{ev.get('name', '?')}** (`{self.event_id}`)? This cannot be undone.",
            view=ConfirmDeleteView(self.event_id, ev.get("name", "?")),
            ephemeral=True,
        )

    async def on_timeout(self):
        for child in self.children:
            try:
                child.disabled = True
            except Exception:
                pass


class EventPickerSelect(discord.ui.Select):
    def __init__(self, cog: "Events", events_list: List[dict], action: str):
        self.cog = cog
        self.action = action
        options: List[discord.SelectOption] = []
        for ev in events_list[:25]:
            try:
                eid = str(ev.get("id", "?"))
                name = str(ev.get("name", "?"))
                dt = _parse_iso_utc(ev.get("start_time_utc"))
                when = dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "?"
                options.append(discord.SelectOption(
                    label=name[:100], value=eid,
                    description=f"{eid} • {when}"[:100]))
            except Exception:
                continue
        if not options:
            options = [discord.SelectOption(label="No events", value="__none__")]
        super().__init__(placeholder=f"🎯 Pick an event to {action}…",
                         options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        eid = self.values[0]
        if eid == "__none__":
            return await interaction.response.send_message("No events to pick from.",
                                                          ephemeral=True)
        if self.action in ("edit", "cancel", "delete"):
            if not await ensure_admin(interaction):
                return
        try:
            ev = db.get_event(eid)
        except Exception as e:
            print(f"[EVENTS] get_event failed (picker): {e}")
            return await interaction.response.send_message(
                "⚠️ Could not load event.", ephemeral=True)
        if not ev:
            return await interaction.response.send_message("❌ Event not found.",
                                                          ephemeral=True)

        if self.action == "edit":
            try:
                await interaction.response.send_modal(
                    EventCreateOrEditModal(self.cog, existing_event=ev))
            except Exception as e:
                print(f"[EVENTS] send_modal (picker edit) failed: {e}")
                await safe_reply_error(interaction, "⚠️ Could not open the form right now. Please try again.")
        elif self.action == "view":
            view = EventConfirmationView(self.cog, ev["id"]) if is_admin_interaction(interaction) else None
            if view:
                await interaction.response.send_message(embed=build_event_detail_embed(ev), view=view, ephemeral=True)
            else:
                await interaction.response.send_message(embed=build_event_detail_embed(ev), ephemeral=True)
        elif self.action == "cancel":
            try:
                cancelled = db.cancel_or_delete_event(eid, delete_permanently=False)
            except Exception as e:
                print(f"[EVENTS] cancel failed (picker): {e}")
                return await interaction.response.send_message(
                    "⚠️ Could not cancel event.", ephemeral=True)
            if not cancelled:
                return await interaction.response.send_message(
                    "❌ Event not found.", ephemeral=True)
            try:
                db.log_audit(interaction.user.id, "event_cancel",
                             f"Cancelled event {eid} ({ev['name']})")
            except Exception:
                pass
            await interaction.response.edit_message(
                content=f"🚫 Event **{ev.get('name', '?')}** (`{eid}`) has been cancelled.",
                view=None)
        elif self.action == "delete":
            await interaction.response.send_message(
                f"⚠️ Permanently delete **{ev.get('name', '?')}** (`{eid}`)? "
                f"This cannot be undone.",
                view=ConfirmDeleteView(eid, ev.get("name", "?")), ephemeral=True)


class EventPickerView(discord.ui.View):
    def __init__(self, cog: "Events", events_list: List[dict], action: str):
        super().__init__(timeout=180)
        self.add_item(EventPickerSelect(cog, events_list, action))


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, event_id: str, event_name: str):
        super().__init__(timeout=60)
        self.event_id = event_id
        self.event_name = event_name

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_admin(interaction):
            return
        try:
            ev = db.cancel_or_delete_event(self.event_id, delete_permanently=True)
        except Exception as e:
            print(f"[EVENTS] delete failed: {e}")
            return await interaction.response.send_message(
                "⚠️ Could not delete the event.", ephemeral=True)
        if not ev:
            return await interaction.response.send_message("❌ Event not found.",
                                                          ephemeral=True)
        try:
            db.log_audit(interaction.user.id, "event_delete",
                         f"Deleted event {self.event_id} ({self.event_name})")
        except Exception:
            pass
        await interaction.response.edit_message(
            content=f"🗑️ Event **{self.event_name}** (`{self.event_id}`) has been permanently deleted.",
            view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Deletion cancelled.", view=None)


# ==============================================================================
# COG
# ==============================================================================

class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminder_task.start()

    def cog_unload(self):
        self.reminder_task.cancel()

    async def _show_picker(self, interaction: discord.Interaction, action: str):
        try:
            upcoming = db.get_upcoming_events(include_cancelled=False) or []
        except Exception as e:
            print(f"[EVENTS] picker fetch failed: {e}")
            return await interaction.response.send_message(
                "⚠️ Could not load events right now.", ephemeral=True)
        if not upcoming:
            return await interaction.response.send_message(
                "📭 No upcoming events to pick from. Use `/event add` to schedule one.",
                ephemeral=True)
        await interaction.response.send_message(
            f"🎯 Pick an event to **{action}**:",
            view=EventPickerView(self, upcoming, action), ephemeral=True)

    # ---------------- Reminder loop ----------------
    @tasks.loop(seconds=20)
    async def reminder_task(self):
        try:
            await self.process_due_reminders()
        except Exception as e:
            print(f"[EVENTS] reminder loop iteration failed: {type(e).__name__}: {e}")
            traceback.print_exc()

    async def process_due_reminders(self) -> int:
        try:
            due_events = db.get_due_reminders() or []
        except Exception as e:
            print(f"[EVENTS] get_due_reminders failed: {e}")
            return 0
        sent_count = 0
        tz_off = _safe_tz_off()
        for ev in due_events:
            try:
                ev_id = ev.get("id")
                if not ev_id:
                    continue
                try:
                    db.mark_reminder_sent(ev_id)
                except Exception as e:
                    print(f"[EVENTS] mark_reminder_sent failed for {ev_id}: {e}")
                try:
                    fallback = db.get_config("event_channel_id", str(EVENT_CHANNEL_ID or 0))
                except Exception:
                    fallback = str(EVENT_CHANNEL_ID or 0)
                chan_id = int(ev.get("channel_id") or fallback or 0)
                if not chan_id:
                    continue
                channel = self.bot.get_channel(chan_id)
                if not channel:
                    try:
                        channel = await self.bot.fetch_channel(chan_id)
                    except Exception as e:
                        print(f"[EVENTS] fetch_channel({chan_id}) failed: {e}")
                        channel = None
                if not channel:
                    continue
                start_dt = _parse_iso_utc(ev.get("start_time_utc"))
                if start_dt is None:
                    continue
                try:
                    dual = format_dual_timestamps(start_dt, tz_off)
                except Exception as e:
                    print(f"[EVENTS] reminder {ev_id}: format failed: {e}")
                    continue
                rem_mins = int(ev.get("reminder_minutes", 10) or 0)
                ev_name = ev.get("name", "Event")
                lead_line = (f"⚔️ **{ev_name}** is starting now!"
                             if rem_mins <= 0
                             else f"⚔️ **{ev_name}** starts in **{rem_mins} minutes**!")
                embed = rof_embed(
                    title=f"🔔 {get_alliance_short()} EVENT REMINDER — {ev_name.upper()}",
                    description=(f"{lead_line}\n"
                                 + (f"\n{ev['description']}\n\n" if ev.get("description") else "\n")
                                 + f"🕒 **Game Time:** `{dual['game_time']}`\n"
                                   f"🇮🇳 **India Time:** `{dual['india_time']}`\n"
                                   f"🌍 **Discord Timestamp:** {dual['discord_full']} ({dual['discord_relative']})"),
                    color=ROFColors.WARNING, footer_extra=f"Event ID: {ev_id}")
                await channel.send(
                    content=f"@everyone 🔔 **{get_alliance_short()} Alliance Event Reminder!**",
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(everyone=True))
                sent_count += 1
            except Exception as e:
                print(f"[EVENTS] reminder processing error: {type(e).__name__}: {e}")
                traceback.print_exc()
                continue
        return sent_count

    @reminder_task.before_loop
    async def before_reminder(self):
        await self.bot.wait_until_ready()

    # ================================================================
    # COMMANDS — flat, no /event group
    # ================================================================

    async def _send_events_list(self, interaction: discord.Interaction):
        try:
            upcoming = db.get_upcoming_events(include_cancelled=False) or []
        except Exception as e:
            print(f"[EVENTS] get_upcoming_events failed: {e}")
            return await interaction.response.send_message(
                "⚠️ Could not load events right now.", ephemeral=True)
        short = get_alliance_short()
        if not upcoming:
            return await interaction.response.send_message(
                embed=rof_embed(title=f"📅 {short} UPCOMING EVENTS",
                                description="No upcoming events are currently scheduled. ⚔️",
                                color=ROFColors.INFO),
                ephemeral=True)
        tz_off = _safe_tz_off()
        tz_label = format_tz_label(tz_off)
        per_page = 4
        pages: List[discord.Embed] = []
        for idx in range(0, len(upcoming), per_page):
            chunk = upcoming[idx:idx + per_page]
            embed = rof_embed(
                title=f"⚔️ {short} UPCOMING ALLIANCE EVENTS",
                description=f"All times shown in **Game Time (`{tz_label}`)**, **India Time (`IST`)**, and your local time:",
                color=ROFColors.ARENA)
            for ev in chunk:
                try:
                    dt = _parse_iso_utc(ev.get("start_time_utc"))
                    if dt is None:
                        continue
                    try:
                        dual = format_dual_timestamps(dt, tz_off)
                    except Exception:
                        continue
                    desc_line = f"📝 *{ev['description']}*\n" if ev.get("description") else ""
                    rem = int(ev.get("reminder_minutes", 10) or 0)
                    rep = int(ev.get("repeat_days", 0) or 0)
                    ann = ev.get("announce_enabled", 1)
                    val = (f"{desc_line}"
                           f"📅 **Date:** {dual['short_date']} | **Repeat:** {_format_repeat(rep)}\n"
                           f"🕒 **Game Time:** `{dual['game_time']}`\n"
                           f"🇮🇳 **India Time:** `{dual['india_time']}`\n"
                           f"⏳ **Countdown:** {dual['discord_relative']} ({dual['discord_short']})\n"
                           f"🔔 **Reminder:** {_format_reminder(rem)} | **Alerts:** {_format_announce(ann)}")
                    embed.add_field(
                        name=f"⚔️ {ev.get('name', '?')} (ID: `{ev.get('id', '?')}`)",
                        value=val, inline=False)
                except Exception as e:
                    print(f"[EVENTS] list row render failed: {e}")
                    continue
            if embed.fields:
                pages.append(embed)
        if not pages:
            return await interaction.response.send_message(
                "⚠️ Events exist but could not be displayed (malformed data).",
                ephemeral=True)
        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0], ephemeral=True)
        else:
            view = PaginatedEmbedView(interaction.user.id, pages)
            await interaction.response.send_message(embed=pages[0], view=view, ephemeral=True)

    # ---------- /events & /event COMMAND GROUP (Streamlined) ----------
    event_group = app_commands.Group(
        guild_only=True,
        name="event",
        description="Create, edit, view, and delete alliance events",
    )

    @app_commands.command(
        name="events",
        description="View upcoming alliance events in Game Time & India Time",
    )
    async def list_events(self, interaction: discord.Interaction):
        await self._send_events_list(interaction)

    @event_group.command(
        name="add",
        description="Create & announce a new alliance event with optional repeat schedule (Admin/Owner)",
    )
    @app_commands.describe(
        repeat="Optional repeat schedule (can also enter custom days in the popup)",
        channel="Optional announcement channel (defaults to configured Event Channel)",
        announce="Send announcement & reminders for this event? (Default: True)",
    )
    @app_commands.choices(
        repeat=[
            app_commands.Choice(name="One-time (No repeat)", value=0),
            app_commands.Choice(name="Every Day (1 day)", value=1),
            app_commands.Choice(name="Every 2 Days", value=2),
            app_commands.Choice(name="Every 3 Days", value=3),
            app_commands.Choice(name="Weekly (7 days)", value=7),
            app_commands.Choice(name="Every 14 Days", value=14),
            app_commands.Choice(name="Custom (enter days in popup)", value=-1),
        ]
    )
    async def event_add_cmd(
        self,
        interaction: discord.Interaction,
        repeat: Optional[int] = None,
        channel: Optional[discord.TextChannel] = None,
        announce: bool = True,
    ):
        if not await ensure_admin(interaction):
            return
        chan_id = channel.id if channel else None
        rep_default = repeat if (repeat is not None and repeat >= 0) else None
        try:
            await interaction.response.send_modal(
                EventCreateOrEditModal(
                    self,
                    channel_id=chan_id,
                    default_repeat_days=rep_default,
                    announce_enabled=announce,
                )
            )
        except Exception as e:
            print(f"[EVENTS] send_modal failed (event add): {e}")
            await safe_reply_error(interaction, "⚠️ Could not open the form right now. Please try again.")

    @event_group.command(name="edit", description="Edit an existing alliance event (Admin/Owner only)")
    @app_commands.describe(event_id="The event ID — leave blank to pick from a list")
    @app_commands.autocomplete(event_id=event_id_autocomplete)
    async def event_edit_cmd(self, interaction: discord.Interaction,
                             event_id: Optional[str] = None):
        if not await ensure_admin(interaction):
            return
        if not event_id:
            return await self._show_picker(interaction, "edit")
        try:
            ev = db.get_event(event_id)
        except Exception as e:
            print(f"[EVENTS] get_event failed (event edit): {e}")
            return await interaction.response.send_message(
                "⚠️ Could not load that event right now.", ephemeral=True)
        if not ev:
            return await interaction.response.send_message(
                f"❌ Event ID `{event_id}` not found.", ephemeral=True)
        try:
            await interaction.response.send_modal(
                EventCreateOrEditModal(self, existing_event=ev))
        except Exception as e:
            print(f"[EVENTS] send_modal failed (event edit): {e}")
            await safe_reply_error(interaction, "⚠️ Could not open the form right now. Please try again.")

    @event_group.command(name="view", description="View event details (Admins also get Edit / Mute / Delete buttons)")
    @app_commands.describe(event_id="The event ID — leave blank to pick from a list")
    @app_commands.autocomplete(event_id=event_id_autocomplete)
    async def event_view_cmd(self, interaction: discord.Interaction,
                             event_id: Optional[str] = None):
        if not event_id:
            return await self._show_picker(interaction, "view")
        try:
            ev = db.get_event(event_id)
        except Exception as e:
            print(f"[EVENTS] get_event failed (event view): {e}")
            return await interaction.response.send_message(
                "⚠️ Could not load that event right now.", ephemeral=True)
        if not ev:
            return await interaction.response.send_message(
                f"❌ Event ID `{event_id}` not found. Use `/events` to see all upcoming event IDs.",
                ephemeral=True)
        view = EventConfirmationView(self, ev["id"]) if is_admin_interaction(interaction) else None
        if view:
            await interaction.response.send_message(
                embed=build_event_detail_embed(ev), view=view, ephemeral=True)
        else:
            await interaction.response.send_message(
                embed=build_event_detail_embed(ev), ephemeral=True)

    @event_group.command(name="delete", description="Permanently delete an alliance event (Admin/Owner only)")
    @app_commands.describe(event_id="The event ID — leave blank to pick from a list")
    @app_commands.autocomplete(event_id=event_id_autocomplete)
    async def event_delete_cmd(self, interaction: discord.Interaction,
                               event_id: Optional[str] = None):
        if not await ensure_admin(interaction):
            return
        if not event_id:
            return await self._show_picker(interaction, "delete")
        try:
            ev = db.get_event(event_id)
        except Exception as e:
            print(f"[EVENTS] get_event failed (event delete): {e}")
            return await interaction.response.send_message(
                "⚠️ Could not load that event right now.", ephemeral=True)
        if not ev:
            return await interaction.response.send_message(
                f"❌ Event ID `{event_id}` not found.", ephemeral=True)
        await interaction.response.send_message(
            f"⚠️ Permanently delete **{ev.get('name', '?')}** (`{event_id}`)? "
            f"This cannot be undone.",
            view=ConfirmDeleteView(event_id, ev.get("name", "?")), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
