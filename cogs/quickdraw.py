# cogs/quickdraw.py
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import random
import time
import os
from dotenv import load_dotenv

load_dotenv()
GUILD_ID = int(os.getenv("GUILD_ID"))

class DrawView(discord.ui.View):
    def __init__(self, cog, players):
        super().__init__(timeout=15) # 15 seconds to click
        self.cog = cog
        self.players = players
        self.winner = None
        self.start_time = time.time()

    @discord.ui.button(label="🔥 FIRE 🔥", style=discord.ButtonStyle.danger)
    async def fire_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.players:
            await interaction.response.send_message("You are not in this duel!", ephemeral=True)
            return

        if self.winner is not None:
            await interaction.response.send_message("Too late, someone else already fired!", ephemeral=True)
            return

        # Record the winner
        self.winner = interaction.user
        self.stop() # Stop the view
        
        # Calculate reaction time
        reaction = round(time.time() - self.start_time, 3)
        
        await interaction.response.defer()
        await self.cog.process_winner(interaction, self.players, self.winner, reaction)

class LobbyView(discord.ui.View):
    def __init__(self, cog, host):
        super().__init__(timeout=60)
        self.cog = cog
        self.host = host
        self.players = [host]

    @discord.ui.button(label="Join Duel", style=discord.ButtonStyle.primary)
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.players:
            await interaction.response.send_message("You are already in the lobby!", ephemeral=True)
            return

        if len(self.players) >= 3:
            await interaction.response.send_message("Lobby is full (max 3 players)!", ephemeral=True)
            return

        self.players.append(interaction.user)
        await interaction.response.send_message(f"✅ {interaction.user.mention} joined the duel!", ephemeral=False)
        
        # Update the lobby embed
        embed = discord.Embed(
            title="⚔️ Quick Draw Lobby",
            description=f"Host: {self.host.mention}\n\n**Players ({len(self.players)}/3):**\n" + "\n".join([f"• {p.mention}" for p in self.players]),
            color=discord.Color.blue()
        )
        await interaction.message.edit(embed=embed)

    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.success)
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            await interaction.response.send_message("Only the host can start the game!", ephemeral=True)
            return
            
        if len(self.players) < 2:
            await interaction.response.send_message("You need at least 2 players to start!", ephemeral=True)
            return

        self.stop()
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        
        await self.cog.start_duel(interaction, self.players)

class QuickDraw(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="quickdraw", description="Start a Quick Draw reflex duel (2-3 players)")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def quickdraw(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚔️ Quick Draw Lobby",
            description=f"Host: {interaction.user.mention}\n\n**Players (1/3):**\n• {interaction.user.mention}\n\n*Waiting for players...*",
            color=discord.Color.blue()
        )
        view = LobbyView(self, interaction.user)
        await interaction.response.send_message(embed=embed, view=view)

    async def start_duel(self, interaction: discord.Interaction, players):
        channel = interaction.channel
        
        # 1. The Setup
        embed = discord.Embed(
            title="🔫 Prepare to Draw...",
            description="Wait for the signal...\n\n*If you click FIRE before the signal, you lose!*",
            color=discord.Color.dark_gray()
        )
        msg = await channel.send(embed=embed)
        
        # 2. The Random Delay (2 to 6 seconds)
        await asyncio.sleep(random.uniform(2.0, 6.0))
        
        # 3. The Signal
        draw_embed = discord.Embed(
            title="🔥 DRAW! 🔥",
            description="Click the button as fast as you can!",
            color=discord.Color.red()
        )
        view = DrawView(self, [p.id for p in players])
        await msg.edit(embed=draw_embed, view=view)
        
        # Wait for someone to click (or timeout)
        await view.wait()
        
        if view.winner is None:
            timeout_embed = discord.Embed(
                title="💤 Too Slow!",
                description="Nobody clicked the button in time. The duel is a draw!",
                color=discord.Color.light_gray()
            )
            await msg.edit(embed=timeout_embed, view=None)

    async def process_winner(self, interaction: discord.Interaction, players, winner, reaction):
        arcade = self.bot.get_cog("ArcadeCore")
        
        # Award points
        if arcade:
            for pid in players:
                if pid == winner.id:
                    arcade.add_points(pid, 40, "Quick Draw", won=True)
                else:
                    arcade.add_points(pid, 10, "Quick Draw", won=False)

        embed = discord.Embed(
            title="🏆 Duel Over!",
            description=f"**{winner.mention}** was the fastest!\n\n⏱️ Reaction time: **{reaction} seconds**",
            color=discord.Color.gold()
        )
        
        # Find the message and remove the view
        msg = interaction.message
        await msg.edit(embed=embed, view=None)

async def setup(bot):
    await bot.add_cog(QuickDraw(bot))