# cogs/codebreaker.py
import asyncio
import random
import time
import discord
from discord import app_commands
from discord.ext import commands
from typing import Dict, List, Optional, Tuple

from core.config import GUILD_ID, ROFColors
from core.database import db
from core.rooms import MultiplayerRoom, RoomLobbyView, room_manager
from core.ui import rof_embed


def generate_secret_code(allow_repeats: bool = False) -> str:
    """Generate a 4-digit secret code with no leading zero. Default: 4 unique digits."""
    first = random.choice("123456789")
    if allow_repeats:
        rest = [random.choice("0123456789") for _ in range(3)]
        return first + "".join(rest)
    pool = [d for d in "0123456789" if d != first]
    rest = random.sample(pool, 3)
    return first + "".join(rest)


def evaluate_codebreaker_guess(secret: str, guess: str) -> Tuple[int, int]:
    """
    Calculate exact Mastermind/Codebreaker clues:
    Returns (green_exact_position, yellow_wrong_position), handling both unique and repeated digits accurately.
    """
    s_list = list(secret)
    g_list = list(guess)
    greens = 0
    yellows = 0

    for i in range(4):
        if g_list[i] == s_list[i]:
            greens += 1
            s_list[i] = None
            g_list[i] = None

    for i in range(4):
        if g_list[i] is not None and g_list[i] in s_list:
            yellows += 1
            s_list[s_list.index(g_list[i])] = None

    return greens, yellows


# ---------- MULTIPLAYER CODEBREAKER RACE (PRIORITY SPEC 3.8) ----------

class CodebreakerRaceModal(discord.ui.Modal, title="ROF Codebreaker — Submit Guess"):
    guess_input = discord.ui.TextInput(
        label="Enter your 4-digit guess (No leading 0)",
        placeholder="e.g., 4271",
        min_length=4,
        max_length=4,
        required=True,
    )

    def __init__(self, match_view: "CodebreakerMatchView"):
        super().__init__()
        self.match_view = match_view

    async def on_submit(self, interaction: discord.Interaction):
        await self.match_view.handle_guess(interaction, self.guess_input.value.strip())


