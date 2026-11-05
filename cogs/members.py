# cogs/members.py
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


def load_rules() -> str:
    return db.get_formatted_rules()


def save_rules(text: str, actor_id: int = 0):
    db.replace_all_rules(text, actor_id=actor_id)


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
        self.rules_input.default = db.get_formatted_rules()

    async def on_submit(self, interaction: discord.Interaction):
        if not await ensure_admin(interaction):
            return
        save_rules(self.rules_input.value, actor_id=interaction.user.id)
        db.log_audit(interaction.user.id, "rules_replace", "Replaced full alliance rules list via modal")
        await interaction.response.send_message(
            "✅ **Rules updated!** All new members will receive the updated rules in their welcome DM.",
            ephemeral=True,
        )


class Members(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
            thumbnail_url=member.display_avatar.url if hasattr(member, "display_avatar") else None,
            footer_extra=f"Member: {member.display_name}",
        )

    def build_welcome_dm_embeds(self, member: discord.Member) -> list:
        """Build clean, readable onboarding embeds covering all 7 Part 7.2 sections."""
        tz_off = float(db.get_config("game_tz_offset", str(DEFAULT_TZ_OFFSET)))
        upcoming = db.get_upcoming_events()[:3]
        if upcoming:
            ev_lines = []
            for ev in upcoming:
                dt = datetime.fromisoformat(ev["start_time_utc"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dual = format_dual_timestamps(dt, tz_off)
                ev_lines.append(
                    f"⚔️ **{ev['name']}** — `{dual['game_time']}` | `{dual['india_time']}` ({dual['discord_relative']})"
                )
            events_summary = "\n".join(ev_lines)
        else:
            events_summary = "No upcoming events scheduled right now. Use `/events` anytime to check!"

        # Embed 1: Welcome Intro, Alliance Rules & Alliance Info
        embed_rules = rof_embed(
            title=f"🛡️ WELCOME TO ROF, {member.display_name.upper()}!",
            description=(
                "Welcome to the **Rise of Farkers (ROF)** alliance!\n"
                "We operate as a coordinated team across combat events, rallies, and our server gaming arena."
            ),
            color=ROFColors.GOLD,
            thumbnail_url=member.display_avatar.url if hasattr(member, "display_avatar") else None,
        )
        embed_rules.add_field(
            name="📜 Alliance Rules",
            value=db.get_formatted_rules(),
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

        # Embed 2: Quick Guide to Events, Games, AI Assistant & Useful Commands
        embed_guide = rof_embed(
            title="🎮 ROF BOT QUICK-START GUIDE",
            description="Here is how to get the most out of the ROF Discord Bot:",
            color=ROFColors.ARENA,
        )
        embed_guide.add_field(
            name="📅 How to View Events",
            value="Use `/events` in the server or type `events` here in DMs to see upcoming schedules in Game Time and India Time.",
            inline=False,
        )
        embed_guide.add_field(
            name="🕹️ How to Play Games",
            value=(
                "Use `/games` to open the **ROF Gaming Arena**! Play solo games (Wordle, Quick Math, Trivia, Memory Challenge, Reaction Speed Test) "
                "or join multiplayer rooms (Four-Digit Codebreaker, Reaction Race, Trivia Battle, RPS)."
            ),
            inline=False,
        )
        embed_guide.add_field(
            name="🤖 How to Use the Alliance Assistant",
            value="Simply reply to this DM with any question (e.g., *\"When is the next Surge?\"* or *\"How do I play Codebreaker?\"*) and I will answer immediately!",
            inline=False,
        )
        embed_guide.add_field(
            name="⚡ Useful Commands",
            value="`/games` · `/events` · `/rules` · `/profile` · `/leaderboard` · `/help`",
            inline=False,
        )
        return [embed_rules, embed_guide]

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if GUILD_ID and member.guild.id != GUILD_ID:
            return

        # 1. Send Public Welcome Channel Message (Part 7.1)
        welcome_chan_id = int(db.get_config("welcome_channel_id", str(WELCOME_CHANNEL_ID or 0)) or 0)
        welcome_channel = self.bot.get_channel(welcome_chan_id) if welcome_chan_id else member.guild.system_channel

        if welcome_channel:
            try:
                await welcome_channel.send(
                    content=f"👋 Welcome {member.mention}!",
                    embed=self.build_welcome_channel_embed(member),
                )
            except Exception as e:
                print(f"[WELCOME] Could not send public welcome message: {e}")

        # 2. Send Automatic Onboarding DM (Part 7.2) & Safe DM Failure Handling (Part 7.3)
        dm_embeds = self.build_welcome_dm_embeds(member)
        try:
            for emb in dm_embeds:
                await member.send(embed=emb)
        except discord.Forbidden:
            # Part 7.3: Do not retry; log safely; notify in welcome channel to check rules
            print(f"[WELCOME] Member {member.id} ({member.name}) has DMs disabled. Logged safely.")
            if welcome_channel:
                rules_chan_id = int(db.get_config("rules_channel_id", str(RULES_CHANNEL_ID or 0)) or 0)
                rules_ref = f"<#{rules_chan_id}>" if rules_chan_id else "`/rules`"
                try:
                    await welcome_channel.send(
                        f"ℹ️ {member.mention}, your Direct Messages are closed so I couldn't DM your starter guide. "
                        f"Please check {rules_ref} and type `/help` to get started!"
                    )
                except Exception:
                    pass
        except Exception as e:
            print(f"[WELCOME] Unexpected error sending DM to {member.id}: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if GUILD_ID and member.guild.id != GUILD_ID:
            return
        # Only wipe stats if explicitly enabled by admin in server_config
        if db.get_config("wipe_stats_on_leave", "false").lower() == "true":
            db.wipe_player_stats(member.id)

    # ---------- /rules COMMAND GROUP (Part 7.4: view, add, edit, remove) ----------

    rules_group = app_commands.Group(name="rules", description="View and manage official ROF Alliance rules")

    @rules_group.command(name="view", description="View the official ROF Alliance rules")
    async def rules_view_cmd(self, interaction: discord.Interaction):
        embed = rof_embed(
            title="📜 ROF ALLIANCE RULES",
            description=db.get_formatted_rules(),
            color=ROFColors.ARENA,
        )
        await interaction.response.send_message(embed=embed)

    @rules_group.command(name="add", description="Add a new alliance rule (Admin/Owner only)")
    @app_commands.describe(rule_text="The text of the new rule to add")
    async def rules_add_cmd(self, interaction: discord.Interaction, rule_text: str):
        if not await ensure_admin(interaction):
            return
        num = db.add_rule(rule_text, actor_id=interaction.user.id)
        db.log_audit(interaction.user.id, "rule_add", f"Added Rule #{num}: {rule_text}")
        embed = rof_embed(
            title="✅ RULE ADDED",
            description=f"Added **Rule #{num}:** {rule_text}\n\n**Updated Rules:**\n{db.get_formatted_rules()}",
            color=ROFColors.SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @rules_group.command(name="edit", description="Edit an existing rule by number or open full editor (Admin/Owner only)")
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
            return await interaction.response.send_modal(RulesModal())

        ok = db.edit_rule(rule_number, new_text, actor_id=interaction.user.id)
        if not ok:
            return await interaction.response.send_message(
                f"❌ Rule `#{rule_number}` does not exist. Use `/rules view` to check rule numbers.",
                ephemeral=True,
            )
        db.log_audit(interaction.user.id, "rule_edit", f"Edited Rule #{rule_number}: {new_text}")
        embed = rof_embed(
            title="✅ RULE UPDATED",
            description=f"Updated **Rule #{rule_number}**.\n\n**Current Rules:**\n{db.get_formatted_rules()}",
            color=ROFColors.SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @rules_group.command(name="remove", description="Remove a rule by its number (Admin/Owner only)")
    @app_commands.describe(rule_number="The rule number to remove")
    async def rules_remove_cmd(self, interaction: discord.Interaction, rule_number: int):
        if not await ensure_admin(interaction):
            return
        ok = db.remove_rule(rule_number)
        if not ok:
            return await interaction.response.send_message(
                f"❌ Rule `#{rule_number}` was not found.", ephemeral=True
            )
        db.log_audit(interaction.user.id, "rule_remove", f"Removed Rule #{rule_number}")
        embed = rof_embed(
            title="🗑️ RULE REMOVED",
            description=f"Removed Rule `#{rule_number}` and re-numbered remaining rules.\n\n{db.get_formatted_rules()}",
            color=ROFColors.WARNING,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# Preserved legacy /rof group (/rof rules, /rof setrules)
rof_group = app_commands.Group(name="rof", description="ROF Alliance Commands")


@rof_group.command(name="rules", description="View the ROF Alliance rules")
async def view_rules_legacy(interaction: discord.Interaction):
    embed = rof_embed(title="📜 ROF ALLIANCE RULES", description=load_rules(), color=ROFColors.ARENA)
    await interaction.response.send_message(embed=embed)


@rof_group.command(name="setrules", description="Set the ROF Alliance rules (Admin only)")
async def set_rules_legacy(interaction: discord.Interaction):
    if not await ensure_admin(interaction):
        return
    await interaction.response.send_modal(RulesModal())


async def setup(bot: commands.Bot):
    if not bot.tree.get_command("rof"):
        bot.tree.add_command(rof_group)
    await bot.add_cog(Members(bot))