# cogs/singleplayer_games.py
import asyncio
import random
import re
import time
import traceback
import discord
from discord.ext import commands
from typing import Dict, List, Optional, Tuple

from core.config import ROFColors
from core.database import db
from core.permissions import ensure_session_player
from core.ui import GameResultView, GameStartView, rof_embed


# ==============================================================================
# SHARED QUESTION / PUZZLE BANKS
# ==============================================================================

SCRAMBLE_WORDS = {
    "easy": [
        ("APPLE", "A crisp red or green fruit"),
        ("TIGER", "Striped jungle predator"),
        ("SWORD", "Classic medieval blade"),
        ("SHIELD", "Defensive battle gear"),
        ("CROWN", "Worn by a monarch"),
        ("FLAME", "Hot glowing fire"),
        ("WATER", "Essential liquid for life"),
        ("STORM", "Thunder, lightning, and rain"),
    ],
    "medium": [
        ("ALLIANCE", "A union of warriors working together"),
        ("FORTRESS", "A heavily defended military stronghold"),
        ("VICTORY", "Triumph over an enemy in battle"),
        ("STRATEGY", "A careful plan of action"),
        ("CHAMPION", "First-place winner of an arena"),
        ("TREASURE", "Valuable chest of gold and gems"),
        ("GUARDIAN", "Defender who protects the realm"),
        ("CONQUEST", "Taking control of territory"),
    ],
    "hard": [
        ("COMMANDER", "High-ranking leader of an army"),
        ("LABYRINTH", "Complex maze of paths"),
        ("REBELLION", "Uprising against authority"),
        ("MERCENARY", "Soldier hired for battle"),
        ("ARTILLERY", "Large-caliber ranged weaponry"),
        ("VANGUARD", "Forefront troops of an advancing army"),
        ("SOVEREIGN", "Supreme ruler of a realm"),
        ("CHRONICLE", "Historical account of events"),
    ],
}

TRIVIA_BANK = [
    {"cat": "General Knowledge", "diff": "easy", "q": "How many continents are there on Earth?", "opts": ["5", "6", "7", "8"], "ans": "7", "exp": "Earth has 7 continents: Asia, Africa, North America, South America, Antarctica, Europe, and Australia."},
    {"cat": "General Knowledge", "diff": "medium", "q": "Which metal is liquid at standard room temperature?", "opts": ["Mercury", "Lead", "Silver", "Cobalt"], "ans": "Mercury", "exp": "Mercury is the only metallic element that is liquid at standard temperature and pressure."},
    {"cat": "General Knowledge", "diff": "hard", "q": "In which year was the first Nobel Prize awarded?", "opts": ["1895", "1901", "1912", "1920"], "ans": "1901", "exp": "The first Nobel Prizes were awarded in Stockholm, Sweden, on December 10, 1901."},
    {"cat": "Science", "diff": "easy", "q": "What planet is known as the Red Planet?", "opts": ["Venus", "Mars", "Jupiter", "Saturn"], "ans": "Mars", "exp": "Iron oxide (rust) on Mars's surface gives it its reddish appearance."},
    {"cat": "Science", "diff": "medium", "q": "What is the powerhouse of the eukaryotic cell?", "opts": ["Nucleus", "Ribosome", "Mitochondria", "Golgi Body"], "ans": "Mitochondria", "exp": "Mitochondria generate most of the cell's supply of adenosine triphosphate (ATP)."},
    {"cat": "Science", "diff": "hard", "q": "What is the chemical symbol for Tungsten?", "opts": ["Tu", "Tg", "W", "Tn"], "ans": "W", "exp": "Tungsten's symbol W comes from its German name, Wolfram."},
    {"cat": "History", "diff": "easy", "q": "Which ancient civilization built the Machu Picchu citadel?", "opts": ["Aztec", "Maya", "Inca", "Olmec"], "ans": "Inca", "exp": "Machu Picchu was built in the 15th century by the Inca Empire in Peru."},
    {"cat": "History", "diff": "medium", "q": "In which year did World War II end?", "opts": ["1943", "1944", "1945", "1947"], "ans": "1945", "exp": "World War II ended in September 1945 following the surrender of Japan."},
    {"cat": "History", "diff": "hard", "q": "Who was the founder of the Maurya Empire in ancient India?", "opts": ["Ashoka", "Chandragupta Maurya", "Bindusara", "Samudragupta"], "ans": "Chandragupta Maurya", "exp": "Chandragupta Maurya founded the Maurya Empire around 322 BCE."},
    {"cat": "Geography", "diff": "easy", "q": "What is the largest ocean on Earth?", "opts": ["Atlantic Ocean", "Indian Ocean", "Pacific Ocean", "Arctic Ocean"], "ans": "Pacific Ocean", "exp": "The Pacific Ocean covers more than 30% of the Earth's surface."},
    {"cat": "Geography", "diff": "medium", "q": "Which river flows through the city of Cairo?", "opts": ["Tigris", "Euphrates", "Nile", "Congo"], "ans": "Nile", "exp": "Cairo is located along the Nile River just south of the Nile Delta."},
    {"cat": "Geography", "diff": "hard", "q": "Which country has the most natural lakes in the world?", "opts": ["Finland", "Canada", "Russia", "Brazil"], "ans": "Canada", "exp": "Canada contains over 60% of all the natural lakes in the world."},
    {"cat": "Gaming", "diff": "easy", "q": "Which block-building survival game was created by Markus 'Notch' Persson?", "opts": ["Terraria", "Roblox", "Minecraft", "Fortnite"], "ans": "Minecraft", "exp": "Minecraft was originally created by Markus Persson and released by Mojang."},
    {"cat": "Gaming", "diff": "medium", "q": "In Strategy & Alliance games, what does 'PvE' stand for?", "opts": ["Player vs Enemy", "Player vs Environment", "Point vs Experience", "Power vs Energy"], "ans": "Player vs Environment", "exp": "PvE stands for Player versus Environment (fighting AI/monsters rather than other players)."},
    {"cat": "Gaming", "diff": "hard", "q": "Which game won Game of the Year at The Game Awards 2022?", "opts": ["God of War Ragnarök", "Elden Ring", "Horizon Forbidden West", "Stray"], "ans": "Elden Ring", "exp": "FromSoftware's Elden Ring won Game of the Year in December 2022."},
    {"cat": "Movies", "diff": "easy", "q": "Which movie features the quote 'May the Force be with you'?", "opts": ["Star Trek", "Star Wars", "Avatar", "Dune"], "ans": "Star Wars", "exp": "'May the Force be with you' is the iconic phrase from the Star Wars saga."},
    {"cat": "Movies", "diff": "medium", "q": "Who directed the 2010 sci-fi thriller 'Inception'?", "opts": ["Denis Villeneuve", "Christopher Nolan", "Steven Spielberg", "Ridley Scott"], "ans": "Christopher Nolan", "exp": "Christopher Nolan wrote and directed Inception (2010)."},
    {"cat": "Sports", "diff": "easy", "q": "How many players are on the field for one football (soccer) team during a match?", "opts": ["9", "10", "11", "12"], "ans": "11", "exp": "Each regulation football team fields 11 players including the goalkeeper."},
    {"cat": "Sports", "diff": "medium", "q": "How many runs is a boundary hit over the ropes without bouncing in Cricket?", "opts": ["4", "5", "6", "8"], "ans": "6", "exp": "A ball clearing the boundary on the full scores 6 runs in cricket."},
    {"cat": "Technology", "diff": "easy", "q": "What does 'CPU' stand for in computing?", "opts": ["Central Processing Unit", "Core Power Unit", "Computer Personal Utility", "Central Program Utility"], "ans": "Central Processing Unit", "exp": "The Central Processing Unit is the primary processor executing instructions in a computer."},
    {"cat": "Technology", "diff": "medium", "q": "Which protocol secures HTTP web traffic with encryption?", "opts": ["FTP", "SSH", "HTTPS (TLS)", "SMTP"], "ans": "HTTPS (TLS)", "exp": "HTTPS uses Transport Layer Security (TLS) to encrypt communications."},
]

