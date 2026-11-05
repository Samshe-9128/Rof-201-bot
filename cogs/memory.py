# cogs/memory.py
import asyncio
import random
import time
import discord
from discord import app_commands
from discord.ext import commands
from typing import List

from core.config import ROFColors
from core.database import db
from core.permissions import ensure_session_player
from core.ui import GameResultView, rof_embed

EMOJIS = ["🐶", "🐱", "🦊", "🐻", "🐼", "🐨", "🦁", "🐸", "🐵", "🐔", "🐧", "🦆"]
SEQUENCE_PALETTE = [
    ("🔴", "Red"),
    ("🔵", "Blue"),
    ("🟢", "Green"),
    ("🟡", "Yellow"),
    ("🟣", "Purple"),
    ("🟠", "Orange"),
]


# ==============================================================================
# PART 2.2 GAME 3: MEMORY CHALLENGE (SEQUENCE REPRODUCTION)
# ==============================================================================

class SequenceMemoryView(discord.ui.View):
    """Progressive sequence memory game: memorize 🔴 🔵 🟢 🟡 and reproduce it."""

    def __init__(self, cog: "Memory", user: discord.abc.User, level: int = 1, score: int = 0):
        super().__init__(timeout=180.0)
        self.cog = cog
        self.user = user
        self.level = level
        self.score = score
        self.seq_length = min(10, 2 + level)  # Level 1 = 3 items, Level 2 = 4 items, etc.
        self.sequence: List[str] = [random.choice(SEQUENCE_PALETTE)[0] for _ in range(self.seq_length)]
        self.player_input: List[str] = []
        self.memorizing = True
        self.finished = False

        for emoji_char, label in SEQUENCE_PALETTE:
            btn = discord.ui.Button(
                label=label,
                emoji=emoji_char,
                style=discord.ButtonStyle.secondary,
                disabled=True,
                row=0 if SEQUENCE_PALETTE.index((emoji_char, label)) < 3 else 1,
            )
            btn.callback = self._make_color_callback(emoji_char)
            self.add_item(btn)

    def build_embed(self) -> discord.Embed:
        if self.memorizing:
            seq_display = "  ".join(self.sequence)
            desc = (
                f"**Level:** `{self.level}` | **Sequence Length:** `{self.seq_length}` items\n\n"
                f"**Remember this sequence:**\n"
                f"### {seq_display}\n\n"
                f"⏳ *Memorize carefully! Hiding in a moment...*"
            )
            color = ROFColors.WARNING
        else:
            entered = "  ".join(self.player_input) if self.player_input else "*Click the buttons below in order...*"
            remaining = self.seq_length - len(self.player_input)
            desc = (
                f"**Level:** `{self.level}` | **Score:** `{self.score}`\n"
                f"**Items Remaining:** `{remaining} / {self.seq_length}`\n\n"
                f"**Your Input:**\n"
                f"### {entered}\n\n"
                f"Now reproduce the exact sequence using the buttons below!"
            )
            color = ROFColors.ARENA

        return rof_embed(
            title="🧠 ROF MEMORY CHALLENGE",
            description=desc,
            color=color,
            footer_extra=f"Player: {self.user.display_name}",
        )

    def _make_color_callback(self, emoji_char: str):
        async def _callback(interaction: discord.Interaction):
            if not await ensure_session_player(interaction, self.user.id, "play this Memory Challenge"):
                return
            if self.memorizing or self.finished:
                return await interaction.response.defer()

            expected_idx = len(self.player_input)
            self.player_input.append(emoji_char)

            # Check if the clicked item matches the sequence at this position
            if emoji_char != self.sequence[expected_idx]:
                self.finished = True
                self.stop()
                await self._handle_game_over(interaction)
                return

            # Check if entire sequence for this level is complete
            if len(self.player_input) >= self.seq_length:
                self.finished = True
                self.stop()
                new_score = self.score + (self.level * 15)
                next_level = self.level + 1
                next_view = SequenceMemoryView(self.cog, self.user, level=next_level, score=new_score)
                await interaction.response.edit_message(embed=next_view.build_embed(), view=next_view)
                asyncio.create_task(next_view.reveal_then_hide(interaction))
            else:
                await interaction.response.edit_message(embed=self.build_embed(), view=self)

        return _callback

    async def reveal_then_hide(self, interaction: discord.Interaction):
        try:
            delay = min(6.0, 2.2 + (self.seq_length * 0.45))
            await asyncio.sleep(delay)
            if self.finished:
                return
            self.memorizing = False
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = False
            await interaction.edit_original_response(embed=self.build_embed(), view=self)
        except Exception:
            pass

    async def _handle_game_over(self, interaction: discord.Interaction):
        highest_level = self.level
        pts = max(10, (self.level - 1) * 15 + 10)
        won = self.level >= 3
        db.record_game_result(
            user_id=self.user.id,
            game_name="Memory Challenge",
            result="win" if won else "loss",
            score=self.score,
            points_earned=pts,
            attempts=self.level,
            mode="single",
            username=self.user.display_name,
        )
        arcade = self.cog.bot.get_cog("ArcadeCore")
        if arcade:
            arcade.reload_cache()

        embed = rof_embed(
            title="🧠 ROF MEMORY CHALLENGE — GAME OVER",
            description=(
                f"❌ **Incorrect sequence!**\n\n"
                f"**Correct Sequence:** {'  '.join(self.sequence)}\n"
                f"**Your Sequence:** {'  '.join(self.player_input)}\n\n"
                f"🏅 **Highest Level Reached:** `Level {highest_level}` (`{self.seq_length}` items)\n"
                f"🎯 **Final Score:** `{self.score}` (`+{pts} Arcade Points`)"
            ),
            color=ROFColors.SUCCESS if won else ROFColors.ERROR,
            footer_extra=f"Player: {self.user.display_name}",
        )
        res_view = GameResultView(self.user, "Memory Challenge", self.cog.start_sequence_memory)
        await interaction.response.edit_message(embed=embed, view=res_view)


