# cogs/arcade_core.py
import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from dotenv import load_dotenv

load_dotenv()
GUILD_ID = int(os.getenv("GUILD_ID"))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCADE_FILE = os.path.join(BASE_DIR, 'arcade_data.json')

RANKS = [
    (0, "Bronze", "🥉"),
    (100, "Silver", "🥈"),
    (250, "Gold", "🥇"),
    (500, "Diamond", "💎"),
    (1000, "ROF Legend", "👑")
]

def load_arcade():
    if os.path.exists(ARCADE_FILE):
        try:
            with open(ARCADE_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_arcade(data):
    with open(ARCADE_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_rank(points):
    current_rank = RANKS[0]
    for threshold, name, emoji in RANKS:
        if points >= threshold:
            current_rank = (name, emoji)
    return current_rank

class ArcadeCore(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = load_arcade()

    def _ensure_user(self, user_id):
        uid = str(user_id)
        if uid not in self.data:
            self.data[uid] = {
                "points": 0,
                "games_played": 0,
                "wins": 0,
                "game_stats": {}
            }
        return self.data[uid]

    def add_points(self, user_id, points, game_name, won=False):
        user = self._ensure_user(user_id)
        user["points"] += points
        user["games_played"] += 1
        if won:
            user["wins"] += 1
            
        if game_name not in user["game_stats"]:
            user["game_stats"][game_name] = {"played": 0, "won": 0}
            
        user["game_stats"][game_name]["played"] += 1
        if won:
            user["game_stats"][game_name]["won"] += 1
            
        save_arcade(self.data)
        return user["points"]

    @app_commands.command(name="arcade_profile", description="View your Arcade profile and rank")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def profile(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        user = self._ensure_user(target.id)
        
        rank_name, rank_emoji = get_rank(user["points"])
        
        embed = discord.Embed(
            title=f"{rank_emoji} {target.display_name}'s Arcade Profile",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Rank", value=f"**{rank_name}**", inline=True)
        embed.add_field(name="Points", value=f"**{user['points']}**", inline=True)
        embed.add_field(name="Win Rate", value=f"**{user['wins']}/{user['games_played']}**", inline=True)
        
        if user["game_stats"]:
            breakdown = ""
            for game, stats in user["game_stats"].items():
                breakdown += f"**{game}**: {stats['won']} wins / {stats['played']} played\n"
            embed.add_field(name="Game History", value=breakdown, inline=False)
        else:
            embed.add_field(name="Game History", value="No games played yet.", inline=False)
            
        next_rank = None
        for threshold, name, emoji in RANKS:
            if user["points"] < threshold:
                next_rank = (threshold, name)
                break
                
        if next_rank:
            pts_needed = next_rank[0] - user["points"]
            embed.set_footer(text=f"{pts_needed} points to reach {next_rank[1]}")
        else:
            embed.set_footer(text="You have reached the maximum rank!")
            
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="arcade_leaderboard", description="View the global ROF Arcade leaderboard")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def leaderboard(self, interaction: discord.Interaction):
        if not self.data:
            return await interaction.response.send_message("No one has played any games yet!", ephemeral=True)
            
        sorted_users = sorted(self.data.items(), key=lambda x: x[1]["points"], reverse=True)
        
        embed = discord.Embed(title="🏆 ROF Arcade — Global Leaderboard", color=discord.Color.gold())
        desc = ""
        
        for i, (uid, user) in enumerate(sorted_users[:10], 1):
            try:
                member = await self.bot.fetch_user(int(uid))
                name = member.display_name
            except:
                name = f"User {uid}"
                
            rank_name, rank_emoji = get_rank(user["points"])
            medal = {1: '🥇', 2: '🥈', 3: '🥉'}.get(i, f"`#{i}`")
            
            desc += f"{medal} **{name}** — {rank_emoji} {user['points']} pts ({rank_name})\n"
            
        embed.description = desc
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(ArcadeCore(bot))