EMOJI_PUZZLES = [
    {"cat": "Movies", "diff": "easy", "emojis": "🦁 👑", "ans": "The Lion King", "aliases": ["lion king"], "hint": "Animated Disney classic set in the Pride Lands"},
    {"cat": "Movies", "diff": "easy", "emojis": "🕷️ 🧑", "ans": "Spider-Man", "aliases": ["spiderman", "spider man"], "hint": "Friendly neighborhood web-slinger"},
    {"cat": "Movies", "diff": "medium", "emojis": "🚢 🧊 💔", "ans": "Titanic", "aliases": ["the titanic"], "hint": "1997 romance disaster film at sea"},
    {"cat": "Movies", "diff": "hard", "emojis": "🦖 🏞️ 🧬", "ans": "Jurassic Park", "aliases": ["jurassic world"], "hint": "Dinosaurs cloned from prehistoric amber"},
    {"cat": "Games", "diff": "easy", "emojis": "⛏️ 🧱 🧟", "ans": "Minecraft", "aliases": ["mine craft"], "hint": "Blocky survival and crafting sandbox"},
    {"cat": "Games", "diff": "medium", "emojis": "🍄 ⭐ 🏎️", "ans": "Mario Kart", "aliases": ["mariokart", "super mario"], "hint": "Nintendo racing series with power-ups"},
    {"cat": "Animals", "diff": "easy", "emojis": "🐼 🎋", "ans": "Giant Panda", "aliases": ["panda", "panda bear"], "hint": "Black-and-white bear that loves bamboo"},
    {"cat": "Food", "diff": "easy", "emojis": "🥞 🍁", "ans": "Pancakes", "aliases": ["pancake", "maple pancakes"], "hint": "Breakfast stack topped with syrup"},
    {"cat": "Common Phrases", "diff": "medium", "emojis": "🌧️ 🐱 🐶", "ans": "Raining Cats and Dogs", "aliases": ["raining cats & dogs"], "hint": "Idiom meaning a very heavy downpour"},
    {"cat": "Objects", "diff": "easy", "emojis": "⏰ 🔔", "ans": "Alarm Clock", "aliases": ["alarm", "clock"], "hint": "Wakes you up in the morning"},
]


def _shuffle_word(word: str) -> str:
    letters = list(word.upper())
    for _ in range(10):
        random.shuffle(letters)
        if "".join(letters) != word.upper():
            break
    return " ".join(letters)


def _normalize_text(s: str) -> str:
    clean = re.sub(r"[^a-z0-9\s]", "", s.lower()).strip()
    clean = re.sub(r"^(the|a|an)\s+", "", clean)
    return re.sub(r"\s+", " ", clean)


def generate_math_problem(difficulty: str) -> Tuple[str, int]:
    diff = difficulty.lower()
    if diff == "easy":
        op = random.choice(["+", "-"])
        a, b = random.randint(5, 35), random.randint(3, 25)
        if op == "-" and b > a:
            a, b = b, a
        ans = a + b if op == "+" else a - b
        return f"{a} {op} {b}", ans
    elif diff == "medium":
        op = random.choice(["×", "÷"])
        if op == "×":
            a, b = random.randint(4, 14), random.randint(3, 12)
            return f"{a} × {b}", a * b
        else:
            b = random.randint(2, 12)
            ans = random.randint(3, 12)
            a = b * ans
            return f"{a} ÷ {b}", ans
    else:
        a = random.randint(6, 18)
        b = random.randint(3, 12)
        c = random.randint(10, 45)
        op2 = random.choice(["+", "-"])
        val = (a * b) + c if op2 == "+" else (a * b) - c
        return f"({a} × {b}) {op2} {c}", val


# ==============================================================================
# GAME 2: WORD SCRAMBLE
# ==============================================================================

