# bot.py
import traceback
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from core.config import GUILD_ID, TOKEN
from core.database import db
from core.logger import log
from core.ui import install_global_ui_error_handlers, safe_reply_error

load_dotenv()

COGS_TO_LOAD = [
    "cogs.members",
    "cogs.events",
    "cogs.arcade_core",
    "cogs.wordle",
    "cogs.quickdraw",
    "cogs.codebreaker",
    "cogs.memory",
    "cogs.connect4",
    "cogs.singleplayer_games",
    "cogs.multiplayer_games",
    "cogs.fast_games",
    "cogs.launcher",
    "cogs.dm_handler",
    "cogs.admin",
]


class ROFBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        install_global_ui_error_handlers()
        for ext in COGS_TO_LOAD:
            try:
                await self.load_extension(ext)
                log.info("Loaded extension: %s", ext)
            except Exception as e:
                log.error("Failed loading %s: %s", ext, e)
                traceback.print_exc()

        self.tree.on_error = self.on_app_command_error

        try:
            if GUILD_ID:
                guild_obj = discord.Object(id=GUILD_ID)
                self.tree.clear_commands(guild=guild_obj)
                await self.tree.sync(guild=guild_obj)
            await self.tree.sync()
            log.info("Synced global slash commands (server + DM single-player enabled)")
        except Exception as e:
            log.warning("Command sync warning: %s", e)

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        cmd_name = getattr(interaction.command, "name", "unknown")
        if isinstance(error, app_commands.CommandOnCooldown):
            msg = f"⏳ Slow down! Try `/{cmd_name}` again in `{error.retry_after:.1f}s`."
        elif isinstance(error, app_commands.NoPrivateMessage):
            msg = f"🏟️ `/{cmd_name}` can only be used inside a server channel, not in DMs."
        elif isinstance(error, app_commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            msg = f"🔒 I'm missing required server permissions to run `/{cmd_name}`: `{missing}`."
        elif isinstance(error, (app_commands.MissingPermissions, app_commands.CheckFailure)):
            msg = f"🔒 You don't have permission to use `/{cmd_name}`."
        elif isinstance(error, app_commands.CommandNotFound):
            msg = "⚠️ That command is outdated or no longer exists. Try `/help` or `/games`."
        else:
            orig = getattr(error, "original", error)
            log.error("Command '/%s' failed: %s", cmd_name, orig)
            traceback.print_exception(type(orig), orig, orig.__traceback__)
            msg = f"⚠️ `/{cmd_name}` ran into an error and couldn't finish. Please try again in a moment."

        await safe_reply_error(interaction, msg)


bot = ROFBot()


@bot.event
async def on_ready():
    log.info("ROF Bot online: %s (DB: %s)", bot.user, db.db_path)


@bot.event
async def on_guild_join(guild: discord.Guild):
    if GUILD_ID and guild.id != GUILD_ID:
        await guild.leave()


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Missing DISCORD_TOKEN in .env")
    bot.run(TOKEN, log_handler=None)