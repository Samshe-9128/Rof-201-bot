# bot.py
import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
GUILD = discord.Object(id=GUILD_ID)

class ROFBot(commands.Bot):
    async def setup_hook(self):
        await self.load_extension("cogs.members")
        await self.load_extension("cogs.events")
        await self.load_extension("cogs.arcade_core")
        await self.load_extension("cogs.wordle")
        await self.load_extension("cogs.quickdraw")
        await self.load_extension("cogs.codebreaker") # <-- ADD
        await self.load_extension("cogs.undercover") 

        await self.load_extension("cogs.memory") 
        # Sync globally (allows commands to appear in DMs)
        await self.tree.sync()
        
        # Also sync to your guild for instant updates in the server
        self.tree.copy_global_to(guild=GUILD)
        await self.tree.sync(guild=GUILD)


intents = discord.Intents.default()
intents.message_content = True
intents.members = True # Required for Welcome DMs and leave tracking!
bot = ROFBot(command_prefix="!", intents=intents)

bot = ROFBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ ROF Bot online: {bot.user}")

@bot.event
async def on_guild_join(guild):
    if guild.id != GUILD_ID:
        await guild.leave()

if not TOKEN:
    raise RuntimeError("Missing Discord token in .env")

bot.run(TOKEN)