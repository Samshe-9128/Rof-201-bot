# cogs/memory.py
import discord
from discord import app_commands
from discord.ext import commands
import random
import os
import asyncio
import time
from dotenv import load_dotenv

load_dotenv()

EMOJIS = ["🐶", "🐱", "🦊", "🐻", "🐼", "🐨", "🦁", "🐸", "🐵", "🐔", "🐧", "🦆"]

# ---------- SCREEN 1: THE LOBBY ----------
class MemoryLobby(discord.ui.View):
    def __init__(self, cog, user):
        super().__init__(timeout=120)
        self.cog = cog
        self.user = user

    def get_embed(self):
        embed = discord.Embed(
            title="🧠 ROF Memory Match",
            description="Test your memory against the clock!\n\n"
                        "**How to play:**\n"
                        "1. Click Play Game.\n"
                        "2. You will have **3 seconds** to memorize the board.\n"
                        "3. The cards will flip over. Match all the pairs to win Arcade Points!\n\n"
                        "**Rules:**\n"
                        "• You have 10 games per hour.\n"
                        "• Fewer moves = More points.",
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Player: {self.user.display_name}")
        return embed

    @discord.ui.button(label="Play Game", style=discord.ButtonStyle.success, emoji="▶️")
    async def play_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This isn't your lobby!", ephemeral=True)
            
        uid = str(interaction.user.id)
        now = time.time()
        history = [t for t in self.cog.play_history.get(uid, []) if now - t < 3600]
        
        if len(history) >= 10:
            return await interaction.response.send_message(
                "⏳ **Slow down!** You have played 10 games this hour. Take a break and come back later.", 
                ephemeral=True
            )
            
        history.append(now)
        self.cog.play_history[uid] = history

        # Create the game view
        game_view = MemoryGameView(self.cog, self.user, "easy", preview=True)
        
        # Instantly transition to the memorize phase
        await interaction.response.edit_message(embed=game_view.get_embed(preview=True), view=game_view)
        
        # Run the 3-second timer
        await asyncio.sleep(3.0)
        
        # Hide all cards
        for child in game_view.children:
            if isinstance(child, discord.ui.Button):
                child.label = "❓"
                child.style = discord.ButtonStyle.secondary
                child.disabled = False

        game_view.is_locked = False
        
        # Update to the playable board
        try:
            await interaction.edit_original_response(embed=game_view.get_embed(preview=False), view=game_view)
        except discord.NotFound:
            pass


# ---------- SCREEN 2 & 3: THE GAME & MEMORIZE ----------
class MemoryGameView(discord.ui.View):
    def __init__(self, cog, user, difficulty, preview=False):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self.difficulty = difficulty
        self.moves = 0
        self.matches = 0
        
        self.pairs = 8
        self.cols = 4
        self.total_cards = 16
        
        deck = EMOJIS[:self.pairs] * 2
        random.shuffle(deck)
        
        self.cards = deck
        self.revealed = []
        self.matched = set()
        self.is_locked = True

        # Create the grid
        for i in range(self.total_cards):
            btn = discord.ui.Button(label="❓", style=discord.ButtonStyle.secondary, custom_id=f"card_{i}", row=i // self.cols)
            if preview:
                btn.label = self.cards[i]
                btn.style = discord.ButtonStyle.primary
                btn.disabled = True
            btn.callback = self.make_callback(i)
            self.add_item(btn)

    def get_embed(self, preview=False):
        if preview:
            title = "🧠 Memorize the Board!"
            desc = "**You have 3 seconds to memorize the emojis!**\nStudy the board carefully..."
            color = discord.Color.orange()
        else:
            title = "🧠 Memory Match"
            desc = f"Find all {self.pairs} pairs!\n\n**Moves:** {self.moves}\n**Matches:** {self.matches}/{self.pairs}"
            color = discord.Color.purple()
            
        embed = discord.Embed(title=title, description=desc, color=color)
        embed.set_footer(text=f"Player: {self.user.display_name} | Private Game")
        return embed

    def make_callback(self, index):
        async def callback(interaction: discord.Interaction):
            # Bulletproof error handling for Discord API glitches
            try:
                if interaction.user.id != self.user.id:
                    return await interaction.response.send_message("This isn't your game!", ephemeral=True)
                
                if self.is_locked or index in self.matched or index in self.revealed:
                    return await interaction.response.defer()

                self.revealed.append(index)
                
                # Flip the card visually
                for child in self.children:
                    if isinstance(child, discord.ui.Button) and child.custom_id == f"card_{index}":
                        child.label = self.cards[index]
                        child.style = discord.ButtonStyle.primary
                        child.disabled = True

                if len(self.revealed) == 2:
                    self.moves += 1
                    idx1, idx2 = self.revealed
                    
                    if self.cards[idx1] == self.cards[idx2]:
                        # MATCH FOUND!
                        self.matched.add(idx1)
                        self.matched.add(idx2)
                        self.revealed = []
                        
                        for child in self.children:
                            if isinstance(child, discord.ui.Button) and child.custom_id in [f"card_{idx1}", f"card_{idx2}"]:
                                child.style = discord.ButtonStyle.success
                        
                        self.matches += 1
                        
                        if self.matches == self.pairs:
                            self.stop()
                            await self.end_game(interaction)
                        else:
                            await interaction.response.edit_message(embed=self.get_embed(), view=self)
                    else:
                        # NO MATCH
                        self.is_locked = True
                        await interaction.response.edit_message(embed=self.get_embed(), view=self)
                        await asyncio.sleep(1.0)
                        
                        for child in self.children:
                            if isinstance(child, discord.ui.Button) and child.custom_id in [f"card_{idx1}", f"card_{idx2}"]:
                                child.label = "❓"
                                child.style = discord.ButtonStyle.secondary
                                child.disabled = False
                        
                        self.revealed = []
                        self.is_locked = False
                        
                        try:
                            await interaction.edit_original_response(embed=self.get_embed(), view=self)
                        except discord.NotFound:
                            pass
                else:
                    # First card flipped
                    await interaction.response.edit_message(embed=self.get_embed(), view=self)
            
            except discord.NotFound:
                pass # Message was deleted, safely ignore
            except Exception as e:
                print(f"Memory Game Error: {e}") # Logs any other errors to console

        return callback

    # ---------- SCREEN 4: THE RESULT ----------
    async def end_game(self, interaction):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
            
        points = max(10, 50 - (self.moves * 3))
        
        embed = self.get_embed()
        embed.color = discord.Color.gold()
        embed.title = "🏆 Memory Match — Complete!"
        embed.description = f"You cleared the board in **{self.moves} moves**!"
        embed.add_field(name="Points Earned", value=f"**+{points} Arcade Points**", inline=False)
        
        arcade = self.cog.bot.get_cog("ArcadeCore")
        if arcade:
            arcade.add_points(self.user.id, points, "Memory Match", won=True)
            
        view = PlayAgainView(self.cog, self.user)
        try:
            await interaction.response.edit_message(embed=embed, view=view)
        except discord.NotFound:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


# ---------- PLAY AGAIN BUTTON ----------
class PlayAgainView(discord.ui.View):
    def __init__(self, cog, user):
        super().__init__(timeout=60)
        self.cog = cog
        self.user = user

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.success, emoji="🔄")
    async def play_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
            
        lobby = MemoryLobby(self.cog, self.user)
        await interaction.response.edit_message(embed=lobby.get_embed(), view=lobby)


class Memory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.play_history = {}

    @app_commands.command(name="memory", description="Play a private game of Emoji Memory Match")
    async def memory(self, interaction: discord.Interaction):
        lobby = MemoryLobby(self, interaction.user)
        await interaction.response.send_message(embed=lobby.get_embed(), view=lobby, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Memory(bot))