class CodebreakerMatchView(discord.ui.View):
    """Active multiplayer (or solo practice) Four-Digit Codebreaker session."""

    def __init__(
        self,
        cog: "Codebreaker",
        room: MultiplayerRoom,
        max_attempts: int = 10,
        round_seconds: int = 180,
        allow_repeats: bool = False,
    ):
        super().__init__(timeout=round_seconds + 30)
        self.cog = cog
        self.room = room
        self.max_attempts = max_attempts
        self.round_seconds = round_seconds
        self.allow_repeats = allow_repeats
        self.secret_code = generate_secret_code(allow_repeats=allow_repeats)
        self.start_ts = time.time()
        self.end_ts = int(self.start_ts + round_seconds)
        self.guesses: Dict[int, List[Tuple[str, int, int]]] = {p.id: [] for p in room.players}
        self.winner: Optional[discord.abc.User] = None
        self.finished = False
        self.timer_task: Optional[asyncio.Task] = None

    def build_public_embed(self) -> discord.Embed:
        remaining = max(0, int(self.end_ts - time.time()))
        mins, secs = divmod(remaining, 60)
        rule_str = "4 digits (repeats allowed, no leading 0)" if self.allow_repeats else "4 unique digits (no repeats, no leading 0)"

        desc = (
            f"Crack the four-digit secret code!\n"
            f"**Rules:** {rule_str}\n"
            f"**Max Attempts:** `{self.max_attempts}` | **Time Remaining:** `{mins:02d}:{secs:02d}` (<t:{self.end_ts}:R>)\n\n"
            f"🟢 = Correct digit & position | 🟡 = Correct digit, wrong position\n"
            f"*All guesses and clues are private to each player.*"
        )
        embed = rof_embed(
            title="🔐 ROF CODEBREAKER",
            description=desc,
            color=ROFColors.ARENA if not self.finished else (ROFColors.SUCCESS if self.winner else ROFColors.ERROR),
            footer_extra=f"Room {self.room.room_id}",
        )

        progress_lines = []
        for p in self.room.players:
            p_guesses = self.guesses.get(p.id, [])
            used = len(p_guesses)
            if p_guesses:
                best_g, best_y = max((g, y) for _, g, y in p_guesses)
                status = "🏆 **SOLVED!**" if (self.winner and self.winner.id == p.id) else f"Best clue: 🟢 `{best_g}` | 🟡 `{best_y}`"
            else:
                status = "*No guesses yet*"
            progress_lines.append(f"• {p.mention} — Attempts: `{used}/{self.max_attempts}` ({status})")

        embed.add_field(name="👥 Player Progress", value="\n".join(progress_lines) or "*None*", inline=False)

        if self.finished:
            if self.winner:
                w_attempts = len(self.guesses[self.winner.id])
                elapsed = round(time.time() - self.start_ts, 1)
                embed.add_field(
                    name="🏁 Match Result",
                    value=(
                        f"🎉 **{self.winner.mention} cracked the secret code!**\n"
                        f"🔓 **Secret Code:** `{self.secret_code}`\n"
                        f"🎯 **Attempts Used:** `{w_attempts} / {self.max_attempts}` ({elapsed}s)"
                    ),
                    inline=False,
                )
            else:
                embed.add_field(
                    name="🏁 Match Result",
                    value=(
                        f"⌛ **Game Over!** Nobody cracked the code in time.\n"
                        f"🔓 **Secret Code:** `{self.secret_code}`"
                    ),
                    inline=False,
                )
        return embed

    def build_private_board(self, user_id: int) -> discord.Embed:
        p_guesses = self.guesses.get(user_id, [])
        remaining = max(0, int(self.end_ts - time.time()))
        mins, secs = divmod(remaining, 60)

        history_lines = [
            f"`{g_str}` → 🟢 **{greens}** | 🟡 **{yellows}**"
            for g_str, greens, yellows in p_guesses
        ]
        board_text = "\n".join(history_lines) if history_lines else "*No guesses submitted yet.*"

        embed = rof_embed(
            title="🔐 ROF CODEBREAKER — YOUR CLUES",
            description=(
                f"Crack the four-digit secret code!\n"
                f"**Attempts:** `{len(p_guesses)} / {self.max_attempts}`\n"
                f"**Time remaining:** `{mins:02d}:{secs:02d}`"
            ),
            color=ROFColors.INFO,
        )
        embed.add_field(name="Your Previous Guesses", value=board_text, inline=False)
        return embed

    @discord.ui.button(label="Submit Guess", style=discord.ButtonStyle.primary, emoji="🔢")
    async def submit_guess_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.room.has_player(interaction.user.id):
            return await interaction.response.send_message(
                "⚠️ You are not a participant in this Codebreaker room.", ephemeral=True
            )
        if self.finished:
            return await interaction.response.send_message(
                "ℹ️ This Codebreaker match has already ended.", ephemeral=True
            )
        used = len(self.guesses.get(interaction.user.id, []))
        if used >= self.max_attempts:
            return await interaction.response.send_message(
                f"⚠️ You have used all `{self.max_attempts}` attempts! Wait for other players to finish.",
                ephemeral=True,
            )
        await interaction.response.send_modal(CodebreakerRaceModal(self))

    @discord.ui.button(label="My Guesses", style=discord.ButtonStyle.secondary, emoji="📋")
    async def view_my_guesses_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.room.has_player(interaction.user.id):
            return await interaction.response.send_message(
                "⚠️ You are not in this Codebreaker match.", ephemeral=True
            )
        await interaction.response.send_message(
            embed=self.build_private_board(interaction.user.id), ephemeral=True
        )

    async def handle_guess(self, interaction: discord.Interaction, guess_str: str):
        # Validate 4-digit rules before acquiring lock
        if len(guess_str) != 4 or not guess_str.isdigit():
            return await interaction.response.send_message(
                "❌ Invalid guess! Please enter **exactly 4 digits** (e.g., `4271`).", ephemeral=True
            )
        if guess_str[0] == "0":
            return await interaction.response.send_message(
                "❌ Invalid guess! The secret code **cannot start with 0**.", ephemeral=True
            )
        if not self.allow_repeats and len(set(guess_str)) != 4:
            return await interaction.response.send_message(
                "❌ Invalid guess! All **4 digits must be unique** (no repeated digits).", ephemeral=True
            )

        async with self.room.lock:
            if self.finished:
                return await interaction.response.send_message(
                    "⚠️ The match just ended before your guess was processed!", ephemeral=True
                )
            p_list = self.guesses.setdefault(interaction.user.id, [])
            if len(p_list) >= self.max_attempts:
                return await interaction.response.send_message(
                    f"⚠️ You have already used all `{self.max_attempts}` attempts.", ephemeral=True
                )

            greens, yellows = evaluate_codebreaker_guess(self.secret_code, guess_str)
            p_list.append((guess_str, greens, yellows))

            if greens == 4:
                self.winner = interaction.user
                self.finished = True
                if self.timer_task and not self.timer_task.done():
                    self.timer_task.cancel()
            elif all(len(self.guesses.get(p.id, [])) >= self.max_attempts for p in self.room.players):
                self.finished = True
                if self.timer_task and not self.timer_task.done():
                    self.timer_task.cancel()

        # Send private clue board immediately to the player
        private_embed = self.build_private_board(interaction.user.id)
        if greens == 4:
            private_embed.color = ROFColors.SUCCESS
            private_embed.add_field(
                name="🎉 CODE CRACKED!",
                value=f"You solved `{self.secret_code}` in **{len(p_list)}** attempts!",
                inline=False,
            )
        else:
            private_embed.add_field(
                name="Latest Feedback",
                value=f"`{guess_str}` → 🟢 Correct position: **{greens}** | 🟡 Wrong position: **{yellows}**",
                inline=False,
            )
        await interaction.response.send_message(embed=private_embed, ephemeral=True)

        # Update public board
        if self.finished:
            await self.finish_match()
        elif self.room.message:
            try:
                await self.room.message.edit(embed=self.build_public_embed(), view=self)
            except Exception:
                pass

    async def run_timer(self):
        try:
            await asyncio.sleep(self.round_seconds)
            async with self.room.lock:
                if self.finished:
                    return
                self.finished = True
            await self.finish_match()
        except asyncio.CancelledError:
            pass

    async def finish_match(self):
        self.stop()
        self.room.status = "finished"
        room_manager.close_room(self.room.room_id)

        duration = round(time.time() - self.start_ts, 1)
        arcade = self.cog.bot.get_cog("ArcadeCore")

        for p in self.room.players:
            attempts = len(self.guesses.get(p.id, []))
            won = self.winner is not None and p.id == self.winner.id
            pts = max(25, 70 - (attempts - 1) * 5) if won else 10
            score = (100 - (attempts - 1) * 10) if won else (attempts * 5)
            db.record_game_result(
                user_id=p.id,
                game_name="Codebreaker",
                result="win" if won else "loss",
                score=score,
                points_earned=pts,
                attempts=attempts,
                duration_sec=duration,
                mode="multi" if len(self.room.players) > 1 else "single",
                username=p.display_name,
            )
            if arcade:
                arcade.reload_cache()

        rematch_view = CodebreakerFinishedView(self.cog, self.room)
        if self.room.message:
            try:
                await self.room.message.edit(embed=self.build_public_embed(), view=rematch_view)
            except Exception:
                pass


