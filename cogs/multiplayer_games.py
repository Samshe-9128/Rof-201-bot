# cogs/multiplayer_games.py
import asyncio
import random
import time
import discord
from discord.ext import commands
from typing import Dict, List, Optional

from cogs.singleplayer_games import (
    EMOJI_PUZZLES,
    RPS_BEATS,
    RPS_CHOICES,
    SCRAMBLE_WORDS,
    TRIVIA_BANK,
    _normalize_text,
    _shuffle_word,
    generate_math_problem,
)
from core.config import ROFColors
from core.database import db
from core.rooms import MultiplayerRoom, RoomLobbyView, room_manager
from core.ui import rof_embed


# ==============================================================================
# 3.3 WORD GUESSING RACE & 3.7 MULTIPLAYER EMOJI GUESSING
# ==============================================================================

class RaceAnswerModal(discord.ui.Modal, title="Submit Your Answer"):
    answer_input = discord.ui.TextInput(
        label="Your Answer",
        placeholder="Type your answer fast...",
        min_length=1,
        max_length=50,
        required=True,
    )

    def __init__(self, view: "MultiRoundRaceView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        await self.view.handle_submission(interaction, self.answer_input.value.strip())


class MultiRoundRaceView(discord.ui.View):
    """Handles multi-round races for Word Guessing Race (3.3), Quick Math Battle (3.4), and Emoji Race (3.7)."""

    def __init__(
        self,
        cog: "MultiplayerGames",
        room: MultiplayerRoom,
        mode: str = "word_race",  # 'word_race', 'math_battle', 'emoji_race'
        total_rounds: int = 3,
        round_seconds: int = 30,
    ):
        super().__init__(timeout=total_rounds * (round_seconds + 15) + 60)
        self.cog = cog
        self.room = room
        self.mode = mode
        self.total_rounds = total_rounds
        self.round_seconds = round_seconds
        self.current_round = 1
        self.scores: Dict[int, int] = {p.id: 0 for p in room.players}
        self.round_winner: Optional[discord.abc.User] = None
        self.round_solved_by: Dict[int, int] = {}  # user_id -> points earned this round
        self.used_items = set()
        self.finished = False
        self.round_task: Optional[asyncio.Task] = None
        self._prepare_round()

    def _prepare_round(self):
        self.round_winner = None
        self.round_solved_by = {}
        self.round_start_ts = time.perf_counter()
        self.round_deadline = int(time.time() + self.round_seconds)

        if self.mode == "word_race":
            all_words = SCRAMBLE_WORDS["easy"] + SCRAMBLE_WORDS["medium"] + SCRAMBLE_WORDS["hard"]
            pool = [w for w in all_words if w[0] not in self.used_items] or all_words
            word, clue = random.choice(pool)
            self.used_items.add(word)
            self.target_answer = word
            self.valid_aliases = {_normalize_text(word)}
            self.prompt_display = f"Unscramble: **`{_shuffle_word(word)}`**\n💡 *Clue: {clue}*"
        elif self.mode == "math_battle":
            q_str, ans = generate_math_problem("medium" if self.current_round < 3 else "hard")
            self.target_answer = str(ans)
            self.valid_aliases = {str(ans)}
            self.prompt_display = f"Calculate:\n## `{q_str} = ?`\n*Correct answer = 10 pts + up to 5 speed bonus pts!*"
        else:
            pool = [p for p in EMOJI_PUZZLES if p["ans"] not in self.used_items] or EMOJI_PUZZLES
            puz = random.choice(pool)
            self.used_items.add(puz["ans"])
            self.target_answer = puz["ans"]
            self.valid_aliases = {_normalize_text(puz["ans"])} | {_normalize_text(a) for a in puz.get("aliases", [])}
            self.prompt_display = f"Category: **`{puz['cat']}`**\n# {puz['emojis']}\n💡 *Hint: {puz['hint']}*"

    def build_embed(self, status_note: str = "") -> discord.Embed:
        titles = {
            "word_race": "🔤 ROF WORD GUESSING RACE",
            "math_battle": "🧮 ROF QUICK MATH BATTLE",
            "emoji_race": "🎭 ROF MULTIPLAYER EMOJI GUESSING",
        }
        rem = max(0, int(self.round_deadline - time.time()))
        note_block = f"{status_note}\n\n" if status_note else ""
        desc = (
            f"{note_block}"
            f"**Round:** `{self.current_round} / {self.total_rounds}` | **Time Remaining:** `{rem}s` (<t:{self.round_deadline}:R>)\n\n"
            f"{self.prompt_display}"
        )
        embed = rof_embed(
            title=titles.get(self.mode, "ROF MULTIPLAYER RACE"),
            description=desc,
            color=ROFColors.ARENA if not self.finished else ROFColors.GOLD,
            footer_extra=f"Room {self.room.room_id}",
        )

        # Live Scoreboard
        sorted_players = sorted(self.room.players, key=lambda p: self.scores.get(p.id, 0), reverse=True)
        board_lines = []
        for idx, p in enumerate(sorted_players, 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"`#{idx}`")
            board_lines.append(f"{medal} {p.mention} — **`{self.scores.get(p.id, 0)} pts`**")
        embed.add_field(name="📊 Live Scoreboard", value="\n".join(board_lines), inline=False)
        return embed

    @discord.ui.button(label="Submit Answer", style=discord.ButtonStyle.primary, emoji="⚡")
    async def submit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.room.has_player(interaction.user.id):
            return await interaction.response.send_message(
                "⚠️ You are not in this match!", ephemeral=True
            )
        if self.finished:
            return await interaction.response.send_message("ℹ️ Match has already finished!", ephemeral=True)
        if interaction.user.id in self.round_solved_by:
            return await interaction.response.send_message(
                "✅ You already solved this round! Waiting for the round to advance...", ephemeral=True
            )
        await interaction.response.send_modal(RaceAnswerModal(self))

    async def handle_submission(self, interaction: discord.Interaction, raw_value: str):
        norm = raw_value.strip() if self.mode == "math_battle" else _normalize_text(raw_value)
        if norm not in self.valid_aliases:
            return await interaction.response.send_message(
                f"❌ `{raw_value}` is incorrect! Try again!", ephemeral=True
            )

        elapsed = time.perf_counter() - self.round_start_ts
        advance_now = False
        round_summary = ""

        async with self.room.lock:
            if self.finished or interaction.user.id in self.round_solved_by:
                return await interaction.response.send_message(
                    "ℹ️ Round already completed!", ephemeral=True
                )

            if self.mode == "math_battle":
                # Spec 3.4: 10 base points + 0-5 speed bonus; multiple players can score in a round
                speed_bonus = max(0, min(5, int(5 - (elapsed // 4))))
                earned = 10 + speed_bonus
                self.round_solved_by[interaction.user.id] = earned
                self.scores[interaction.user.id] = self.scores.get(interaction.user.id, 0) + earned
                if self.round_winner is None:
                    self.round_winner = interaction.user
                if len(self.round_solved_by) >= len(self.room.players):
                    advance_now = True
                    round_summary = f"⚡ Everyone solved Round {self.current_round}! Answer: **`{self.target_answer}`** (Fastest: {self.round_winner.mention})"
            else:
                # Spec 3.3 & 3.7: First correct answer wins the round immediately
                earned = 20
                self.round_winner = interaction.user
                self.round_solved_by[interaction.user.id] = earned
                self.scores[interaction.user.id] = self.scores.get(interaction.user.id, 0) + earned
                advance_now = True
                round_summary = f"🏆 **{interaction.user.mention}** won Round {self.current_round}! Answer: **`{self.target_answer}`** (`+{earned} pts`)"

        await interaction.response.send_message(
            f"✅ **Correct!** You earned **`+{earned} points`**!", ephemeral=True
        )

        if advance_now:
            if self.round_task and not self.round_task.done():
                self.round_task.cancel()
            await self.advance_or_finish(round_summary)
        elif self.room.message:
            try:
                await self.room.message.edit(
                    embed=self.build_embed(f"✅ {interaction.user.mention} locked in a correct answer!"),
                    view=self,
                )
            except Exception:
                pass

    async def run_round_timer(self):
        try:
            await asyncio.sleep(self.round_seconds)
            async with self.room.lock:
                if self.finished:
                    return
                summary = f"⌛ Round {self.current_round} time expired! Answer was **`{self.target_answer}`**."
            await self.advance_or_finish(summary)
        except asyncio.CancelledError:
            pass

    async def advance_or_finish(self, summary: str):
        async with self.room.lock:
            if self.finished:
                return
            if self.current_round >= self.total_rounds:
                self.finished = True
            else:
                self.current_round += 1
                self._prepare_round()

        if self.finished:
            await self.finish_match(summary)
        else:
            if self.room.message:
                try:
                    await self.room.message.edit(embed=self.build_embed(summary), view=self)
                except Exception:
                    pass
            self.round_task = asyncio.create_task(self.run_round_timer())

    async def finish_match(self, final_note: str):
        self.stop()
        self.room.status = "finished"
        room_manager.close_room(self.room.room_id)
        for child in self.children:
            child.disabled = True

        game_names = {
            "word_race": "Word Guessing Race",
            "math_battle": "Quick Math Battle",
            "emoji_race": "Multiplayer Emoji Guessing",
        }
        gname = game_names.get(self.mode, "Multiplayer Race")
        max_score = max(self.scores.values()) if self.scores else 0
        winners = [p for p in self.room.players if self.scores.get(p.id, 0) == max_score and max_score > 0]

        for p in self.room.players:
            sc = self.scores.get(p.id, 0)
            is_win = p in winners
            pts = max(10, sc + (20 if is_win else 5))
            db.record_game_result(
                user_id=p.id,
                game_name=gname,
                result="win" if is_win else "loss",
                score=sc,
                points_earned=pts,
                attempts=self.total_rounds,
                mode="multi",
                username=p.display_name,
            )
        arcade = self.cog.bot.get_cog("ArcadeCore")
        if arcade:
            arcade.reload_cache()

        embed = self.build_embed(final_note)
        if winners:
            w_mentions = ", ".join(w.mention for w in winners)
            embed.add_field(
                name="🏆 Final Match Winner",
                value=f"🎉 **{w_mentions}** won the match with **`{max_score} points`**!",
                inline=False,
            )
        else:
            embed.add_field(name="🏁 Final Result", value="No points were scored this match.", inline=False)

        rematch_view = MultiRematchView(self.cog, self.mode)
        if self.room.message:
            try:
                await self.room.message.edit(embed=embed, view=rematch_view)
            except Exception:
                pass


# ==============================================================================
# 3.5 TRIVIA BATTLE (PRIVATE LOCKED ANSWERS, TIE HANDLING)
# ==============================================================================

class TriviaBattleView(discord.ui.View):
    def __init__(self, cog: "MultiplayerGames", room: MultiplayerRoom, total_rounds: int = 5):
        super().__init__(timeout=total_rounds * 35 + 60)
        self.cog = cog
        self.room = room
        pool = list(TRIVIA_BANK)
        random.shuffle(pool)
        self.questions = pool[: min(total_rounds, len(pool))]
        self.round_idx = 0
        self.scores: Dict[int, int] = {p.id: 0 for p in room.players}
        self.submissions: Dict[int, Tuple[str, float]] = {}
        self.finished = False
        self.round_task: Optional[asyncio.Task] = None
        self._setup_round()

    def _setup_round(self):
        self.submissions = {}
        self.round_start = time.perf_counter()
        self.deadline = int(time.time() + 20)
        self.clear_items()
        q_item = self.questions[self.round_idx]
        opts = list(q_item["opts"])
        random.shuffle(opts)
        labels = ["A", "B", "C", "D"]
        for i, opt in enumerate(opts):
            btn = discord.ui.Button(label=f"{labels[i]}: {opt}", style=discord.ButtonStyle.primary, row=i // 2)
            btn.callback = self._make_opt_cb(opt)
            self.add_item(btn)

    def build_embed(self, note: str = "") -> discord.Embed:
        q_item = self.questions[self.round_idx]
        note_block = f"{note}\n\n" if note else ""
        answered_mentions = [p.mention for p in self.room.players if p.id in self.submissions]
        ans_status = ", ".join(answered_mentions) if answered_mentions else "*Waiting for players...*"

        desc = (
            f"{note_block}"
            f"**Round:** `{self.round_idx + 1} / {len(self.questions)}` | **Category:** `{q_item['cat']}`\n"
            f"**Time Closes:** <t:{self.deadline}:R>\n\n"
            f"### {q_item['q']}\n\n"
            f"🔒 **Locked In ({len(self.submissions)}/{len(self.room.players)}):** {ans_status}"
        )
        embed = rof_embed(
            title="❓ ROF TRIVIA BATTLE",
            description=desc,
            color=ROFColors.ARENA if not self.finished else ROFColors.GOLD,
            footer_extra=f"Room {self.room.room_id}",
        )

        sorted_p = sorted(self.room.players, key=lambda p: self.scores.get(p.id, 0), reverse=True)
        sb = "\n".join(
            f"`#{i}` {p.mention} — **`{self.scores.get(p.id, 0)} pts`**"
            for i, p in enumerate(sorted_p, 1)
        )
        embed.add_field(name="📊 Live Scoreboard", value=sb, inline=False)
        return embed

    def _make_opt_cb(self, chosen_opt: str):
        async def _cb(interaction: discord.Interaction):
            if not self.room.has_player(interaction.user.id):
                return await interaction.response.send_message(
                    "⚠️ You are not in this Trivia Battle room.", ephemeral=True
                )
            async with self.room.lock:
                if self.finished:
                    return await interaction.response.send_message("ℹ️ Match has ended.", ephemeral=True)
                if interaction.user.id in self.submissions:
                    return await interaction.response.send_message(
                        "🔒 You already locked in your answer for this question! (Changing answers is disabled.)",
                        ephemeral=True,
                    )
                elapsed = time.perf_counter() - self.round_start
                self.submissions[interaction.user.id] = (chosen_opt, elapsed)
                all_in = len(self.submissions) >= len(self.room.players)

            await interaction.response.send_message(
                f"🔒 Answer **`{chosen_opt}`** locked in privately! Waiting for round to close...",
                ephemeral=True,
            )

            if all_in:
                if self.round_task and not self.round_task.done():
                    self.round_task.cancel()
                await self.score_and_advance()
            elif self.room.message:
                try:
                    await self.room.message.edit(embed=self.build_embed(), view=self)
                except Exception:
                    pass

        return _cb

    async def run_timer(self):
        try:
            await asyncio.sleep(20.0)
            await self.score_and_advance()
        except asyncio.CancelledError:
            pass

    async def score_and_advance(self):
        async with self.room.lock:
            if self.finished:
                return
            q_item = self.questions[self.round_idx]
            correct_ans = q_item["ans"]
            correct_players = []
            for p in self.room.players:
                sub = self.submissions.get(p.id)
                if sub and sub[0] == correct_ans:
                    speed_bonus = max(0, min(5, int(5 - (sub[1] // 4))))
                    pts = 15 + speed_bonus
                    self.scores[p.id] = self.scores.get(p.id, 0) + pts
                    correct_players.append(f"{p.mention} (`+{pts}`)")

            summary = (
                f"✅ **Round {self.round_idx + 1} Answer:** **{correct_ans}** — *{q_item['exp']}*\n"
                f"🎯 **Correct:** {', '.join(correct_players) if correct_players else 'Nobody'}"
            )

            if self.round_idx + 1 >= len(self.questions):
                self.finished = True
            else:
                self.round_idx += 1
                self._setup_round()

        if self.finished:
            await self.finish_battle(summary)
        else:
            if self.room.message:
                try:
                    await self.room.message.edit(embed=self.build_embed(summary), view=self)
                except Exception:
                    pass
            self.round_task = asyncio.create_task(self.run_timer())

    async def finish_battle(self, final_summary: str):
        self.stop()
        self.room.status = "finished"
        room_manager.close_room(self.room.room_id)
        for child in self.children:
            child.disabled = True

        max_sc = max(self.scores.values()) if self.scores else 0
        winners = [p for p in self.room.players if self.scores.get(p.id, 0) == max_sc and max_sc > 0]
        is_tie = len(winners) > 1

        for p in self.room.players:
            sc = self.scores.get(p.id, 0)
            res = ("draw" if is_tie else "win") if p in winners else "loss"
            pts = max(10, sc + (20 if p in winners else 5))
            db.record_game_result(
                user_id=p.id,
                game_name="Trivia Battle",
                result=res,
                score=sc,
                points_earned=pts,
                attempts=len(self.questions),
                mode="multi",
                username=p.display_name,
            )
        arcade = self.cog.bot.get_cog("ArcadeCore")
        if arcade:
            arcade.reload_cache()

        embed = self.build_embed(final_summary)
        if is_tie:
            embed.add_field(
                name="🤝 Tie Match!",
                value=f"**{', '.join(w.mention for w in winners)}** tied for 1st place with **`{max_sc} pts`**!",
                inline=False,
            )
        elif winners:
            embed.add_field(
                name="🏆 Trivia Battle Champion",
                value=f"🎉 **{winners[0].mention}** won with **`{max_sc} pts`**!",
                inline=False,
            )
        else:
            embed.add_field(name="🏁 Match Complete", value="No points scored!", inline=False)

        rematch_view = MultiRematchView(self.cog, "trivia_battle")
        if self.room.message:
            try:
                await self.room.message.edit(embed=embed, view=rematch_view)
            except Exception:
                pass


# ==============================================================================
# 3.6 MULTIPLAYER ROCK PAPER SCISSORS (PRIVATE MOVES, BO3 / BO5)
# ==============================================================================

class MultiplayerRPSView(discord.ui.View):
    def __init__(self, cog: "MultiplayerGames", room: MultiplayerRoom, best_of: int = 3):
        super().__init__(timeout=180.0)
        self.cog = cog
        self.room = room
        self.p1 = room.players[0]
        self.p2 = room.players[1]
        self.best_of = best_of
        self.target_wins = (best_of // 2) + 1
        self.scores = {self.p1.id: 0, self.p2.id: 0}
        self.current_moves: Dict[int, str] = {}
        self.round_num = 1
        self.last_reveal = "Both players: choose your move privately below!"
        self.finished = False

    def build_embed(self) -> discord.Embed:
        p1_locked = "🔒 Locked In" if self.p1.id in self.current_moves else "⏳ Choosing..."
        p2_locked = "🔒 Locked In" if self.p2.id in self.current_moves else "⏳ Choosing..."
        desc = (
            f"**Format:** Best of `{self.best_of}` (First to `{self.target_wins}` wins)\n"
            f"**Round:** `{self.round_num}`\n"
            f"**Score:** {self.p1.mention} **`{self.scores[self.p1.id]}`** — **`{self.scores[self.p2.id]}`** {self.p2.mention}\n\n"
            f"{self.last_reveal}\n\n"
            f"• {self.p1.mention}: {p1_locked}\n"
            f"• {self.p2.mention}: {p2_locked}"
        )
        return rof_embed(
            title="✂️ ROF MULTIPLAYER ROCK PAPER SCISSORS",
            description=desc,
            color=ROFColors.ARENA if not self.finished else ROFColors.SUCCESS,
            footer_extra=f"Room {self.room.room_id}",
        )

    @discord.ui.button(label="Rock", style=discord.ButtonStyle.primary, emoji="🪨")
    async def rock_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._submit_move(interaction, "rock")

    @discord.ui.button(label="Paper", style=discord.ButtonStyle.primary, emoji="📄")
    async def paper_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._submit_move(interaction, "paper")

    @discord.ui.button(label="Scissors", style=discord.ButtonStyle.primary, emoji="✂️")
    async def scissors_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._submit_move(interaction, "scissors")

    async def _submit_move(self, interaction: discord.Interaction, move: str):
        if interaction.user.id not in (self.p1.id, self.p2.id):
            return await interaction.response.send_message(
                "⚠️ Only the two dueling players can choose moves!", ephemeral=True
            )
        async with self.room.lock:
            if self.finished:
                return await interaction.response.send_message("ℹ️ Match is already over.", ephemeral=True)
            if interaction.user.id in self.current_moves:
                return await interaction.response.send_message(
                    "🔒 You have already locked in your move for this round!", ephemeral=True
                )
            self.current_moves[interaction.user.id] = move
            both_ready = len(self.current_moves) == 2

        emoji_c, label_c = RPS_CHOICES[move]
        await interaction.response.send_message(
            f"🔒 You selected **{emoji_c} {label_c}** (hidden until both players submit).",
            ephemeral=True,
        )

        if not both_ready:
            if self.room.message:
                try:
                    await self.room.message.edit(embed=self.build_embed(), view=self)
                except Exception:
                    pass
            return

        # Both submitted! Reveal moves simultaneously
        m1 = self.current_moves[self.p1.id]
        m2 = self.current_moves[self.p2.id]
        e1, l1 = RPS_CHOICES[m1]
        e2, l2 = RPS_CHOICES[m2]

        if m1 == m2:
            outcome = "🤝 **Round Draw!**"
        elif RPS_BEATS[m1] == m2:
            self.scores[self.p1.id] += 1
            outcome = f"🎯 **{self.p1.mention} wins Round {self.round_num}!**"
        else:
            self.scores[self.p2.id] += 1
            outcome = f"🎯 **{self.p2.mention} wins Round {self.round_num}!**"

        self.last_reveal = (
            f"**Round {self.round_num} Reveal:**\n"
            f"• {self.p1.mention} chose **{e1} {l1}**\n"
            f"• {self.p2.mention} chose **{e2} {l2}**\n"
            f"{outcome}"
        )
        self.current_moves = {}
        self.round_num += 1

        if self.scores[self.p1.id] >= self.target_wins or self.scores[self.p2.id] >= self.target_wins:
            self.finished = True
            self.stop()
            self.room.status = "finished"
            room_manager.close_room(self.room.room_id)
            winner = self.p1 if self.scores[self.p1.id] > self.scores[self.p2.id] else self.p2
            loser = self.p2 if winner.id == self.p1.id else self.p1

            db.record_game_result(
                user_id=winner.id,
                game_name="Multiplayer RPS",
                result="win",
                score=self.scores[winner.id] * 25,
                points_earned=35,
                attempts=self.round_num - 1,
                mode="multi",
                username=winner.display_name,
            )
            db.record_game_result(
                user_id=loser.id,
                game_name="Multiplayer RPS",
                result="loss",
                score=self.scores[loser.id] * 10,
                points_earned=10,
                attempts=self.round_num - 1,
                mode="multi",
                username=loser.display_name,
            )
            arcade = self.cog.bot.get_cog("ArcadeCore")
            if arcade:
                arcade.reload_cache()

            embed = self.build_embed()
            embed.add_field(
                name="🏆 Match Winner",
                value=f"🎉 **{winner.mention}** won the Best of {self.best_of} series!",
                inline=False,
            )
            rematch_view = MultiRematchView(self.cog, "rps_multi")
            if self.room.message:
                try:
                    await self.room.message.edit(embed=embed, view=rematch_view)
                except Exception:
                    pass
        else:
            if self.room.message:
                try:
                    await self.room.message.edit(embed=self.build_embed(), view=self)
                except Exception:
                    pass


class MultiRematchView(discord.ui.View):
    def __init__(self, cog: "MultiplayerGames", mode: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.mode = mode

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.success, emoji="🔄")
    async def rematch_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.open_multiplayer_room(interaction, self.mode)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        for child in self.children:
            child.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except Exception:
            pass


class MultiplayerGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def open_multiplayer_room(self, interaction: discord.Interaction, mode: str, best_of: int = 3):
        meta = {
            "word_race": ("Word Guessing Race", 2, 10, "🔤 Unscramble the same secret word across 3 rounds! First correct submission wins each round."),
            "math_battle": ("Quick Math Battle", 2, 10, "🧮 Solve the same calculations simultaneously! 10 pts + up to 5 speed bonus pts per round."),
            "trivia_battle": ("Trivia Battle", 2, 10, "❓ Lock in private answers to 5 trivia questions! Live scoreboard & tie handling."),
            "rps_multi": ("Multiplayer Rock Paper Scissors", 2, 2, f"✂️ 1v1 Best of {best_of} duel! Both moves stay hidden until both players lock in."),
            "emoji_race": ("Multiplayer Emoji Guessing", 2, 10, "🎭 Identify the movie, game, phrase, or object from emojis faster than your opponents!"),
        }
        title, min_p, max_p, desc = meta.get(mode, meta["word_race"])

        existing = room_manager.get_player_active_room(interaction.user.id, mode)
        if existing:
            return await interaction.response.send_message(
                f"⚠️ You are already in an active **{title}** room (`{existing.room_id}`).",
                ephemeral=True,
            )

        room = room_manager.create_room(
            game_key=mode,
            game_title=title,
            host=interaction.user,
            min_players=min_p,
            max_players=max_p,
            config={"best_of": best_of},
        )

        async def _on_start(start_inter: discord.Interaction, active_room: MultiplayerRoom):
            if mode in ("word_race", "math_battle", "emoji_race"):
                view = MultiRoundRaceView(self, active_room, mode=mode, total_rounds=3)
                await start_inter.response.edit_message(embed=view.build_embed(), view=view)
                active_room.message = start_inter.message
                view.round_task = asyncio.create_task(view.run_round_timer())
            elif mode == "trivia_battle":
                view = TriviaBattleView(self, active_room, total_rounds=5)
                await start_inter.response.edit_message(embed=view.build_embed(), view=view)
                active_room.message = start_inter.message
                view.round_task = asyncio.create_task(view.run_timer())
            elif mode == "rps_multi":
                view = MultiplayerRPSView(self, active_room, best_of=best_of)
                await start_inter.response.edit_message(embed=view.build_embed(), view=view)
                active_room.message = start_inter.message

        lobby = RoomLobbyView(room=room, on_start_callback=_on_start, extra_description=desc)
        await interaction.response.send_message(embed=lobby.build_embed(), view=lobby)
        try:
            room.message = await interaction.original_response()
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(MultiplayerGames(bot))