class ScrambleAnswerModal(discord.ui.Modal, title="ROF Word Scramble — Submit Answer"):
    answer_input = discord.ui.TextInput(
        label="Unscrambled Word",
        placeholder="Type your answer here...",
        min_length=2,
        max_length=30,
        required=True,
    )

    def __init__(self, view: "WordScrambleSessionView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        # fix I: guard the modal.
        try:
            await self.view.check_answer(interaction, self.answer_input.value.strip())
        except Exception as e:
            print(f"[SINGLE] ScrambleAnswerModal error: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⚠️ Something went wrong. Please try again.", ephemeral=True
                    )
            except Exception:
                pass


class WordScrambleSessionView(discord.ui.View):
    def __init__(
        self,
        cog: "SinglePlayerGames",
        user: discord.abc.User,
        difficulty: str = "medium",
        round_seconds: int = 35,
        max_rounds: int = 3,
    ):
        # fix A: view must outlive all rounds, not just one.
        super().__init__(timeout=max_rounds * round_seconds + 60)
        self.cog = cog
        self.user = user
        self.difficulty = difficulty.lower()
        self.round_seconds = round_seconds
        self.round_num = 1
        self.max_rounds = max_rounds
        self.score = 0
        self.used_words = set()
        self.hint_used = False
        self.finished = False
        self._ended = False  # fix D: idempotent end guard
        self._lock = asyncio.Lock()  # fix B/C: serialize concurrent callbacks
        self.timer_task: Optional[asyncio.Task] = None
        self._pick_next_word()

    def _pick_next_word(self):
        pool = [
            pair for pair in SCRAMBLE_WORDS.get(self.difficulty, SCRAMBLE_WORDS["medium"])
            if pair[0] not in self.used_words
        ]
        if not pool:
            pool = SCRAMBLE_WORDS["medium"]
        self.answer, self.clue = random.choice(pool)
        self.used_words.add(self.answer)
        self.scrambled = _shuffle_word(self.answer)
        self.hint_used = False
        self.deadline = int(time.time() + self.round_seconds)

    def build_embed(self) -> discord.Embed:
        rem = max(0, int(self.deadline - time.time()))
        mins, secs = divmod(rem, 60)
        hint_line = (
            f"\n💡 **Hint:** {self.clue} (Starts with **`{self.answer[0]}`**)"
            if self.hint_used else ""
        )
        desc = (
            f"**Difficulty:** `{self.difficulty.capitalize()}` | "
            f"**Round:** `{self.round_num} / {self.max_rounds}` | **Score:** `{self.score}`\n\n"
            f"Unscramble the following word:\n"
            f"### `{self.scrambled}`\n"
            f"{hint_line}\n"
            f"⏱️ **Time Remaining:** `{mins:02d}:{secs:02d}` (<t:{self.deadline}:R>)"
        )
        return rof_embed(
            title="🔤 ROF WORD SCRAMBLE",
            description=desc,
            color=ROFColors.ARENA,
            footer_extra=f"Player: {self.user.display_name}",
        )

    @discord.ui.button(label="Submit Answer", style=discord.ButtonStyle.primary, emoji="✍️")
    async def submit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user.id):
            return
        if self._ended:
            return await interaction.response.send_message(
                "⌛ Session has ended.", ephemeral=True
            )
        try:
            await interaction.response.send_modal(ScrambleAnswerModal(self))
        except Exception as e:
            print(f"[SINGLE] scramble send_modal failed: {e}")

    @discord.ui.button(label="Hint", style=discord.ButtonStyle.secondary, emoji="💡")
    async def hint_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user.id):
            return
        # fix K: reject if already ended.
        if self._ended:
            return await interaction.response.send_message(
                "⌛ Session has ended.", ephemeral=True
            )
        self.hint_used = True
        button.disabled = True
        try:
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        except Exception as e:
            print(f"[SINGLE] scramble hint edit failed: {e}")

    async def check_answer(self, interaction: discord.Interaction, guess: str):
        # fix B/D/J: lock + deadline check + idempotent end.
        outcome = "unknown"
        async with self._lock:
            if self._ended:
                outcome = "ended"
            elif time.time() > self.deadline:
                # fix J: strictly reject past deadline even if timer hasn't fired yet.
                self._ended = True
                outcome = "expired"
            elif guess.upper() != self.answer.upper():
                outcome = "wrong"
            else:
                self.score += 15 if not self.hint_used else 10
                if self.round_num >= self.max_rounds:
                    self._ended = True
                    outcome = "final_correct"
                else:
                    self.round_num += 1
                    self._pick_next_word()
                    outcome = "advance"

        if outcome == "ended":
            return await interaction.response.send_message(
                "⌛ Session has already ended.", ephemeral=True
            )
        if outcome == "expired":
            # Kick off the timeout finish outside the lock.
            try:
                await self.end_session(interaction, won=(self.score > 0), timed_out=True)
            except Exception as e:
                print(f"[SINGLE] scramble expired-end failed: {e}")
            return
        if outcome == "wrong":
            return await interaction.response.send_message(
                f"❌ `{guess.upper()}` is not correct! Keep trying!", ephemeral=True
            )
        if outcome == "final_correct":
            if self.timer_task and not self.timer_task.done():
                self.timer_task.cancel()
            await self.end_session(interaction, won=True)
            return
        # outcome == "advance"
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.label == "Hint":
                child.disabled = False
        try:
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        except Exception as e:
            print(f"[SINGLE] scramble advance edit failed: {e}")

    async def run_timer(self, interaction: discord.Interaction):
        try:
            while not self._ended:
                await asyncio.sleep(1.0)
                if self._ended:
                    return
                if time.time() >= self.deadline:
                    # fix D: acquire lock to coordinate with check_answer.
                    async with self._lock:
                        if self._ended:
                            return
                        self._ended = True
                    await self.end_session(interaction, won=(self.score > 0), timed_out=True)
                    return
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[SINGLE] scramble timer error: {type(e).__name__}: {e}")
            traceback.print_exc()

    async def on_timeout(self):
        # fix H: safety net.
        if self._ended:
            return
        try:
            async with self._lock:
                if self._ended:
                    return
                self._ended = True
            if self.timer_task and not self.timer_task.done():
                self.timer_task.cancel()
            await self._send_result_embed(None, won=(self.score > 0), timed_out=True)
        except Exception as e:
            print(f"[SINGLE] scramble on_timeout failed: {e}")

    async def end_session(self, interaction: discord.Interaction, won: bool, timed_out: bool = False):
        self.stop()
        pts = max(5, self.score)

        # fix E: DB must not block the result screen.
        try:
            db.record_game_result(
                user_id=self.user.id,
                game_name="Word Scramble",
                result="win" if won else "loss",
                score=self.score,
                points_earned=pts,
                attempts=self.round_num,
                mode="single",
                username=self.user.display_name,
            )
        except Exception as e:
            print(f"[SINGLE] scramble DB record failed: {type(e).__name__}: {e}")

        # fix F: arcade best-effort.
        arcade = self.cog.bot.get_cog("ArcadeCore")
        if arcade:
            try:
                arcade.reload_cache()
            except Exception as e:
                print(f"[SINGLE] scramble arcade reload failed: {e}")

        await self._send_result_embed(interaction, won, timed_out, pts)

    async def _send_result_embed(self, interaction, won: bool, timed_out: bool, pts: int = None):
        pts = max(5, self.score) if pts is None else pts
        status_line = (
            f"⌛ **Time Expired!** The correct word was **`{self.answer}`**."
            if timed_out
            else f"🎉 **All {self.max_rounds} rounds cleared!** Last word: **`{self.answer}`**."
        )
        embed = rof_embed(
            title="🔤 ROF WORD SCRAMBLE — COMPLETE",
            description=(
                f"{status_line}\n\n"
                f"🏆 **Final Score:** `{self.score}`\n"
                f"🏅 **Arcade Points Earned:** `+{pts} pts`"
            ),
            color=ROFColors.SUCCESS if won else ROFColors.ERROR,
            footer_extra=f"Player: {self.user.display_name}",
        )
        res_view = GameResultView(
            self.user,
            "Word Scramble",
            lambda inter: self.cog.start_word_scramble(inter, self.difficulty),
        )
        try:
            if interaction is None:
                return
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=res_view)
            else:
                await interaction.edit_original_response(embed=embed, view=res_view)
        except Exception as e:
            print(f"[SINGLE] scramble result edit failed: {e}")


# ==============================================================================
# GAME 4: QUICK MATH (60-SECOND SESSION)
# ==============================================================================

