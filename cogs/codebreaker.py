# cogs/codebreaker.py
import discord
from discord import app_commands
from discord.ext import commands
import os
import random
from dotenv import load_dotenv

load_dotenv()
GUILD_ID = int(os.getenv("GUILD_ID"))

class SetCodeModal(discord.ui.Modal, title="Set the Secret Code"):
    code = discord.ui.TextInput(
        label="Enter a 4-digit code (numbers 1-6 only)",
        placeholder="e.g., 1234",
        min_length=4,
        max_length=4
    )

    def __init__(self, cog, challenger, opponent):
        super().__init__()
        self.cog = cog
        self.challenger = challenger
        self.opponent = opponent

    async def on_submit(self, interaction: discord.Interaction):
        code = self.code.value
        if not code.isdigit() or any(c not in '123456' for c in code):
            return await interaction.response.send_message("❌ Invalid code! Use only numbers 1-6.", ephemeral=True)

        view = CodebreakerGameView(self.cog, self.challenger, self.opponent, code)
        await interaction.response.send_message(f"✅ Code set! {self.opponent.mention}, your turn to guess.", embed=view.get_embed(), view=view)

class GuessModal(discord.ui.Modal, title="Guess the Code"):
    guess = discord.ui.TextInput(
        label="Enter your 4-digit guess (1-6)",
        min_length=4,
        max_length=4
    )

    def __init__(self, view):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.opponent.id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        await self.view.process_guess(interaction, self.guess.value)

class CodebreakerGameView(discord.ui.View):
    def __init__(self, cog, challenger, opponent, secret_code):
        super().__init__(timeout=600)
        self.cog = cog
        self.challenger = challenger
        self.opponent = opponent
        self.secret_code = list(secret_code)
        self.guesses = []
        self.won = False

    @discord.ui.button(label="Make a Guess", style=discord.ButtonStyle.primary, emoji="🔍")
    async def guess_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message("Only the guesser can use this button!", ephemeral=True)
        await interaction.response.send_modal(GuessModal(self))

    def get_embed(self):
        embed = discord.Embed(title="🔐 Codebreaker", color=discord.Color.dark_purple())
        embed.description = f"**{self.opponent.mention}** is trying to crack **{self.challenger.mention}**'s code!\n" \
                            f"🟩 = Right number, right spot\n🟨 = Right number, wrong spot\n⬛ = Wrong number\n\n"
        
        board = ""
        for g in self.guesses:
            board += f"`{g['guess']}`  ➔  {g['result']}\n"
            
        if not board: board = "*No guesses yet.*"
        embed.add_field(name=f"Guesses ({len(self.guesses)}/10)", value=board, inline=False)
        return embed

    async def process_guess(self, interaction, guess_str):
        if not guess_str.isdigit() or any(c not in '123456' for c in guess_str):
            return await interaction.response.send_message("❌ Invalid guess! Use only numbers 1-6.", ephemeral=True)

        guess = list(guess_str)
        secret_copy = self.secret_code.copy()
        result = []

        # Check greens
        for i in range(4):
            if guess[i] == secret_copy[i]:
                result.append("🟩")
                secret_copy[i] = "X"
                guess[i] = "Y"

        # Check yellows
        for i in range(4):
            if guess[i] != "Y" and guess[i] in secret_copy:
                result.append("🟨")
                secret_copy[secret_copy.index(guess[i])] = "X"

        # Fill blacks
        while len(result) < 4:
            result.append("⬛")

        random.shuffle(result) # Shuffle so they don't know which is which
        self.guesses.append({"guess": guess_str, "result": " ".join(result)})

        if guess_str == "".join(self.secret_code):
            self.won = True
            self.stop()
            await self.end_game(interaction)
        elif len(self.guesses) >= 10:
            self.stop()
            await self.end_game(interaction)
        else:
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def end_game(self, interaction):
        for child in self.children: child.disabled = True
        embed = self.get_embed()
        arcade = self.cog.bot.get_cog("ArcadeCore")

        if self.won:
            embed.color = discord.Color.green()
            embed.add_field(name="Result", value=f"🏆 **{self.opponent.mention} cracked the code!**", inline=False)
            if arcade:
                arcade.add_points(self.opponent.id, 50, "Codebreaker", won=True)
                arcade.add_points(self.challenger.id, 10, "Codebreaker", won=False)
        else:
            embed.color = discord.Color.red()
            embed.add_field(name="Result", value=f"❌ **Out of guesses!** The code was `{''.join(self.secret_code)}`", inline=False)
            if arcade:
                arcade.add_points(self.challenger.id, 40, "Codebreaker", won=True)
                arcade.add_points(self.opponent.id, 10, "Codebreaker", won=False)

        await interaction.response.edit_message(embed=embed, view=self)

class Codebreaker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="codebreaker", description="Challenge someone to crack your secret code")
    @app_commands.describe(opponent="The member who will guess your code")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def codebreaker(self, interaction: discord.Interaction, opponent: discord.Member):
        if opponent.bot or opponent.id == interaction.user.id:
            return await interaction.response.send_message("Invalid opponent.", ephemeral=True)
        
        await interaction.response.send_modal(SetCodeModal(self, interaction.user, opponent))

async def setup(bot):
    await bot.add_cog(Codebreaker(bot))