# ==============================================================================
# PRESERVED CLASSIC 4x4 EMOJI PAIR MEMORY MATCH
# ==============================================================================

class MemoryLobby(discord.ui.View):
    def __init__(self, cog: "Memory", user: discord.abc.User):
        super().__init__(timeout=120)
        self.cog = cog
        self.user = user

    def get_embed(self):
        return rof_embed(
            title="🧠 ROF MEMORY ARENA",
            description=(
                "Choose which Memory mode you want to play:\n\n"
                "🔴 **Memory Challenge (Sequence):** Memorize a growing sequence of colours (`🔴 🔵 🟢 🟡`) and reproduce it level by level.\n\n"
                "🃏 **Emoji Pair Match (4x4 Grid):** Memorize the 16-card board in 3 seconds and match all 8 animal pairs!"
            ),
            color=ROFColors.ARENA,
            footer_extra=f"Player: {self.user.display_name}",
        )

    @discord.ui.button(label="Sequence Challenge", style=discord.ButtonStyle.primary, emoji="🔴")
    async def sequence_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user.id):
            return
        await self.cog.start_sequence_memory(interaction)

    @discord.ui.button(label="Emoji Pair Match", style=discord.ButtonStyle.success, emoji="🃏")
    async def play_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user.id):
            return

        uid = str(interaction.user.id)
        now = time.time()
        history = [t for t in self.cog.play_history.get(uid, []) if now - t < 3600]

        if len(history) >= 10:
            return await interaction.response.send_message(
                "⏳ **Slow down!** You have played 10 Pair Match games this hour. Try Sequence Challenge or take a short break!",
                ephemeral=True,
            )

        history.append(now)
        self.cog.play_history[uid] = history

        game_view = MemoryGameView(self.cog, self.user, "easy", preview=True)
        await interaction.response.edit_message(embed=game_view.get_embed(preview=True), view=game_view)
        await asyncio.sleep(3.0)

        for child in game_view.children:
            if isinstance(child, discord.ui.Button):
                child.label = "❓"
                child.style = discord.ButtonStyle.secondary
                child.disabled = False

        game_view.is_locked = False
        try:
            await interaction.edit_original_response(embed=game_view.get_embed(preview=False), view=game_view)
        except discord.NotFound:
            pass


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

        deck = EMOJIS[: self.pairs] * 2
        random.shuffle(deck)

        self.cards = deck
        self.revealed = []
        self.matched = set()
        self.is_locked = True

        for i in range(self.total_cards):
            btn = discord.ui.Button(
                label="❓",
                style=discord.ButtonStyle.secondary,
                custom_id=f"card_{i}",
                row=i // self.cols,
            )
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
            color = ROFColors.WARNING
        else:
            title = "🧠 ROF Memory Match"
            desc = f"Find all {self.pairs} pairs!\n\n**Moves:** `{self.moves}`\n**Matches:** `{self.matches}/{self.pairs}`"
            color = ROFColors.ARENA

        return rof_embed(title=title, description=desc, color=color, footer_extra=f"Player: {self.user.display_name}")

    def make_callback(self, index):
        async def callback(interaction: discord.Interaction):
            try:
                if interaction.user.id != self.user.id:
                    return await interaction.response.send_message("This isn't your game!", ephemeral=True)

                if self.is_locked or index in self.matched or index in self.revealed:
                    return await interaction.response.defer()

                self.revealed.append(index)

                for child in self.children:
                    if isinstance(child, discord.ui.Button) and child.custom_id == f"card_{index}":
                        child.label = self.cards[index]
                        child.style = discord.ButtonStyle.primary
                        child.disabled = True

                if len(self.revealed) == 2:
                    self.moves += 1
                    idx1, idx2 = self.revealed

                    if self.cards[idx1] == self.cards[idx2]:
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
                    await interaction.response.edit_message(embed=self.get_embed(), view=self)
            except discord.NotFound:
                pass
            except Exception as e:
                print(f"Memory Game Error: {e}")

        return callback

    async def end_game(self, interaction):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        points = max(10, 50 - (self.moves * 3))
        embed = self.get_embed()
        embed.color = ROFColors.GOLD
        embed.title = "🏆 ROF Memory Match — Complete!"
        embed.description = f"You cleared the board in **{self.moves} moves**!"
        embed.add_field(name="Points Earned", value=f"**+{points} Arcade Points**", inline=False)

        db.record_game_result(
            user_id=self.user.id,
            game_name="Memory Match",
            result="win",
            score=points,
            points_earned=points,
            attempts=self.moves,
            mode="single",
            username=self.user.display_name,
        )
        arcade = self.cog.bot.get_cog("ArcadeCore")
        if arcade:
            arcade.reload_cache()

        view = PlayAgainView(self.cog, self.user)
        try:
            await interaction.response.edit_message(embed=embed, view=view)
        except discord.NotFound:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


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

    async def start_sequence_memory(self, interaction: discord.Interaction):
        view = SequenceMemoryView(self, interaction.user, level=1, score=0)
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=view.build_embed(), view=view)
        else:
            await interaction.response. edit_message(embed=view.build_embed(), view=view)
        asyncio.create_task(view.reveal_then_hide(interaction))

    @app_commands.command(name="memory", description="Play ROF Memory Challenge (Sequence) or Emoji Pair Match")
    async def memory(self, interaction: discord.Interaction):
        lobby = MemoryLobby(self, interaction.user)
        await interaction.response.send_message(embed=lobby.get_embed(), view=lobby, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Memory(bot))