class CodebreakerFinishedView(discord.ui.View):
    def __init__(self, cog: "Codebreaker", prev_room: MultiplayerRoom):
        super().__init__(timeout=180)
        self.cog = cog
        self.prev_room = prev_room

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.success, emoji="🔄")
    async def rematch_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.open_room(interaction)

    @discord.ui.button(label="View Stats", style=discord.ButtonStyle.primary, emoji="📊")
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        prof = db.get_player_profile(interaction.user.id)
        gstat = prof["game_stats"].get("Codebreaker", {})
        embed = rof_embed(
            title=f"📊 {interaction.user.display_name} — Codebreaker Stats",
            description=(
                f"**Played:** `{gstat.get('played', 0)}` | **Wins:** `{gstat.get('wins', 0)}`\n"
                f"**Best Score:** `{gstat.get('best_score', 0)}` | **Total Points:** `{prof['points']}`"
            ),
            color=ROFColors.ARENA,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        for child in self.children:
            child.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except Exception:
            pass


# ---------- PRESERVED 1v1 CLASSIC CHALLENGE MODAL & VIEW ----------

class SetCodeModal(discord.ui.Modal, title="Set the Secret Code"):
    code = discord.ui.TextInput(
        label="Enter a 4-digit code (numbers 1-6 only)",
        placeholder="e.g., 1234",
        min_length=4,
        max_length=4,
    )

    def __init__(self, cog, challenger, opponent):
        super().__init__()
        self.cog = cog
        self.challenger = challenger
        self.opponent = opponent

    async def on_submit(self, interaction: discord.Interaction):
        code = self.code.value.strip()
        if not code.isdigit() or any(c not in "123456" for c in code):
            return await interaction.response.send_message(
                "❌ Invalid code! Use only numbers 1-6.", ephemeral=True
            )
        view = CodebreakerGameView(self.cog, self.challenger, self.opponent, code)
        await interaction.response.send_message(
            f"✅ Code set! {self.opponent.mention}, your turn to guess.",
            embed=view.get_embed(),
            view=view,
        )


class GuessModal(discord.ui.Modal, title="Guess the Code"):
    guess = discord.ui.TextInput(
        label="Enter your 4-digit guess (1-6)",
        min_length=4,
        max_length=4,
    )

    def __init__(self, view):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.opponent.id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        await self.view.process_guess(interaction, self.guess.value.strip())


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
            return await interaction.response.send_message(
                "Only the guesser can use this button!", ephemeral=True
            )
        await interaction.response.send_modal(GuessModal(self))

    def get_embed(self):
        embed = rof_embed(
            title="🔐 ROF Codebreaker (1v1 Duel)",
            description=(
                f"**{self.opponent.mention}** is trying to crack **{self.challenger.mention}**'s code!\n"
                f"🟩 = Right number, right spot | 🟨 = Right number, wrong spot | ⬛ = Wrong number\n"
            ),
            color=ROFColors.ARENA,
        )
        board = "\n".join(f"`{g['guess']}`  ➔  {g['result']}" for g in self.guesses)
        embed.add_field(
            name=f"Guesses ({len(self.guesses)}/10)",
            value=board or "*No guesses yet.*",
            inline=False,
        )
        return embed

    async def process_guess(self, interaction, guess_str):
        if not guess_str.isdigit() or any(c not in "123456" for c in guess_str):
            return await interaction.response.send_message(
                "❌ Invalid guess! Use only numbers 1-6.", ephemeral=True
            )
        greens, yellows = evaluate_codebreaker_guess("".join(self.secret_code), guess_str)
        blacks = 4 - greens - yellows
        pegs = (["🟩"] * greens) + (["🟨"] * yellows) + (["⬛"] * blacks)
        self.guesses.append({"guess": guess_str, "result": " ".join(pegs)})

        if greens == 4:
            self.won = True
            self.stop()
            await self.end_game(interaction)
        elif len(self.guesses) >= 10:
            self.stop()
            await self.end_game(interaction)
        else:
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def end_game(self, interaction):
        for child in self.children:
            child.disabled = True
        embed = self.get_embed()
        arcade = self.cog.bot.get_cog("ArcadeCore")

        if self.won:
            embed.color = ROFColors.SUCCESS
            embed.add_field(
                name="Result", value=f"🏆 **{self.opponent.mention} cracked the code!**", inline=False
            )
            if arcade:
                arcade.add_points(self.opponent.id, 50, "Codebreaker", won=True)
                arcade.add_points(self.challenger.id, 10, "Codebreaker", won=False)
        else:
            embed.color = ROFColors.ERROR
            embed.add_field(
                name="Result",
                value=f"❌ **Out of guesses!** The code was `{''.join(self.secret_code)}`",
                inline=False,
            )
            if arcade:
                arcade.add_points(self.challenger.id, 40, "Codebreaker", won=True)
                arcade.add_points(self.opponent.id, 10, "Codebreaker", won=False)

        await interaction.response.edit_message(embed=embed, view=self)


class Codebreaker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def open_room(
        self,
        interaction: discord.Interaction,
        max_attempts: int = 10,
        round_seconds: int = 180,
        allow_repeats: bool = False,
        min_players: int = 1,
    ):
        existing = room_manager.get_player_active_room(interaction.user.id, "codebreaker")
        if existing:
            return await interaction.response.send_message(
                f"⚠️ You are already in an active Codebreaker room (`{existing.room_id}`).",
                ephemeral=True,
            )

        room = room_manager.create_room(
            game_key="codebreaker",
            game_title="Four-Digit Codebreaker",
            host=interaction.user,
            min_players=min_players,
            max_players=8,
            config={
                "max_attempts": max_attempts,
                "round_seconds": round_seconds,
                "allow_repeats": allow_repeats,
            },
        )

        async def _on_start(start_inter: discord.Interaction, active_room: MultiplayerRoom):
            match_view = CodebreakerMatchView(
                self,
                active_room,
                max_attempts=max_attempts,
                round_seconds=round_seconds,
                allow_repeats=allow_repeats,
            )
            await start_inter.response.edit_message(
                embed=match_view.build_public_embed(), view=match_view
            )
            active_room.message = start_inter.message
            match_view.timer_task = asyncio.create_task(match_view.run_timer())

        lobby = RoomLobbyView(
            room=room,
            on_start_callback=_on_start,
            extra_description=(
                f"🎯 **Goal:** Crack the 4-digit secret code first!\n"
                f"🔢 **Digits:** {'4 digits (repeats allowed)' if allow_repeats else '4 unique digits (no repeats, no leading 0)'}\n"
                f"⏳ **Limit:** `{max_attempts}` attempts • `{round_seconds}s` timer"
            ),
        )
        await interaction.response.send_message(embed=lobby.build_embed(), view=lobby)
        try:
            room.message = await interaction.original_response()
        except Exception:
            pass

    @app_commands.command(
        name="codebreaker",
        description="Start a Four-Digit Codebreaker Multiplayer Room or 1v1 Duel",
    )
    @app_commands.describe(
        opponent="Optional: Challenge a specific member to a classic 1v1 duel (leave blank for Multiplayer Room)",
        attempts="Max attempts allowed in Room mode (default: 10)",
        timer_seconds="Round timer in seconds for Room mode (default: 180)",
    )
    async def codebreaker(
        self,
        interaction: discord.Interaction,
        opponent: Optional[discord.Member] = None,
        attempts: int = 10,
        timer_seconds: int = 180,
    ):
        if opponent is not None:
            if opponent.bot or opponent.id == interaction.user.id:
                return await interaction.response.send_message(
                    "⚠️ Please choose a valid human opponent.", ephemeral=True
                )
            return await interaction.response.send_modal(
                SetCodeModal(self, interaction.user, opponent)
            )

        attempts = max(4, min(20, attempts))
        timer_seconds = max(30, min(600, timer_seconds))
        await self.open_room(
            interaction, max_attempts=attempts, round_seconds=timer_seconds, min_players=1
        )


async def setup(bot):
    await bot.add_cog(Codebreaker(bot))