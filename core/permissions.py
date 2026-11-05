# core/permissions.py
import discord
from core.config import OWNER_ID
from core.database import db


def is_owner_user(user_id: int) -> bool:
    return bool(OWNER_ID and int(user_id) == int(OWNER_ID))


def is_admin_interaction(interaction: discord.Interaction) -> bool:
    """Validate whether the caller is the Bot Owner or an Authorized Administrator."""
    if is_owner_user(interaction.user.id):
        return True
    role_ids = []
    if interaction.guild and hasattr(interaction.user, "guild_permissions"):
        if interaction.user.guild_permissions.administrator:
            return True
        if hasattr(interaction.user, "roles"):
            role_ids = [r.id for r in interaction.user.roles]
    return db.is_db_admin(interaction.user.id, role_ids)


async def ensure_owner(interaction: discord.Interaction) -> bool:
    if is_owner_user(interaction.user.id):
        return True
    msg = "🔒 Access Denied: Only the **ROF Bot Owner** can perform this action."
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)
    return False


async def ensure_admin(interaction: discord.Interaction) -> bool:
    if is_admin_interaction(interaction):
        return True
    msg = "🔒 Access Denied: Only **Authorized ROF Administrators** can perform this action."
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)
    return False


async def ensure_session_player(interaction: discord.Interaction, expected_user_id: int, action_label: str = "use this control") -> bool:
    if interaction.user.id == expected_user_id:
        return True
    msg = f"⚠️ You cannot {action_label} because this session belongs to <@{expected_user_id}>. Use `/games` to start your own session!"
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)
    return False
