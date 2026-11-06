# cogs/members.py
import traceback
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from typing import Optional

from core.config import (
    DEFAULT_TZ_OFFSET,
    GUILD_ID,
    ROFColors,
    RULES_CHANNEL_ID,
    WELCOME_CHANNEL_ID,
    format_dual_timestamps,
)
from core.database import db
from core.permissions import ensure_admin
from core.ui import rof_embed


# ==============================================================================
# HELPERS
# ==============================================================================

def _safe_tz_off() -> float:
    try:
        return float(db.get_config("game_tz_offset", str(DEFAULT_TZ_OFFSET)))
    except Exception as e:
        print(f"[MEMBERS] tz config read failed: {e}")
        return float(DEFAULT_TZ_OFFSET)


def _safe_config_int(key: str, default: int = 0) -> int:
    """fix A: DB read + int cast in one guarded call."""
    try:
        return int(db.get_config(key, str(default)) or default)
    except Exception as e:
        print(f"[MEMBERS] config '{key}' read/cast failed: {e}")
        return int(default)


def _parse_iso_utc(raw_value) -> Optional[datetime]:
    """fix J: normalize trailing `Z` and return None on malformed input."""
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
        print(f"[MEMBERS] invalid ISO datetime '{raw_value}': {e}")
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _safe_rules_text(fallback: str = "*No rules have been set yet.*") -> str:
    """fix B/G: never let rules rendering crash a caller."""
    try:
        return db.get_formatted_rules()
    except Exception as e:
        print(f"[MEMBERS] get_formatted_rules failed: {e}")
        return fallback


def load_rules() -> str:
    # fix I: safe accessor for legacy callers.
    return _safe_rules_text()


def save_rules(text: str, actor_id: int = 0):
    # fix I: intentionally propagates — caller must handle.
    db.replace_all_rules(text, actor_id=actor_id)


# ==============================================================================
# MODAL
# ==============================================================================

class RulesModal(discord.ui.Modal, title="Set ROF Alliance Rules"):
    rules_input = discord.ui.TextInput(
        label="Enter the alliance rules (one per line):",
        style=discord.TextStyle.paragraph,
        placeholder="Type your rules here, one rule per line.",
        min_length=5,
        max_length=4000,
        required=True,
    )

    def __init__(self):
        super().__init__()
        # fix D: guarded prefill.
        try:
            self.rules_input.default = db.get_formatted_rules()
        except Exception as e:
            print(f"[MEMBERS] RulesModal prefill failed: {e}")
            self.rules_input.default = ""

    async def on_submit(self, interaction: discord.Interaction):
        # fix E: guard the whole flow so the user always gets a response.
        try:
            if not await ensure_admin(interaction):
                return

            try:
                save_rules(self.rules_input.value, actor_id=interaction.user.id)
            except Exception as e:
                print(f"[MEMBERS] save_rules failed: {type(e).__name__}: {e}")
                traceback.print_exc()
                return await interaction.response.send_message(
                    "⚠️ Could not save the rules right now. Please try again.",
                    ephemeral=True,
                )

            # fix F: audit log is fire-and-forget.
            try:
                db.log_audit(
                    interaction.user.id,
                    "rules_replace",
                    "Replaced full alliance rules list via modal",
                )
            except Exception as e:
                print(f"[MEMBERS] log_audit failed (rules modal): {e}")

            await interaction.response.send_message(
                "✅ **Rules updated!** All new members will receive the updated rules in their welcome DM.",
                ephemeral=True,
            )
        except Exception as e:
            print(f"[MEMBERS] RulesModal.on_submit crashed: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⚠️ Could not update the rules right now.", ephemeral=True
                    )
            except Exception:
                pass


# ==============================================================================
# COG
# ==============================================================================

