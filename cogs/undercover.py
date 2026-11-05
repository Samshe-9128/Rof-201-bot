# cogs/undercover.py
import discord
from discord import app_commands
from discord.ext import commands
import random
import os
from dotenv import load_dotenv

load_dotenv()
GUILD_ID = int(os.getenv("GUILD_ID"))

WORDS = [
    ("Apple", "Pear"), ("Cat", "Dog"), ("Car", "Truck"), ("Coffee", "Tea"),
    ("Sun", "Moon"), ("Pizza", "Burger"), ("Guitar", "Violin"), ("Beach", "Desert")
]

class UndercoverLobby(discord.ui.View):
    def __init__(self, cog, host):
        super().__init__(timeout=120)
        self.cog = cog
        self.host = host
        self.players = [host]

    def get_embed(self):
        desc = f"**Host:** {self.host.mention}\n\n**Players ({len(self.players)}/6):**\n"
        desc += "\n".join([f"• {p.mention}" for p in self.players])
        desc += "\n\n*Click Join to play! Need at least 3 players.*"
        return discord.Embed(title="🕵️ Undercover Lobby", description=desc, color=discord.Color.blue())

    @discord.ui.button(label="Join", style=discord.ButtonStyle.primary, emoji="✋")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in [p.id for p in self.players]:
            return await interaction.response.send_message("Already in lobby!", ephemeral=True)
        if len(self.players) >= 6:
            return await interaction.response.send_message("Lobby is full!", ephemeral=True)
        
        self.players.append(interaction.user)
        await interaction.response.edit_message(embed=self.get_embed())

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success, emoji="▶️")
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            return await interaction.response.send_message("Only the host can start!", ephemeral=True)
        if len(self.players) < 3:
            return await interaction.response.send_message("Need at least 3 players!", ephemeral=True)
        
        self.stop()
        await interaction.response.edit_message(embed=self.get_embed(), view=None)
        await self.cog.start_game(interaction.channel, self.players)

class UndercoverVote(discord.ui.View):
    def __init__(self, cog, players, spy):
        super().__init__(timeout=180)
        self.cog = cog
        self.players = players
        self.spy = spy
        self.votes = {}

        options = [discord.SelectOption(label=p.display_name, value=str(p.id)) for p in players]
        self.select = discord.ui.Select(placeholder="Who is the spy?", options=options)
        self.select.callback = self.vote_callback
        self.add_item(self.select)

    async def vote_callback(self, interaction: discord.Interaction):
        if interaction.user.id not in [p.id for p in self.players]:
            return await interaction.response.send_message("You are not playing!", ephemeral=True)
            
        self.votes[interaction.user.id] = int(self.select.values[0])
        await interaction.response.send_message("✅ Vote locked in!", ephemeral=True)

        if len(self.votes) == len(self.players):
            self.stop()
            await self.cog.tally_votes(interaction.channel, self.players, self.votes, self.spy)

class Undercover(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="undercover", description="Start a game of Who's the Spy (3-6 players)")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def undercover(self, interaction: discord.Interaction):
        view = UndercoverLobby(self, interaction.user)
        await interaction.response.send_message(embed=view.get_embed(), view=view)

    async def start_game(self, channel, players):
        pair = random.choice(WORDS)
        civilian_word, spy_word = pair
        spy = random.choice(players)

        # DM everyone
        failed_dms = []
        for p in players:
            try:
                word = spy_word if p.id == spy.id else civilian_word
                role = "SPY 🤫" if p.id == spy.id else "CIVILIAN 👤"
                await p.send(f"🕵️ **Undercover Started!**\nYour word is: **{word}**\nYour role: {role}\n\n*Describe your word in the channel without saying the word itself!*")
            except:
                failed_dms.append(p.mention)

        if failed_dms:
            return await channel.send(f"⚠️ Could not DM {', '.join(failed_dms)}. Please enable DMs from server members and try again.")

        embed = discord.Embed(
            title="🕵️ Undercover Started",
            description="Everyone has been DMed a secret word.\nOne of you is the Spy and got a slightly different word!\n\n**Take turns describing your word in the chat.**\nWhen ready, click the button below to vote.",
            color=discord.Color.orange()
        )
        view = StartVoteView(self, players, spy)
        await channel.send(embed=embed, view=view)

    async def tally_votes(self, channel, players, votes, spy):
        counts = {}
        for target_id in votes.values():
            counts[target_id] = counts.get(target_id, 0) + 1

        max_votes = max(counts.values())
        eliminated = [pid for pid, c in counts.items() if c == max_votes]

        # Handle tie
        eliminated_player = discord.utils.get(players, id=random.choice(eliminated))
        arcade = self.bot.get_cog("ArcadeCore")

        embed = discord.Embed(title="🔍 Voting Results", color=discord.Color.red())
        
        if eliminated_player.id == spy.id:
            embed.description = f"🎯 **Correct!** {eliminated_player.mention} was the Spy!\nThe words were: Civilian = `{WORDS[0][0]}`, Spy = `{WORDS[0][1]}` (or similar pair)"
            embed.color = discord.Color.green()
            if arcade:
                for p in players:
                    if p.id != spy.id:
                        arcade.add_points(p.id, 30, "Undercover", won=True)
        else:
            embed.description = f"❌ **Wrong!** {eliminated_player.mention} was innocent.\nThe Spy was actually {spy.mention}!"
            if arcade:
                arcade.add_points(spy.id, 50, "Undercover", won=True)

        await channel.send(embed=embed)

class StartVoteView(discord.ui.View):
    def __init__(self, cog, players, spy):
        super().__init__(timeout=None)
        self.cog = cog
        self.players = players
        self.spy = spy

    @discord.ui.button(label="Start Voting", style=discord.ButtonStyle.danger, emoji="🗳️")
    async def vote_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [p.id for p in self.players]:
            return await interaction.response.send_message("You are not playing!", ephemeral=True)
        
        self.stop()
        await interaction.response.edit_message(embed=discord.Embed(title="🗳️ Voting Started", description="Check the dropdown below to cast your vote!", color=discord.Color.dark_red()), view=None)
        
        vote_view = UndercoverVote(self.cog, self.players, self.spy)
        await interaction.channel.send("Cast your votes below:", view=vote_view)

async def setup(bot):
    await bot.add_cog(Undercover(bot))