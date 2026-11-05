# bot.py
import os
import traceback
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from core.config import GUILD_ID, TOKEN
from core.database import db

load_dotenv()

COGS_TO_LOAD = [
    "cogs.members",
    "cogs.events",
    "cogs.arcade_core",
    "cogs.wordle",
    "cogs.quickdraw",
    "cogs.codebreaker",
    "cogs.undercover",
    "cogs.memory",
    "cogs.connect4",
    "cogs.singleplayer_games",
    "cogs.multiplayer_games",
    "cogs.launcher",
    "cogs.dm_handler",
    "cogs.admin",
]


class ROFBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Load all ROF extensions
        for ext in COGS_TO_LOAD:
            try:
                await self.load_extension(ext)
                print(f"[BOOT] Loaded extension: {ext}")
            except Exception as e:
                print(f"[BOOT] Error loading {ext}: {e}")
                traceback.print_exc()

        # Attach safe global application command error handler (Part 12: never expose stack traces/secrets)
        self.tree.on_error = self.on_app_command_error

        # Sync commands cleanly without duplicating global + guild commands
        try:
            if GUILD_ID:
                guild_obj = discord.Object(id=GUILD_ID)
                self.tree.copy_global_to(guild=guild_obj)
                await self.tree.sync(guild=guild_obj)
                print(f"[BOOT] Synced commands to guild {GUILD_ID}")
            else:
                await self.tree.sync()
                print("[BOOT] Synced global commands")
        except Exception as e:
            print(f"[BOOT] Command sync warning: {e}")

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        print(f"[ERROR] Command '{ getattr(interaction.command, 'name', 'unknown') }' failed: {error}")
        traceback.print_exc()
        safe_msg = "⚠️ Something went wrong while processing that action. Please try again in a moment."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(safe_msg, ephemeral=True)
            else:
                await interaction.response.send_message(safe_msg, ephemeral=True)
        except Exception:
            pass


bot = ROFBot()


@bot.event
async def on_ready():
    print(f"✅ ROF Bot online: {bot.user} (Database initialized at {db.db_path})")


@bot.event
async def on_guild_join(guild: discord.Guild):
    if GUILD_ID and guild.id != GUILD_ID:
        await guild.leave()


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Missing DISCORD_TOKEN in .env")
    bot.run(TOKEN)