# cogs/admin.py
import json
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from core.config import DEFAULT_TZ_OFFSET, OWNER_ID, ROFColors
from core.database import db
from core.permissions import ensure_admin, ensure_owner
from core.ui import rof_embed


class Admin(commands.Cog):
    """Part 9 & Part 11: Administration and Owner Security Controls (/admin settings|welcome|channels|permissions)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    admin_group = app_commands.Group(
        name="admin",
        description="ROF Administration, Channel Configuration, Welcome Setup, and Security Controls",
    )

    @admin_group.command(name="settings", description="Configure core ROF Bot settings (Admin/Owner only)")
    @app_commands.describe(
        game_tz_offset="Server Game Time UTC offset in hours (default: -2 for UTC-02:00)",
        default_reminder_minutes="Default event reminder minutes before start (default: 10)",
        wordle_open_to_all="Allow all alliance members to play Wordle (True/False)",
        wipe_stats_on_leave="Wipe player stats if they leave the Discord server (True/False)",
    )
    async def admin_settings_cmd(
        self,
        interaction: discord.Interaction,
        game_tz_offset: Optional[float] = None,
        default_reminder_minutes: Optional[int] = None,
        wordle_open_to_all: Optional[bool] = None,
        wipe_stats_on_leave: Optional[bool] = None,
    ):
        if not await ensure_admin(interaction):
            return

        changes = []
        if game_tz_offset is not None:
            if game_tz_offset < -12 or game_tz_offset > 14:
                return await interaction.response.send_message(
                    "❌ Invalid UTC offset (must be between -12 and +14).", ephemeral=True
                )
            db.set_config("game_tz_offset", str(game_tz_offset))
            changes.append(f"Game Timezone Offset → `UTC{game_tz_offset:+g}`")

        if default_reminder_minutes is not None:
            if default_reminder_minutes < 1 or default_reminder_minutes > 1440:
                return await interaction.response.send_message(
                    "❌ Default reminder minutes must be between 1 and 1440.", ephemeral=True
                )
            db.set_config("default_reminder_minutes", str(default_reminder_minutes))
            changes.append(f"Default Event Reminder → `{default_reminder_minutes} mins`")

        if wordle_open_to_all is not None:
            db.set_config("wordle_open_to_all", "true" if wordle_open_to_all else "false")
            changes.append(f"Wordle Open to All Members → `{wordle_open_to_all}`")

        if wipe_stats_on_leave is not None:
            db.set_config("wipe_stats_on_leave", "true" if wipe_stats_on_leave else "false")
            changes.append(f"Wipe Stats on Member Leave → `{wipe_stats_on_leave}`")

        if changes:
            db.log_audit(interaction.user.id, "admin_settings", "; ".join(changes))

        tz_val = db.get_config("game_tz_offset", str(DEFAULT_TZ_OFFSET))
        rem_val = db.get_config("default_reminder_minutes", "10")
        w_val = db.get_config("wordle_open_to_all", "true")
        wipe_val = db.get_config("wipe_stats_on_leave", "false")

        embed = rof_embed(
            title="⚙️ ROF ADMIN SETTINGS",
            description=(
                f"**Game Timezone Offset:** `UTC{float(tz_val):+g}` (India Time: `Asia/Kolkata`)\n"
                f"**Default Event Reminder:** `{rem_val} minutes before`\n"
                f"**Wordle Open to All Members:** `{w_val}`\n"
                f"**Wipe Player Stats on Leave:** `{wipe_val}`"
            ),
            color=ROFColors.ARENA,
        )
        if changes:
            embed.add_field(name="✅ Applied Changes", value="\n".join(f"• {c}" for c in changes), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @admin_group.command(name="channels", description="Configure Event, Welcome, Rules, and AI Assistant channels (Admin/Owner)")
    @app_commands.describe(
        event_channel="Channel where event announcements and 10-minute reminders are posted",
        welcome_channel="Channel where public welcome greetings are posted",
        rules_channel="Channel referenced when a new member has DMs disabled",
        assistant_channel="Toggle a channel for natural-language Alliance Assistant responses",
    )
    async def admin_channels_cmd(
        self,
        interaction: discord.Interaction,
        event_channel: Optional[discord.TextChannel] = None,
        welcome_channel: Optional[discord.TextChannel] = None,
        rules_channel: Optional[discord.TextChannel] = None,
        assistant_channel: Optional[discord.TextChannel] = None,
    ):
        if not await ensure_admin(interaction):
            return

        updates = []
        if event_channel:
            db.set_config("event_channel_id", str(event_channel.id))
            updates.append(f"Event Channel → {event_channel.mention}")
        if welcome_channel:
            db.set_config("welcome_channel_id", str(welcome_channel.id))
            updates.append(f"Welcome Channel → {welcome_channel.mention}")
        if rules_channel:
            db.set_config("rules_channel_id", str(rules_channel.id))
            updates.append(f"Rules Channel → {rules_channel.mention}")
        if assistant_channel:
            raw = db.get_config("assistant_channels", "[]")
            try:
                clist = [int(x) for x in json.loads(raw)]
            except Exception:
                clist = []
            if assistant_channel.id in clist:
                clist.remove(assistant_channel.id)
                updates.append(f"Assistant Channel Removed → {assistant_channel.mention}")
            else:
                clist.append(assistant_channel.id)
                updates.append(f"Assistant Channel Added → {assistant_channel.mention}")
            db.set_config("assistant_channels", json.dumps(clist))

        if updates:
            db.log_audit(interaction.user.id, "admin_channels", "; ".join(updates))

        ev_cid = int(db.get_config("event_channel_id", "0") or 0)
        wel_cid = int(db.get_config("welcome_channel_id", "0") or 0)
        rul_cid = int(db.get_config("rules_channel_id", "0") or 0)
        try:
            ai_cids = json.loads(db.get_config("assistant_channels", "[]"))
        except Exception:
            ai_cids = []

        embed = rof_embed(
            title="📡 ROF CONFIGURED CHANNELS",
            description=(
                f"**Event Announcements & Reminders:** {f'<#{ev_cid}>' if ev_cid else '*Not set*'}\n"
                f"**Welcome Channel:** {f'<#{wel_cid}>' if wel_cid else '*System Default*'}\n"
                f"**Rules Reference Channel:** {f'<#{rul_cid}>' if rul_cid else '*Uses /rules*'}\n"
                f"**AI Assistant Channels:** {', '.join(f'<#{c}>' for c in ai_cids) if ai_cids else '*DMs & @Mentions only*'}"
            ),
            color=ROFColors.ARENA,
        )
        if updates:
            embed.add_field(name="✅ Updated", value="\n".join(f"• {u}" for u in updates), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @admin_group.command(name="welcome", description="Test the Welcome Channel message and Onboarding DM (Admin/Owner)")
    @app_commands.describe(member="Optional member to preview onboarding for (defaults to you)")
    async def admin_welcome_cmd(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ):
        if not await ensure_admin(interaction):
            return
        target = member or interaction.user
        mem_cog = self.bot.get_cog("Members")
        if not mem_cog:
            return await interaction.response.send_message("❌ Members cog not loaded.", ephemeral=True)

        welcome_emb = mem_cog.build_welcome_channel_embed(target)
        dm_embeds = mem_cog.build_welcome_dm_embeds(target)
        await interaction.response.send_message(
            content="👁️ **Preview of Welcome Channel Embed + Onboarding DM Embeds:**",
            embeds=[welcome_emb] + dm_embeds,
            ephemeral=True,
        )

    @admin_group.command(
        name="permissions",
        description="Manage Authorized ROF Administrators, view Audit Logs, or create a DB Backup (Owner Only)",
    )
    @app_commands.describe(
        action="Choose what to manage (View Roster, Add/Remove Admin, View Audit Logs, Backup DB)",
        user="Optional user to grant/revoke ROF Administrator access",
        role="Optional role to grant/revoke ROF Administrator access",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="View Admin Roster & Recent Audit Logs", value="view"),
            app_commands.Choice(name="Add Authorized Admin (User or Role)", value="add"),
            app_commands.Choice(name="Remove Authorized Admin (User or Role)", value="remove"),
            app_commands.Choice(name="Create Database Backup", value="backup"),
        ]
    )
    async def admin_permissions_cmd(
        self,
        interaction: discord.Interaction,
        action: str = "view",
        user: Optional[discord.Member] = None,
        role: Optional[discord.Role] = None,
    ):
        # Part 9.1: Only the configured Bot Owner can manage administrators and security config
        if not await ensure_owner(interaction):
            return

        if action == "add":
            if not user and not role:
                return await interaction.response.send_message(
                    "⚠️ Specify either a `user` or `role` to grant ROF Administrator permissions.",
                    ephemeral=True,
                )
            if user:
                db.add_admin(user.id, "user", added_by=interaction.user.id)
                db.log_audit(interaction.user.id, "admin_grant_user", f"Granted admin to user {user.id}")
            if role:
                db.add_admin(role.id, "role", added_by=interaction.user.id)
                db.log_audit(interaction.user.id, "admin_grant_role", f"Granted admin to role {role.id}")
            return await interaction.response.send_message(
                "✅ Authorized administrator roster updated!", ephemeral=True
            )

        if action == "remove":
            if not user and not role:
                return await interaction.response.send_message(
                    "⚠️ Specify either a `user` or `role` to remove from ROF Administrators.",
                    ephemeral=True,
                )
            if user:
                db.remove_admin(user.id, "user")
                db.log_audit(interaction.user.id, "admin_revoke_user", f"Revoked admin from user {user.id}")
            if role:
                db.remove_admin(role.id, "role")
                db.log_audit(interaction.user.id, "admin_revoke_role", f"Revoked admin from role {role.id}")
            return await interaction.response.send_message(
                "✅ Removed from authorized administrator roster.", ephemeral=True
            )

        if action == "backup":
            dest = db.create_backup()
            db.log_audit(interaction.user.id, "db_backup", f"Created DB backup {dest}")
            return await interaction.response.send_message(
                f"💾 Database backup created safely (`{dest.split('/')[-1]}`).", ephemeral=True
            )

        admins = db.get_admins()
        admin_lines = [f"👑 **Bot Owner:** <@{OWNER_ID}> (`{OWNER_ID}`)"]
        for a in admins:
            if a["target_type"] == "role":
                admin_lines.append(f"🛡️ **Role:** <@&{a['target_id']}> (`{a['target_id']}`)")
            else:
                admin_lines.append(f"🛡️ **Admin:** <@{a['target_id']}> (`{a['target_id']}`)")

        logs = db.get_audit_logs(limit=8)
        log_lines = [
            f"• `{l['created_at']}` — <@{l['actor_id']}>: **{l['action']}** ({l['details']})"
            for l in logs
        ] or ["*No administrative actions logged yet.*"]

        embed = rof_embed(
            title="🔐 ROF SECURITY & PERMISSIONS CENTER",
            description="\n".join(admin_lines),
            color=ROFColors.GOLD,
        )
        embed.add_field(name="📋 Recent Administrative Audit Logs", value="\n".join(log_lines), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