class Members(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- welcome rendering ----------

    def build_welcome_channel_embed(self, member: discord.Member) -> discord.Embed:
        return rof_embed(
            title="🛡️ WELCOME TO ROF!",
            description=(
                f"Welcome to the alliance, {member.mention}!\n"
                f"We're glad to have you here.\n\n"
                f"📬 Check your **Direct Messages** for alliance rules and a quick guide to using the ROF bot.\n"
                f"Have fun and enjoy the chaos! 🔥"
            ),
            color=ROFColors.GOLD,
            thumbnail_url=(
                member.display_avatar.url if hasattr(member, "display_avatar") else None
            ),
            footer_extra=f"Member: {member.display_name}",
        )

    def build_welcome_dm_embeds(self, member: discord.Member) -> list:
        """Build clean, readable onboarding embeds (Part 7.2 sections)."""
        # fix B: every external call is guarded with a sensible fallback.
        tz_off = _safe_tz_off()

        try:
            upcoming = db.get_upcoming_events()[:3] or []
        except Exception as e:
            print(f"[MEMBERS] get_upcoming_events failed (welcome DM): {e}")
            upcoming = []

        if upcoming:
            ev_lines = []
            for ev in upcoming:
                try:
                    dt = _parse_iso_utc(ev.get("start_time_utc"))
                    if dt is None:
                        continue
                    try:
                        dual = format_dual_timestamps(dt, tz_off)
                    except Exception as e:
                        print(f"[MEMBERS] format_dual_timestamps failed: {e}")
                        continue
                    ev_lines.append(
                        f"⚔️ **{ev.get('name', '?')}** — `{dual['game_time']}` | "
                        f"`{dual['india_time']}` ({dual['discord_relative']})"
                    )
                except Exception as e:
                    print(f"[MEMBERS] welcome event line render failed: {e}")
                    continue
            events_summary = (
                "\n".join(ev_lines)
                or "No upcoming events scheduled right now. Use `/events` anytime to check!"
            )
        else:
            events_summary = (
                "No upcoming events scheduled right now. Use `/events` anytime to check!"
            )

        rules_text = _safe_rules_text()

        embed_rules = rof_embed(
            title=f"🛡️ WELCOME TO ROF, {member.display_name.upper()}!",
            description=(
                "Welcome to the **Rise of Farkers (ROF)** alliance!\n"
                "We operate as a coordinated team across combat events, rallies, and our server gaming arena."
            ),
            color=ROFColors.GOLD,
            thumbnail_url=(
                member.display_avatar.url if hasattr(member, "display_avatar") else None
            ),
        )
        embed_rules.add_field(
            name="📜 Alliance Rules",
            value=rules_text,
            inline=False,
        )
        embed_rules.add_field(
            name="🌐 Important Alliance Information",
            value=(
                "• **Standard Game Time:** `UTC-02:00` (with automatic **India Time `IST`** conversion)\n"
                "• **Event Reminders:** Announced 10 minutes before launch\n"
                f"• **Upcoming Schedule:**\n{events_summary}"
            ),
            inline=False,
        )

        embed_guide = rof_embed(
            title="🎮 ROF BOT QUICK-START GUIDE",
            description="Here is how to get the most out of the ROF Discord Bot:",
            color=ROFColors.ARENA,
        )
        embed_guide.add_field(
            name="📅 How to View Events",
            value=(
                "Use `/events` in the server or type `events` here in DMs to see upcoming schedules "
                "in Game Time and India Time."
            ),
            inline=False,
        )
        embed_guide.add_field(
            name="🕹️ How to Play Games",
            value=(
                "Use `/games` to open the **ROF Gaming Arena**! Play solo games "
                "(Wordle, Quick Math, Trivia, Memory Challenge, Reaction Speed Test) "
                "or join multiplayer rooms (Four-Digit Codebreaker, Reaction Race, Trivia Battle, RPS)."
            ),
            inline=False,
        )
        embed_guide.add_field(
            name="🤖 How to Use the Alliance Assistant",
            value=(
                "Simply reply to this DM with any question (e.g., *\"When is the next Surge?\"* "
                "or *\"How do I play Codebreaker?\"*) and I will answer immediately!"
            ),
            inline=False,
        )
        embed_guide.add_field(
            name="⚡ Useful Commands",
            value="`/games` · `/events` · `/rules` · `/profile` · `/leaderboard` · `/help`",
            inline=False,
        )
        return [embed_rules, embed_guide]

    # ---------- listeners ----------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if GUILD_ID and member.guild.id != GUILD_ID:
            return

        # fix A: fully guarded config + channel resolution.
        welcome_chan_id = _safe_config_int(
            "welcome_channel_id", WELCOME_CHANNEL_ID or 0
        )

        welcome_channel = None
        if welcome_chan_id:
            try:
                welcome_channel = self.bot.get_channel(welcome_chan_id)
            except Exception as e:
                print(f"[MEMBERS] get_channel({welcome_chan_id}) failed: {e}")
                welcome_channel = None
        if welcome_channel is None:
            welcome_channel = getattr(member.guild, "system_channel", None)

        # fix K: fallback for DM-failure notification.
        notify_channel = welcome_channel or getattr(member.guild, "system_channel", None)

        # 1. Public welcome message
        if welcome_channel:
            try:
                await welcome_channel.send(
                    content=f"👋 Welcome {member.mention}!",
                    embed=self.build_welcome_channel_embed(member),
                )
            except Exception as e:
                print(f"[MEMBERS] Could not send public welcome message: {e}")

        # 2. Build DM embeds — separate build failure from send failure (fix C).
        try:
            dm_embeds = self.build_welcome_dm_embeds(member)
        except Exception as e:
            print(f"[MEMBERS] Failed to build onboarding DM for {member.id}: {e}")
            traceback.print_exc()
            dm_embeds = []

        if dm_embeds:
            sent_any = False
            hit_forbidden = False
            try:
                for emb in dm_embeds:
                    await member.send(embed=emb)
                    sent_any = True
            except discord.Forbidden:
                hit_forbidden = True
                print(
                    f"[MEMBERS] Member {member.id} ({member.name}) has DMs disabled. "
                    f"(sent_any={sent_any})"
                )
            except Exception as e:
                print(
                    f"[MEMBERS] Unexpected error sending DM to {member.id}: "
                    f"{type(e).__name__}: {e}"
                )

            # 3. Notify in channel only if we got Forbidden (DMs closed).
            # If partial delivery happened (sent_any=True) we still notify once,
            # because the member didn't receive the full guide.
            if hit_forbidden and notify_channel:
                rules_chan_id = _safe_config_int(
                    "rules_channel_id", RULES_CHANNEL_ID or 0
                )
                rules_ref = f"<#{rules_chan_id}>" if rules_chan_id else "`/rules`"
                try:
                    await notify_channel.send(
                        f"ℹ️ {member.mention}, your Direct Messages are closed so I couldn't "
                        f"DM your starter guide. Please check {rules_ref} and type `/help` "
                        f"to get started!"
                    )
                except Exception as e:
                    print(f"[MEMBERS] welcome-channel fallback failed: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if GUILD_ID and member.guild.id != GUILD_ID:
            return
        # fix H: guarded config + guarded wipe.
        try:
            wipe_flag = (db.get_config("wipe_stats_on_leave", "false") or "false").lower()
        except Exception as e:
            print(f"[MEMBERS] get_config(wipe_stats_on_leave) failed: {e}")
            wipe_flag = "false"

        if wipe_flag == "true":
            try:
                db.wipe_player_stats(member.id)
            except Exception as e:
                print(f"[MEMBERS] wipe_player_stats failed ({member.id}): {e}")

    # ---------- /rules COMMAND GROUP ----------

    rules_group = app_commands.Group(
        name="rules", description="View and manage official ROF Alliance rules"
    )

    @rules_group.command(name="view", description="View the official ROF Alliance rules")
    async def rules_view_cmd(self, interaction: discord.Interaction):
        embed = rof_embed(
            title="📜 ROF ALLIANCE RULES",
            description=_safe_rules_text(),
            color=ROFColors.ARENA,
        )
        await interaction.response.send_message(embed=embed)

    @rules_group.command(name="add", description="Add a new alliance rule (Admin/Owner only)")
    @app_commands.describe(rule_text="The text of the new rule to add")
    async def rules_add_cmd(self, interaction: discord.Interaction, rule_text: str):
        if not await ensure_admin(interaction):
            return
        # fix G: guarded DB write.
        try:
            num = db.add_rule(rule_text, actor_id=interaction.user.id)
        except Exception as e:
            print(f"[MEMBERS] add_rule failed: {type(e).__name__}: {e}")
            return await interaction.response.send_message(
                "⚠️ Could not add the rule right now.", ephemeral=True
            )
        # fix F: fire-and-forget audit.
        try:
            db.log_audit(
                interaction.user.id, "rule_add", f"Added Rule #{num}: {rule_text}"
            )
        except Exception as e:
            print(f"[MEMBERS] log_audit failed (rule add): {e}")

        embed = rof_embed(
            title="✅ RULE ADDED",
            description=(
                f"Added **Rule #{num}:** {rule_text}\n\n"
                f"**Updated Rules:**\n{_safe_rules_text()}"
            ),
            color=ROFColors.SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @rules_group.command(
        name="edit",
        description="Edit an existing rule by number or open full editor (Admin/Owner only)",
    )
    @app_commands.describe(
        rule_number="Optional rule number to edit (leave blank to open the full rules editor modal)",
        new_text="New text for the specified rule number",
    )
    async def rules_edit_cmd(
        self,
        interaction: discord.Interaction,
        rule_number: Optional[int] = None,
        new_text: Optional[str] = None,
    ):
        if not await ensure_admin(interaction):
            return
        if rule_number is None or not new_text:
            try:
                await interaction.response.send_modal(RulesModal())
            except Exception as e:
                print(f"[MEMBERS] send_modal failed (rules edit): {e}")
            return

        # fix G: guarded DB write.
        try:
            ok = db.edit_rule(rule_number, new_text, actor_id=interaction.user.id)
        except Exception as e:
            print(f"[MEMBERS] edit_rule failed: {type(e).__name__}: {e}")
            return await interaction.response.send_message(
                "⚠️ Could not edit the rule right now.", ephemeral=True
            )
        if not ok:
            return await interaction.response.send_message(
                f"❌ Rule `#{rule_number}` does not exist. Use `/rules view` to check rule numbers.",
                ephemeral=True,
            )
        try:
            db.log_audit(
                interaction.user.id,
                "rule_edit",
                f"Edited Rule #{rule_number}: {new_text}",
            )
        except Exception as e:
            print(f"[MEMBERS] log_audit failed (rule edit): {e}")

        embed = rof_embed(
            title="✅ RULE UPDATED",
            description=(
                f"Updated **Rule #{rule_number}**.\n\n"
                f"**Current Rules:**\n{_safe_rules_text()}"
            ),
            color=ROFColors.SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @rules_group.command(name="remove", description="Remove a rule by its number (Admin/Owner only)")
    @app_commands.describe(rule_number="The rule number to remove")
    async def rules_remove_cmd(self, interaction: discord.Interaction, rule_number: int):
        if not await ensure_admin(interaction):
            return
        # fix G: guarded DB write.
        try:
            ok = db.remove_rule(rule_number)
        except Exception as e:
            print(f"[MEMBERS] remove_rule failed: {type(e).__name__}: {e}")
            return await interaction.response.send_message(
                "⚠️ Could not remove the rule right now.", ephemeral=True
            )
        if not ok:
            return await interaction.response.send_message(
                f"❌ Rule `#{rule_number}` was not found.", ephemeral=True
            )
        try:
            db.log_audit(
                interaction.user.id, "rule_remove", f"Removed Rule #{rule_number}"
            )
        except Exception as e:
            print(f"[MEMBERS] log_audit failed (rule remove): {e}")

        embed = rof_embed(
            title="🗑️ RULE REMOVED",
            description=(
                f"Removed Rule `#{rule_number}` and re-numbered remaining rules.\n\n"
                f"{_safe_rules_text()}"
            ),
            color=ROFColors.WARNING,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ==============================================================================
# LEGACY /rof GROUP
# ==============================================================================

rof_group = app_commands.Group(name="rof", description="ROF Alliance Commands")


@rof_group.command(name="rules", description="View the ROF Alliance rules")
async def view_rules_legacy(interaction: discord.Interaction):
    # fix I: load_rules() already returns a fallback instead of raising.
    embed = rof_embed(
        title="📜 ROF ALLIANCE RULES",
        description=load_rules(),
        color=ROFColors.ARENA,
    )
    await interaction.response.send_message(embed=embed)


@rof_group.command(name="setrules", description="Set the ROF Alliance rules (Admin only)")
async def set_rules_legacy(interaction: discord.Interaction):
    if not await ensure_admin(interaction):
        return
    try:
        await interaction.response.send_modal(RulesModal())
    except Exception as e:
        print(f"[MEMBERS] send_modal failed (legacy setrules): {e}")


async def setup(bot: commands.Bot):
    if not bot.tree.get_command("rof"):
        bot.tree.add_command(rof_group)
    await bot.add_cog(Members(bot))