class QuickMathModal(discord.ui.Modal, title="ROF Quick Math — Submit Answer"):
    ans_input = discord.ui.TextInput(
        label="Numeric Answer",
        placeholder="e.g., 42 or -5",
        min_length=1,
        max_length=10,
        required=True,
    )

    def __init__(self, view: "QuickMathSessionView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.view.submit_answer(interaction, self.ans_input.value.strip())
        except Exception as e:
            print(f"[SINGLE] QuickMathModal error: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⚠️ Something went wrong. Please try again.", ephemeral=True
                    )
            except Exception:
                pass


class QuickMathSessionView(discord.ui.View):
    def __init__(self, cog: "SinglePlayerGames", user: discord.abc.User, difficulty: str = "medium"):
        super().__init__(timeout=90.0)
        self.cog = cog
        self.user = user
        self.difficulty = difficulty.lower()
        self.session_seconds = 60
        self.start_ts = time.time()
        self.end_ts = int(self.start_ts + self.session_seconds)
        self.score = 0
        self.streak = 0
        self.best_streak = 0
        self.correct_count = 0
        self.total_answered = 0
        self.finished = False
        self._ended = False  # fix D: idempotent end
        self._session_ended = False  # prevent double end_session
        self._lock = asyncio.Lock()
        self.timer_task: Optional[asyncio.Task] = None
        self.question_str, self.correct_answer = generate_math_problem(self.difficulty)

    def build_embed(self, feedback: str = "") -> discord.Embed:
        rem = max(0, int(self.end_ts - time.time()))
        fb_block = f"\n{feedback}\n" if feedback else ""
        desc = (
            f"**Difficulty:** `{self.difficulty.capitalize()}` | "
            f"**Time Remaining:** `{rem}s` (<t:{self.end_ts}:R>)\n"
            f"**Score:** `{self.score}` | **Streak:** 🔥 `{self.streak}`\n"
            f"{fb_block}\n"
            f"Solve this calculation:\n"
            f"## `{self.question_str} = ?`"
        )
        return rof_embed(
            title="🧮 ROF QUICK MATH",
            description=desc,
            color=ROFColors.ARENA,
            footer_extra=f"Player: {self.user.display_name}",
        )

    @discord.ui.button(label="Submit Answer", style=discord.ButtonStyle.primary, emoji="🔢")
    async def answer_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user.id):
            return
        if self._ended or time.time() >= self.end_ts:
            async with self._lock:
                if self._ended:
                    return await interaction.response.send_message(
                        "⌛ Session has ended.", ephemeral=True
                    )
                self._ended = True
            return await self.finish_session(interaction)
        try:
            await interaction.response.send_modal(QuickMathModal(self))
        except Exception as e:
            print(f"[SINGLE] quickmath send_modal failed: {e}")

    @discord.ui.button(label="End Early", style=discord.ButtonStyle.secondary, emoji="⏹️")
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user.id):
            return
        async with self._lock:
            if self._ended:
                return await interaction.response.send_message(
                    "⌛ Session has ended.", ephemeral=True
                )
            self._ended = True
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()
        await self.finish_session(interaction)

    async def submit_answer(self, interaction: discord.Interaction, raw_val: str):
        outcome = "unknown"
        fb = ""
        prev_q = ""
        prev_a = 0
        async with self._lock:
            if self._ended or time.time() >= self.end_ts:
                self._ended = True
                outcome = "ended"
            else:
                try:
                    val = int(raw_val)
                except ValueError:
                    outcome = "invalid"
                else:
                    self.total_answered += 1
                    prev_q = self.question_str
                    prev_a = self.correct_answer
                    if val == self.correct_answer:
                        self.correct_count += 1
                        self.streak += 1
                        self.best_streak = max(self.best_streak, self.streak)
                        mult = {"easy": 10, "medium": 15, "hard": 20}.get(self.difficulty, 15)
                        self.score += mult + min(10, self.streak * 2)
                        fb = f"✅ **Correct!** `{prev_q} = {prev_a}`"
                    else:
                        self.streak = 0
                        fb = f"❌ **Incorrect!** `{prev_q} = {prev_a}` (You answered `{val}`)"
                    self.question_str, self.correct_answer = generate_math_problem(self.difficulty)
                    outcome = "processed"

        if outcome == "ended":
            return await self.finish_session(interaction)
        if outcome == "invalid":
            return await interaction.response.send_message(
                "❌ Please enter a valid whole number.", ephemeral=True
            )
        try:
            await interaction.response.edit_message(embed=self.build_embed(feedback=fb), view=self)
        except Exception as e:
            print(f"[SINGLE] quickmath submit edit failed: {e}")

    async def run_timer(self, interaction: discord.Interaction):
        try:
            # fix M: sleep only the remaining time.
            remaining = self.end_ts - time.time()
            if remaining > 0:
                await asyncio.sleep(remaining)
            async with self._lock:
                if self._ended:
                    return
                self._ended = True
            await self.finish_session(interaction)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[SINGLE] quickmath timer error: {type(e).__name__}: {e}")

    async def on_timeout(self):
        if self._ended:
            return
        try:
            async with self._lock:
                if self._ended:
                    return
                self._ended = True
            if self.timer_task and not self.timer_task.done():
                self.timer_task.cancel()
            await self.finish_session(None)
        except Exception as e:
            print(f"[SINGLE] quickmath on_timeout failed: {e}")

    async def finish_session(self, interaction: Optional[discord.Interaction]):
        # fix D: prevent double end.
        async with self._lock:
            if self._session_ended:
                return
            self._session_ended = True
        self.stop()

        acc = round((self.correct_count / self.total_answered) * 100, 1) if self.total_answered > 0 else 0.0
        won = self.correct_count >= 3
        pts = max(5, self.correct_count * 8)

        try:
            db.record_game_result(
                user_id=self.user.id,
                game_name="Quick Math",
                result="win" if won else "loss",
                score=self.score,
                points_earned=pts,
                attempts=self.total_answered,
                duration_sec=60.0,
                mode="single",
                username=self.user.display_name,
            )
        except Exception as e:
            print(f"[SINGLE] quickmath DB record failed: {type(e).__name__}: {e}")

        arcade = self.cog.bot.get_cog("ArcadeCore")
        if arcade:
            try:
                arcade.reload_cache()
            except Exception as e:
                print(f"[SINGLE] quickmath arcade reload failed: {e}")

        embed = rof_embed(
            title="🧮 ROF QUICK MATH — TIME UP!",
            description=(
                f"🏆 **Final Score:** `{self.score}`\n"
                f"✅ **Correct Answers:** `{self.correct_count} / {self.total_answered}`\n"
                f"🎯 **Accuracy:** `{acc}%`\n"
                f"🔥 **Best Streak:** `{self.best_streak}`\n"
                f"🏅 **Arcade Points Earned:** `+{pts} pts`"
            ),
            color=ROFColors.SUCCESS if won else ROFColors.WARNING,
            footer_extra=f"Player: {self.user.display_name}",
        )
        res_view = GameResultView(
            self.user,
            "Quick Math",
            lambda inter: self.cog.start_quick_math(inter, self.difficulty),
        )
        if interaction is None:
            return
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=res_view)
            else:
                await interaction.edit_original_response(embed=embed, view=res_view)
        except Exception as e:
            print(f"[SINGLE] quickmath result edit failed: {e}")


