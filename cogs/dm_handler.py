# cogs/dm_handler.py
import discord
from discord.ext import commands
import json
import os
import random
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

GUILD_ID = int(os.getenv("GUILD_ID"))
TZ_OFFSET = float(os.getenv("SERVER_TZ_OFFSET", "-2"))
SERVER_TZ = timezone(timedelta(hours=TZ_OFFSET))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_FILE = os.path.join(BASE_DIR, 'rules.json')
EVENTS_FILE = os.path.join(BASE_DIR, 'events.json')

class DMHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_rules(self):
        if os.path.exists(RULES_FILE):
            try:
                with open(RULES_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f).get("rules", "No rules have been set yet.")
            except:
                pass
        return "Rules are currently being updated."

    def get_events(self):
        if os.path.exists(EVENTS_FILE):
            try:
                with open(EVENTS_FILE, 'r') as f:
                    events = json.load(f)
                now = datetime.now(SERVER_TZ)
                upcoming = [e for e in events if datetime.fromisoformat(e["time"]) > now]
                upcoming.sort(key=lambda x: x["time"])
                
                if not upcoming:
                    return "No upcoming events scheduled right now. ⚔️"
                
                text = ""
                for e in upcoming[:3]:
                    dt = datetime.fromisoformat(e["time"])
                    text += f"⚔️ **{e['name']}**\n🕒 <t:{int(dt.timestamp())}:F> (<t:{int(dt.timestamp())}:R>)\n\n"
                return text
            except:
                pass
        return "Unable to load events."

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore bots and server messages
        if message.author.bot or message.guild is not None:
            return

        content = message.content.lower().strip()

        # 1. Greetings
        if any(word in content for word in ["hi", "hello", "hey", "yo", "hola"]):
            greetings = [
                f"Hello {message.author.name}! 🛡️ Welcome to the ROF bot DMs. How can I help you today?",
                f"Hey there, {message.author.name}! Ready to play some games or check the events?",
                f"Greetings, warrior! ⚔️ What do you need? Type `/help` to see my commands."
            ]
            await message.channel.send(random.choice(greetings))

        # 2. Rules
        elif "rule" in content:
            embed = discord.Embed(title="📜 ROF Alliance Rules", description=self.get_rules(), color=discord.Color.blue())
            await message.channel.send(embed=embed)

        # 3. Events
        elif "event" in content or "schedule" in content:
            embed = discord.Embed(title="📅 Upcoming ROF Events", description=self.get_events(), color=discord.Color.gold())
            await message.channel.send(embed=embed)

        # 4. Games
        elif "game" in content or "play" in content:
            await message.channel.send(
                "🎮 **Here are the games you can play with me right now in DMs:**\n"
                "• `/wordle` — Today's daily word\n"
                "• `/wordle_practice` — Unlimited practice\n"
                "• `/memory` — Emoji memory match\n"
                "• `/2048` — The classic tile game\n\n"
                "For multiplayer games (Connect 4, Quick Draw), please use the commands inside the ROF server!"
            )

        # 5. Help Menu
        elif "help" in content or "command" in content:
            embed = discord.Embed(
                title="🛡️ ROF Bot Commands",
                description="Here is what I can do:\n\n"
                            "**🎮 Games:** `/wordle`, `/memory`, `/2048`\n"
                            "**📊 Stats:** `/arcade_profile`, `/arcade_leaderboard`\n"
                            "**📜 Rules:** Type 'rules' to see them here\n"
                            "**📅 Events:** Type 'events' to see them here",
                color=discord.Color.purple()
            )
            await message.channel.send(embed=embed)

        # 6. Fallback for anything else
        else:
            embed = discord.Embed(
                title="🤖 I'm here to help!",
                description="I am a private bot for the ROF Alliance. I may not understand everything you say, but here are things you can ask me:\n\n"
                            "👉 'rules'\n"
                            "👉 'events'\n"
                            "👉 'games'\n"
                            "👉 'help'\n\n"
                            "*Or just type `/` to see all my slash commands.*",
                color=discord.Color.light_grey()
            )
            await message.channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(DMHandler(bot))