# ==============================================================================
# GAME 6: TRIVIA
# ==============================================================================

class TriviaSessionView(discord.ui.View):
    def __init__(
        self,
        cog: "SinglePlayerGames",
        user: discord.abc.User,
        category: str = "All",
        difficulty: str = "medium",
        total_questions: int = 5,
    ):
        super().__init__(timeout=180.0)
        self.cog = cog
        self.user = user
        self.category = category
        self.difficulty = difficulty.lower()
        pool = [
            q for q in TRIVIA_BANK
            if (category == "All" or q["cat"].lower() == category.lower())
        ]
        if not pool:
            pool = list(TRIVIA_BANK)
        random.shuffle(pool)
        self.questions = pool[: min(total_questions, len(pool))]
        self.index = 0
        self.score = 0
        self.correct_count = 0
        self.last_explanation = ""
        self._ended = False
        self._lock = asyncio.Lock()
        self._build_option_buttons()

    def _build_option_buttons(self):
        self.clear_items()
        q_item = self.questions[self.index]
        opts = list(q_item["opts"])
        random.shuffle(opts)
        labels = ["A", "B", "C", "D"]
        for i, opt_text in enumerate(opts):
            btn = discord.ui.Button(
                label=f"{labels[i]}: {opt_text}",
                style=discord.ButtonStyle.primary,
                row=i // 2,
            )
            # fix B: capture round_idx so stale clicks are rejected.
            btn.callback = self._make_choice_cb(opt_text, self.index)
            self.add_item(btn)

    def build_embed(self) -> discord.Embed:
        q_item = self.questions[self.index]
        exp_block = f"{self.last_explanation}\n\n" if self.last_explanation else ""
        desc = (
            f"{exp_block}"
            f"**Category:** `{q_item['cat']}` | "
            f"**Question:** `{self.index + 1} / {len(self.questions)}` | "
            f"**Score:** `{self.score}`\n\n"
            f"### {q_item['q']}"
        )
        return rof_embed(
            title="❓ ROF TRIVIA CHALLENGE",
            description=desc,
            color=ROFColors.ARENA,
            footer_extra=f"Player: {self.user.display_name}",
        )

    def _make_choice_cb(self, chosen_opt: str, round_idx: int):
        async def _cb(interaction: discord.Interaction):
            try:
                if not await ensure_session_player(interaction, self.user.id):
                    return
                async with self._lock:
                    if self._ended:
                        return await interaction.response.send_message(
                            "⌛ Trivia session has ended.", ephemeral=True
                        )
                    if self.index != round_idx:
                        return await interaction.response.send_message(
                            "⏭️ That was a previous question — please answer the current one.",
                            ephemeral=True,
                        )
                    q_item = self.questions[self.index]
                    if chosen_opt == q_item["ans"]:
                        self.correct_count += 1
                        self.score += 20
                        self.last_explanation = (
                            f"✅ **Correct!** ({q_item['ans']}) — *{q_item['exp']}*"
                        )
                    else:
                        self.last_explanation = (
                            f"❌ **Incorrect!** Correct answer: **{q_item['ans']}** — "
                            f"*{q_item['exp']}*"
                        )

                    self.index += 1
                    end_game = self.index >= len(self.questions)
                    if end_game:
                        self._ended = True

                if end_game:
                    self.stop()
                    await self.finish_trivia(interaction)
                else:
                    self._build_option_buttons()
                    await interaction.response.edit_message(embed=self.build_embed(), view=self)
            except Exception as e:
                print(f"[SINGLE] trivia callback error: {type(e).__name__}: {e}")
                traceback.print_exc()
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(
                            "⚠️ Something went wrong. Please try again.", ephemeral=True
                        )
                except Exception:
                    pass

        return _cb

    async def on_timeout(self):
        if self._ended:
            return
        self._ended = True
        try:
            for child in self.children:
                try:
                    child.disabled = True
                except Exception:
                    pass
        except Exception:
            pass

    async def finish_trivia(self, interaction: discord.Interaction):
        total = len(self.questions)
        acc = round((self.correct_count / total) * 100, 1) if total else 0.0
        won = self.correct_count >= (total // 2 + 1)
        pts = max(10, self.correct_count * 12)

        try:
            db.record_game_result(
                user_id=self.user.id,
                game_name="Trivia",
                result="win" if won else "loss",
                score=self.score,
                points_earned=pts,
                attempts=total,
                mode="single",
                username=self.user.display_name,
            )
        except Exception as e:
            print(f"[SINGLE] trivia DB record failed: {type(e).__name__}: {e}")

        arcade = self.cog.bot.get_cog("ArcadeCore")
        if arcade:
            try:
                arcade.reload_cache()
            except Exception as e:
                print(f"[SINGLE] trivia arcade reload failed: {e}")

        embed = rof_embed(
            title="❓ ROF TRIVIA — COMPLETE",
            description=(
                f"{self.last_explanation}\n\n"
                f"🏆 **Final Score:** `{self.score}`\n"
                f"✅ **Correct:** `{self.correct_count} / {total}` (`{acc}%` accuracy)\n"
                f"🏅 **Arcade Points Earned:** `+{pts} pts`"
            ),
            color=ROFColors.SUCCESS if won else ROFColors.WARNING,
            footer_extra=f"Player: {self.user.display_name}",
        )
        res_view = GameResultView(
            self.user,
            "Trivia",
            lambda inter: self.cog.start_trivia(inter, self.category, self.difficulty),
        )
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=res_view)
            else:
                await interaction.edit_original_response(embed=embed, view=res_view)
        except Exception as e:
            print(f"[SINGLE] trivia result edit failed: {e}")


# ==============================================================================
# GAME 7: ROCK PAPER SCISSORS (VS BOT)
# ==============================================================================

RPS_CHOICES = {
    "rock": ("🪨", "Rock"),
    "paper": ("📄", "Paper"),
    "scissors": ("✂️", "Scissors"),
}
RPS_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}


class SingleRPSView(discord.ui.View):
    def __init__(self, cog: "SinglePlayerGames", user: discord.abc.User, best_of: int = 3):
        super().__init__(timeout=180.0)
        self.cog = cog
        self.user = user
        self.best_of = best_of
        self.target_wins = (best_of // 2) + 1
        self.player_wins = 0
        self.bot_wins = 0
        self.draws = 0
        self.last_round_text = "Choose your move below!"
        self._ended = False
        self._lock = asyncio.Lock()  # fix C

    def build_embed(self) -> discord.Embed:
        mode_str = f"Best of {self.best_of}" if self.best_of > 1 else "Single Round"
        desc = (
            f"**Format:** `{mode_str}` (First to `{self.target_wins}`)\n"
            f"**Score:** You `{self.player_wins}` — `{self.bot_wins}` ROF Bot "
            f"(Draws: `{self.draws}`)\n\n"
            f"{self.last_round_text}"
        )
        return rof_embed(
            title="✂️ ROF ROCK PAPER SCISSORS",
            description=desc,
            color=ROFColors.ARENA,
            footer_extra=f"Player: {self.user.display_name}",
        )

    @discord.ui.button(label="Rock", style=discord.ButtonStyle.primary, emoji="🪨")
    async def rock_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play_move(interaction, "rock")

    @discord.ui.button(label="Paper", style=discord.ButtonStyle.primary, emoji="📄")
    async def paper_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play_move(interaction, "paper")

    @discord.ui.button(label="Scissors", style=discord.ButtonStyle.primary, emoji="✂️")
    async def scissors_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play_move(interaction, "scissors")

    async def _play_move(self, interaction: discord.Interaction, player_move: str):
        if not await ensure_session_player(interaction, self.user.id):
            return

        # fix C: serialize inside the lock so double-clicks can't register two moves.
        async with self._lock:
            if self._ended:
                return await interaction.response.send_message(
                    "ℹ️ Match has already ended.", ephemeral=True
                )

            bot_move = random.choice(["rock", "paper", "scissors"])
            p_emoji, p_label = RPS_CHOICES[player_move]
            b_emoji, b_label = RPS_CHOICES[bot_move]

            if player_move == bot_move:
                self.draws += 1
                outcome = "🤝 **DRAW ROUND!**"
            elif RPS_BEATS[player_move] == bot_move:
                self.player_wins += 1
                outcome = "🎉 **YOU WIN THE ROUND!**"
            else:
                self.bot_wins += 1
                outcome = "💥 **BOT WINS THE ROUND!**"

            self.last_round_text = (
                f"**Your move:** {p_emoji} {p_label}\n"
                f"**Bot move:** {b_emoji} {b_label}\n"
                f"{outcome}"
            )

            game_over = (
                self.player_wins >= self.target_wins
                or self.bot_wins >= self.target_wins
            )
            if game_over:
                self._ended = True

        if game_over:
            self.stop()
            await self._finish_match(interaction)
        else:
            try:
                await interaction.response.edit_message(embed=self.build_embed(), view=self)
            except Exception as e:
                print(f"[SINGLE] rps round edit failed: {e}")

    async def on_timeout(self):
        if self._ended:
            return
        self._ended = True
        for child in self.children:
            try:
                child.disabled = True
            except Exception:
                pass

    async def _finish_match(self, interaction: discord.Interaction):
        won = self.player_wins > self.bot_wins
        pts = 25 if won else 5

        try:
            db.record_game_result(
                user_id=self.user.id,
                game_name="Rock Paper Scissors",
                result="win" if won else "loss",
                score=self.player_wins * 20,
                points_earned=pts,
                attempts=self.player_wins + self.bot_wins + self.draws,
                mode="single",
                username=self.user.display_name,
            )
        except Exception as e:
            print(f"[SINGLE] rps DB record failed: {type(e).__name__}: {e}")

        arcade = self.cog.bot.get_cog("ArcadeCore")
        if arcade:
            try:
                arcade.reload_cache()
            except Exception as e:
                print(f"[SINGLE] rps arcade reload failed: {e}")

        embed = rof_embed(
            title="✂️ ROF ROCK PAPER SCISSORS — MATCH OVER",
            description=(
                f"{self.last_round_text}\n\n"
                f"🏁 **Final Match Score:** `{self.player_wins} - {self.bot_wins}`\n"
                f"🏆 **Result:** {'YOU WIN!' if won else 'BOT WINS!'}\n"
                f"🏅 **Arcade Points:** `+{pts} pts`"
            ),
            color=ROFColors.SUCCESS if won else ROFColors.ERROR,
            footer_extra=f"Player: {self.user.display_name}",
        )
        res_view = GameResultView(
            self.user,
            "Rock Paper Scissors",
            lambda inter: self.cog.start_rps(inter, self.best_of),
        )
        try:
            await interaction.response.edit_message(embed=embed, view=res_view)
        except Exception as e:
            print(f"[SINGLE] rps final edit failed: {e}")


# ==============================================================================
# GAME 8: NUMBER GUESSING
# ==============================================================================

class NumberGuessModal(discord.ui.Modal, title="ROF Number Guessing — Enter Guess"):
    num_input = discord.ui.TextInput(
        label="Your Number Guess",
        placeholder="Enter a number...",
        min_length=1,
        max_length=5,
        required=True,
    )

    def __init__(self, view: "NumberGuessSessionView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.view.check_guess(interaction, self.num_input.value.strip())
        except Exception as e:
            print(f"[SINGLE] NumberGuessModal error: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⚠️ Something went wrong. Please try again.", ephemeral=True
                    )
            except Exception:
                pass


class NumberGuessSessionView(discord.ui.View):
    def __init__(self, cog: "SinglePlayerGames", user: discord.abc.User, difficulty: str = "medium"):
        super().__init__(timeout=180.0)
        self.cog = cog
        self.user = user
        self.difficulty = difficulty.lower()
        ranges = {"easy": (1, 50, 7), "medium": (1, 100, 7), "hard": (1, 500, 9)}
        self.low, self.high, self.max_attempts = ranges.get(self.difficulty, (1, 100, 7))
        self.secret = random.randint(self.low, self.high)
        self.history: List[Tuple[int, str]] = []
        self._ended = False
        self._lock = asyncio.Lock()  # fix K

    def build_embed(self) -> discord.Embed:
        rem = self.max_attempts - len(self.history)
        hist_str = (
            "\n".join(f"`{g}` → **{hint}**" for g, hint in self.history)
            or "*No guesses yet.*"
        )
        desc = (
            f"**Range:** `{self.low} – {self.high}` | "
            f"**Difficulty:** `{self.difficulty.capitalize()}`\n"
            f"**Attempts Remaining:** `{rem} / {self.max_attempts}`\n\n"
            f"**Previous Guesses:**\n{hist_str}"
        )
        return rof_embed(
            title="🔢 ROF NUMBER GUESSING",
            description=desc,
            color=ROFColors.ARENA,
            footer_extra=f"Player: {self.user.display_name}",
        )

    @discord.ui.button(label="Submit Guess", style=discord.ButtonStyle.primary, emoji="🎯")
    async def guess_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user.id):
            return
        if self._ended:
            return await interaction.response.send_message(
                "⌛ Game has ended.", ephemeral=True
            )
        try:
            await interaction.response.send_modal(NumberGuessModal(self))
        except Exception as e:
            print(f"[SINGLE] numberguess send_modal failed: {e}")

    async def on_timeout(self):
        if self._ended:
            return
        self._ended = True
        for child in self.children:
            try:
                child.disabled = True
            except Exception:
                pass

    async def check_guess(self, interaction: discord.Interaction, raw_val: str):
        won = False
        exhausted = False
        async with self._lock:
            if self._ended:
                return await interaction.response.send_message(
                    "⌛ Game has already ended.", ephemeral=True
                )
            try:
                g = int(raw_val)
            except ValueError:
                return await interaction.response.send_message(
                    "❌ Please enter a valid integer.", ephemeral=True
                )
            if g < self.low or g > self.high:
                return await interaction.response.send_message(
                    f"⚠️ Guess must be between **{self.low}** and **{self.high}**.",
                    ephemeral=True,
                )

            if g == self.secret:
                self.history.append((g, "🎯 EXACT MATCH!"))
                won = True
                self._ended = True
            elif g < self.secret:
                self.history.append((g, "⬆️ HIGHER"))
                if len(self.history) >= self.max_attempts:
                    exhausted = True
                    self._ended = True
            else:
                self.history.append((g, "⬇️ LOWER"))
                if len(self.history) >= self.max_attempts:
                    exhausted = True
                    self._ended = True

        if won:
            await self._finish(interaction, won=True)
        elif exhausted:
            await self._finish(interaction, won=False)
        else:
            try:
                await interaction.response.edit_message(embed=self.build_embed(), view=self)
            except Exception as e:
                print(f"[SINGLE] numberguess edit failed: {e}")

    async def _finish(self, interaction: discord.Interaction, won: bool):
        self.stop()
        used = len(self.history)
        pts = max(15, 50 - (used - 1) * 5) if won else 5
        score = max(10, 100 - (used - 1) * 12) if won else 0

        try:
            db.record_game_result(
                user_id=self.user.id,
                game_name="Number Guessing",
                result="win" if won else "loss",
                score=score,
                points_earned=pts,
                attempts=used,
                mode="single",
                username=self.user.display_name,
            )
        except Exception as e:
            print(f"[SINGLE] numberguess DB record failed: {type(e).__name__}: {e}")

        arcade = self.cog.bot.get_cog("ArcadeCore")
        if arcade:
            try:
                arcade.reload_cache()
            except Exception as e:
                print(f"[SINGLE] numberguess arcade reload failed: {e}")

        embed = rof_embed(
            title="🔢 ROF NUMBER GUESSING — RESULT",
            description=(
                f"{'🎉 **YOU FOUND THE NUMBER!**' if won else '❌ **OUT OF ATTEMPTS!**'}\n\n"
                f"🔓 **Secret Number:** `{self.secret}`\n"
                f"🎯 **Attempts Used:** `{used} / {self.max_attempts}`\n"
                f"🏅 **Arcade Points Earned:** `+{pts} pts`"
            ),
            color=ROFColors.SUCCESS if won else ROFColors.ERROR,
            footer_extra=f"Player: {self.user.display_name}",
        )
        res_view = GameResultView(
            self.user,
            "Number Guessing",
            lambda inter: self.cog.start_number_guessing(inter, self.difficulty),
        )
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=res_view)
            else:
                await interaction.edit_original_response(embed=embed, view=res_view)
        except Exception as e:
            print(f"[SINGLE] numberguess result edit failed: {e}")


# ==============================================================================
# GAME 9: EMOJI GUESSING
# ==============================================================================

class EmojiGuessModal(discord.ui.Modal, title="ROF Emoji Guessing — Submit Answer"):
    ans_input = discord.ui.TextInput(
        label="Your Answer",
        placeholder="e.g., The Lion King",
        min_length=2,
        max_length=50,
        required=True,
    )

    def __init__(self, view: "EmojiGuessSessionView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.view.check_answer(interaction, self.ans_input.value.strip())
        except Exception as e:
            print(f"[SINGLE] EmojiGuessModal error: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⚠️ Something went wrong. Please try again.", ephemeral=True
                    )
            except Exception:
                pass


class EmojiGuessSessionView(discord.ui.View):
    def __init__(self, cog: "SinglePlayerGames", user: discord.abc.User, category: str = "All"):
        super().__init__(timeout=180.0)
        self.cog = cog
        self.user = user
        self.category = category
        pool = [
            p for p in EMOJI_PUZZLES
            if category == "All" or p["cat"].lower() == category.lower()
        ]
        if not pool:
            pool = list(EMOJI_PUZZLES)
        self.puzzle = random.choice(pool)
        self.max_attempts = 3
        self.attempts = 0
        self.hint_shown = False
        self._ended = False
        self._lock = asyncio.Lock()  # fix L

    def build_embed(self, feedback: str = "") -> discord.Embed:
        rem = self.max_attempts - self.attempts
        hint_line = f"\n💡 **Hint:** {self.puzzle['hint']}" if self.hint_shown else ""
        fb_line = f"\n{feedback}\n" if feedback else ""
        desc = (
            f"**Category:** `{self.puzzle['cat']}` | "
            f"**Attempts Remaining:** `{rem} / {self.max_attempts}`\n"
            f"{fb_line}\n"
            f"Identify this puzzle from the emojis:\n"
            f"# {self.puzzle['emojis']}"
            f"{hint_line}"
        )
        return rof_embed(
            title="🎭 ROF EMOJI GUESSING",
            description=desc,
            color=ROFColors.ARENA,
            footer_extra=f"Player: {self.user.display_name}",
        )

    @discord.ui.button(label="Submit Answer", style=discord.ButtonStyle.primary, emoji="✍️")
    async def submit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user.id):
            return
        if self._ended:
            return await interaction.response.send_message(
                "⌛ Game has ended.", ephemeral=True
            )
        try:
            await interaction.response.send_modal(EmojiGuessModal(self))
        except Exception as e:
            print(f"[SINGLE] emojiguess send_modal failed: {e}")

    @discord.ui.button(label="Hint", style=discord.ButtonStyle.secondary, emoji="💡")
    async def hint_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user.id):
            return
        if self._ended:
            return await interaction.response.send_message(
                "⌛ Game has ended.", ephemeral=True
            )
        self.hint_shown = True
        button.disabled = True
        try:
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        except Exception as e:
            print(f"[SINGLE] emojiguess hint edit failed: {e}")

    async def on_timeout(self):
        if self._ended:
            return
        self._ended = True
        for child in self.children:
            try:
                child.disabled = True
            except Exception:
                pass

    async def check_answer(self, interaction: discord.Interaction, raw_ans: str):
        won = False
        out_of_attempts = False
        async with self._lock:
            if self._ended:
                return await interaction.response.send_message(
                    "⌛ Game has already ended.", ephemeral=True
                )
            norm_guess = _normalize_text(raw_ans)
            valid_targets = (
                {_normalize_text(self.puzzle["ans"])}
                | {_normalize_text(a) for a in self.puzzle.get("aliases", [])}
            )
            self.attempts += 1
            if norm_guess in valid_targets:
                won = True
                self._ended = True
            elif self.attempts >= self.max_attempts:
                out_of_attempts = True
                self._ended = True

        if won:
            await self._finish(interaction, won=True)
        elif out_of_attempts:
            await self._finish(interaction, won=False)
        else:
            try:
                await interaction.response.edit_message(
                    embed=self.build_embed(feedback=f"❌ `{raw_ans}` is not correct! Try again."),
                    view=self,
                )
            except Exception as e:
                print(f"[SINGLE] emojiguess wrong-answer edit failed: {e}")

    async def _finish(self, interaction: discord.Interaction, won: bool):
        self.stop()
        pts = (25 if not self.hint_shown else 15) if won else 5
        score = pts * 2 if won else 0

        try:
            db.record_game_result(
                user_id=self.user.id,
                game_name="Emoji Guessing",
                result="win" if won else "loss",
                score=score,
                points_earned=pts,
                attempts=self.attempts,
                mode="single",
                username=self.user.display_name,
            )
        except Exception as e:
            print(f"[SINGLE] emojiguess DB record failed: {type(e).__name__}: {e}")

        arcade = self.cog.bot.get_cog("ArcadeCore")
        if arcade:
            try:
                arcade.reload_cache()
            except Exception as e:
                print(f"[SINGLE] emojiguess arcade reload failed: {e}")

        embed = rof_embed(
            title="🎭 ROF EMOJI GUESSING — RESULT",
            description=(
                f"# {self.puzzle['emojis']}\n"
                f"{'🎉 **CORRECT!**' if won else '❌ **OUT OF ATTEMPTS!**'}\n\n"
                f"✅ **Answer:** **{self.puzzle['ans']}**\n"
                f"🎯 **Attempts Used:** `{self.attempts} / {self.max_attempts}`\n"
                f"🏅 **Arcade Points:** `+{pts} pts`"
            ),
            color=ROFColors.SUCCESS if won else ROFColors.ERROR,
            footer_extra=f"Player: {self.user.display_name}",
        )
        res_view = GameResultView(
            self.user,
            "Emoji Guessing",
            lambda inter: self.cog.start_emoji_guessing(inter, self.category),
        )
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=res_view)
            else:
                await interaction.edit_original_response(embed=embed, view=res_view)
        except Exception as e:
            print(f"[SINGLE] emojiguess result edit failed: {e}")


# ==============================================================================
# COG
# ==============================================================================

class SinglePlayerGames(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def launch_word_scramble(self, interaction: discord.Interaction):
        view = GameStartView(
            user=interaction.user,
            game_title="ROF WORD SCRAMBLE",
            short_desc="Rearrange mixed-up letters to identify the original word across 3 rounds.",
            how_to_play="1. Select your difficulty.\n2. Click **Start Game**.\n3. Unscramble the letters and submit your answer before time runs out!",
            timer_info="35 seconds per word • Optional Hints",
            start_callback=self.start_word_scramble,
            difficulties=["Easy", "Medium", "Hard"],
        )
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    async def start_word_scramble(self, interaction: discord.Interaction, difficulty: str = "medium"):
        view = WordScrambleSessionView(self, interaction.user, difficulty=difficulty)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)
        view.timer_task = asyncio.create_task(view.run_timer(interaction))

    async def launch_quick_math(self, interaction: discord.Interaction):
        view = GameStartView(
            user=interaction.user,
            game_title="ROF QUICK MATH",
            short_desc="Solve as many mathematical questions as possible in 60 seconds!",
            how_to_play="1. Select Easy (+, -), Medium (×, ÷), or Hard (Mixed).\n2. Click **Start Game**.\n3. Submit answers rapidly to build your streak and score!",
            timer_info="60-second sprint • Streak bonuses",
            start_callback=self.start_quick_math,
            difficulties=["Easy", "Medium", "Hard"],
        )
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    async def start_quick_math(self, interaction: discord.Interaction, difficulty: str = "medium"):
        view = QuickMathSessionView(self, interaction.user, difficulty=difficulty)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)
        view.timer_task = asyncio.create_task(view.run_timer(interaction))

    async def launch_trivia(self, interaction: discord.Interaction):
        view = GameStartView(
            user=interaction.user,
            game_title="ROF TRIVIA CHALLENGE",
            short_desc="Test your knowledge across Science, History, Geography, Gaming, Movies, Sports, and Tech!",
            how_to_play="1. Choose a difficulty.\n2. Click **Start Game**.\n3. Select one of the 4 answer buttons for each question.",
            timer_info="5 Questions per session • Instant explanations",
            start_callback=lambda inter, diff: self.start_trivia(inter, "All", diff),
            difficulties=["Easy", "Medium", "Hard"],
        )
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    async def start_trivia(self, interaction: discord.Interaction, category: str = "All", difficulty: str = "medium"):
        view = TriviaSessionView(self, interaction.user, category=category, difficulty=difficulty)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    async def launch_rps(self, interaction: discord.Interaction):
        view = GameStartView(
            user=interaction.user,
            game_title="ROF ROCK PAPER SCISSORS",
            short_desc="Face off against the ROF Bot in Rock Paper Scissors!",
            how_to_play="1. Select match length (Single, Best of 3, or Best of 5).\n2. Choose Rock, Paper, or Scissors each round.",
            timer_info="Best of 1 / Best of 3 / Best of 5",
            # fix G: normalize difficulty case before dict lookup.
            start_callback=lambda inter, diff: self.start_rps(
                inter,
                {"easy": 1, "medium": 3, "hard": 5}.get(
                    (diff or "medium").lower(), 3
                ),
            ),
            difficulties=["Easy", "Medium", "Hard"],
            default_difficulty="Medium",
        )
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    async def start_rps(self, interaction: discord.Interaction, best_of: int = 3):
        view = SingleRPSView(self, interaction.user, best_of=best_of)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    async def launch_number_guessing(self, interaction: discord.Interaction):
        view = GameStartView(
            user=interaction.user,
            game_title="ROF NUMBER GUESSING",
            short_desc="Find the secret number using HIGHER and LOWER clues!",
            how_to_play="1. Choose Easy (1–50), Medium (1–100), or Hard (1–500).\n2. Submit guesses to narrow down the exact secret number.",
            timer_info="7–9 attempts • Higher/Lower guidance",
            start_callback=self.start_number_guessing,
            difficulties=["Easy", "Medium", "Hard"],
        )
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    async def start_number_guessing(self, interaction: discord.Interaction, difficulty: str = "medium"):
        view = NumberGuessSessionView(self, interaction.user, difficulty=difficulty)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    async def launch_emoji_guessing(self, interaction: discord.Interaction):
        view = GameStartView(
            user=interaction.user,
            game_title="ROF EMOJI GUESSING",
            short_desc="Identify the movie, game, animal, food, phrase, or object from emojis!",
            how_to_play="1. Click **Start Game**.\n2. Study the emoji puzzle.\n3. Submit your answer or request a hint!",
            timer_info="3 attempts per puzzle • Optional Hint",
            start_callback=lambda inter, _diff: self.start_emoji_guessing(inter, "All"),
        )
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    async def start_emoji_guessing(self, interaction: discord.Interaction, category: str = "All"):
        view = EmojiGuessSessionView(self, interaction.user, category=category)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


async def setup(bot):
    await bot.add_cog(SinglePlayerGames(bot))