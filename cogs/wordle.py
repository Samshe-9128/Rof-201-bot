# cogs/wordle.py
import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import random
import traceback
import difflib
import time
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

from core.config import BASE_DIR, OWNER_ID, ROFColors
from core.database import db

load_dotenv()

GREEN = '🟩'
YELLOW = '🟨'
GREY = '⬛'
EMPTY = '⬜'

ANSWERS_FILE = os.path.join(BASE_DIR, 'wordle_answers.txt')
VALID_FILE = os.path.join(BASE_DIR, 'wordle_valid.txt')
STATS_FILE = os.path.join(BASE_DIR, 'wordle_stats.json')
GAMES_FILE = os.path.join(BASE_DIR, 'wordle_games.json')
DAILY_FILE = os.path.join(BASE_DIR, 'wordle_daily.json')
APPROVED_FILE = os.path.join(BASE_DIR, 'approved.json')

GUESS_COOLDOWN_SEC = 2


# ---------- helpers ----------

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return default
    return default


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_word_list(path):
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return [w.strip().lower() for w in f if len(w.strip()) == 5 and w.strip().isalpha()]


def is_authorized(user_id):
    if OWNER_ID and int(user_id) == int(OWNER_ID):
        return True
    if int(user_id) in load_json(APPROVED_FILE, []):
        return True
    # Allow alliance members when wordle_open_to_all is enabled in config
    return db.get_config("wordle_open_to_all", "true").lower() == "true"


def evaluate_guess(guess, answer):
    """Wordle scoring with correct repeated-letter handling."""
    result = [GREY] * 5
    a = list(answer)
    g = list(guess)
    for i in range(5):
        if g[i] == a[i]:
            result[i] = GREEN
            a[i] = None
            g[i] = None
    for i in range(5):
        if g[i] is not None and g[i] in a:
            result[i] = YELLOW
            a[a.index(g[i])] = None
    return result


# ---------- modal ----------

class GuessModal(discord.ui.Modal, title="ROF Wordle — Enter your guess"):
    guess_input = discord.ui.TextInput(
        label="Your 5-letter guess",
        placeholder="Any 5 letters — probe words welcome!",
        min_length=5,
        max_length=5,
        required=True,
    )

    def __init__(self, cog, user_id, mode):
        super().__init__()
        self.cog = cog
        self.user_id = user_id
        self.mode = mode

    async def on_submit(self, interaction: discord.Interaction):
        word = (self.guess_input.value or "").strip().lower()
        try:
            await self.cog.process_guess(interaction, self.user_id, self.mode, word)
        except Exception as e:
            print(f"[WORDLE] modal submit error: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                await interaction.response.send_message(
                    "❌ An unexpected error occurred while checking your guess. Please try again.",
                    ephemeral=True,
                )
            except Exception:
                pass


# ---------- views ----------

class ShareResultView(discord.ui.View):
    """Preserved ShareResultView enhanced with Play Again (Practice) and Statistics buttons."""

    def __init__(self, cog, game, mode, stats, user_id: int = 0):
        super().__init__(timeout=600)
        self.cog = cog
        self.game = game
        self.mode = mode
        self.stats = stats
        self.user_id = user_id

    @discord.ui.button(label="Share Result", style=discord.ButtonStyle.success, emoji="📋")
    async def share_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        text = self.cog.format_share_text(self.game, self.mode, self.stats)
        await interaction.response.send_message(
            "Copy the block below and paste it anywhere:\n\n"
            f"```\n{text}\n```",
            ephemeral=True,
        )

    @discord.ui.button(label="New Practice Game", style=discord.ButtonStyle.primary, emoji="🔄")
    async def new_practice_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_id and interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        await self.cog.start_game(interaction, 'practice', force_new=True)

    @discord.ui.button(label="Statistics", style=discord.ButtonStyle.secondary, emoji="📊")
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.send_user_stats(interaction)


class WordleGameView(discord.ui.View):
    def __init__(self, cog, user_id, mode):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.mode = mode

    @discord.ui.button(label="Type Guess", style=discord.ButtonStyle.primary, emoji="⌨️")
    async def guess_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return
        try:
            await interaction.response.send_modal(GuessModal(self.cog, self.user_id, self.mode))
        except Exception as e:
            print(f"[WORDLE] send_modal failed: {e}")

    @discord.ui.button(label="Give Up", style=discord.ButtonStyle.danger, emoji="🏳️")
    async def giveup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return
        try:
            await self.cog.give_up(interaction, self.user_id, self.mode)
        except Exception as e:
            print(f"[WORDLE] give_up failed: {e}")


# ---------- cog ----------

class Wordle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.answers = load_word_list(ANSWERS_FILE)
        # Valid list kept only for optional friendlier messaging / suggestions.
        self.valid_words = set(self.answers) | set(load_word_list(VALID_FILE))
        self.stats = load_json(STATS_FILE, {})
        self.games = load_json(GAMES_FILE, {})
        self.daily = load_json(DAILY_FILE, {})
        self.last_guess = {}

        print(f"[WORDLE] Loaded {len(self.answers)} answers, {len(self.valid_words)} valid words")

    # ---------- time ----------

    def _today_str(self):
        return datetime.now(timezone.utc).strftime('%Y-%m-%d')

    def _next_reset_delta(self):
        now = datetime.now(timezone.utc)
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return tomorrow - now

    def _format_countdown(self):
        d = self._next_reset_delta()
        total = int(d.total_seconds())
        h, m = total // 3600, (total % 3600) // 60
        return f"{h}h {m}m"

    # ---------- storage ----------

    def _get_daily_answer(self):
        today = self._today_str()
        if today not in self.daily:
            if not self.answers:
                return None
            self.daily[today] = random.choice(self.answers)
            save_json(DAILY_FILE, self.daily)
        return self.daily[today]

    def _get_game(self, user_id, mode):
        return self.games.get(str(user_id), {}).get(mode)

    def _save_game(self, user_id, mode, game):
        uid = str(user_id)
        self.games.setdefault(uid, {})[mode] = game
        save_json(GAMES_FILE, self.games)

    def _get_stats(self, user_id):
        uid = str(user_id)
        if uid not in self.stats:
            self.stats[uid] = {
                'games_played': 0,
                'wins': 0,
                'current_streak': 0,
                'max_streak': 0,
                'last_won_date': None,
                'guess_distribution': [0, 0, 0, 0, 0, 0],
                'total_guesses_on_win': 0,
            }
        self.stats[uid].setdefault('total_guesses_on_win', 0)
        return self.stats[uid]

    def _save_stats(self):
        save_json(STATS_FILE, self.stats)

    # ---------- rendering ----------

    def _render_board(self, guesses, answer):
        lines = []
        for guess in guesses:
            result = evaluate_guess(guess, answer)
            cells = [f"**{c.upper()}**{result[i]}" for i, c in enumerate(guess)]
            lines.append(' '.join(cells))
        for _ in range(6 - len(guesses)):
            lines.append(f"{EMPTY} {EMPTY} {EMPTY} {EMPTY} {EMPTY}")
        return '\n'.join(lines)

    def _render_keyboard(self, guesses, answer):
        status = {}
        for guess in guesses:
            result = evaluate_guess(guess, answer)
            for i, c in enumerate(guess):
                if result[i] == GREEN:
                    status[c] = GREEN
                elif result[i] == YELLOW and status.get(c) != GREEN:
                    status[c] = YELLOW
                elif c not in status:
                    status[c] = GREY

        rows = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm']
        out = []
        for row in rows:
            parts = []
            for c in row:
                s = status.get(c, EMPTY)
                parts.append(f"`{c.upper()}`{s}")
            out.append(' '.join(parts))
        return '\n'.join(out)

    def _build_embed(self, mode, game, user_id=None):
        title = "ROF Wordle — Daily" if mode == 'daily' else "ROF Wordle — Practice"
        embed = discord.Embed(title=title, color=ROFColors.ARENA)
        embed.description = self._render_board(game['guesses'], game['answer'])

        if game['guesses']:
            embed.add_field(
                name="Keyboard",
                value=self._render_keyboard(game['guesses'], game['answer']),
                inline=False,
            )

        embed.add_field(name="Attempts", value=f"**{len(game['guesses'])} / 6**", inline=True)

        if game.get('finished'):
            if game.get('won'):
                embed.color = ROFColors.SUCCESS
                embed.add_field(
                    name="Result",
                    value=f"🎉 **WIN! Correct in {len(game['guesses'])} guesses!** (Word: **{game['answer'].upper()}**)",
                    inline=False,
                )
            else:
                embed.color = ROFColors.ERROR
                embed.add_field(
                    name="Result",
                    value=f"❌ **GAME OVER.** The word was **{game['answer'].upper()}**",
                    inline=False,
                )

            if user_id is not None:
                stats = self._get_stats(user_id)
                if mode == 'daily' and stats['games_played'] > 0:
                    wr = round(stats['wins'] / stats['games_played'] * 100)
                    embed.add_field(
                        name="Your Stats",
                        value=(
                            f"🔥 Streak: **{stats['current_streak']}** | "
                            f"🏆 Best: **{stats['max_streak']}** | "
                            f"📊 Win rate: **{wr}%**"
                        ),
                        inline=False,
                    )
        else:
            if mode == 'daily':
                embed.set_footer(text=f"Next word in {self._format_countdown()} • ROF Gaming Arena")
            else:
                embed.set_footer(text="ROF Gaming Arena • Unlimited Practice")
        return embed

    def format_share_text(self, game, mode, stats=None):
        date = game['date']
        gs = game['guesses']
        won = game.get('won', False)

        lines = []
        header = f"ROF Wordle {date}" if mode == 'daily' else "ROF Wordle — Practice"
        lines.append(header)

        score = f"{len(gs)}/6" if won else "X/6"
        if mode == 'daily' and stats:
            streak = stats.get('current_streak', 0)
            if won and streak > 0:
                score += f"  🔥{streak}"
        lines.append(score)
        lines.append("")

        for guess in gs:
            result = evaluate_guess(guess, game['answer'])
            lines.append(''.join(result))

        return '\n'.join(lines)

    def _suggest_words(self, word, n=3):
        """Optional helper — not used to block guesses anymore, only for info hints."""
        try:
            return difflib.get_close_matches(word, list(self.valid_words), n=n, cutoff=0.5)
        except Exception:
            return []

    # ---------- game flow ----------

    async def start_game(self, interaction, mode, force_new=False):
        if not self.answers:
            await interaction.response.send_message(
                "⚠️ Wordle is not set up (missing `wordle_answers.txt`).", ephemeral=True
            )
            return

        user_id = interaction.user.id
        game = self._get_game(user_id, mode)

        if mode == 'daily':
            today = self._today_str()
            answer = self._get_daily_answer()

            if game and game.get('date') == today and game.get('finished'):
                stats = self._get_stats(user_id)
                embed = discord.Embed(
                    title="✅ Already played today",
                    description=(
                        f"Today's word was **{game['answer'].upper()}**.\n"
                        f"🔥 Streak: **{stats['current_streak']}** | "
                        f"🏆 Best: **{stats['max_streak']}**\n\n"
                        f"⏳ Next word in **{self._format_countdown()}**"
                    ),
                    color=ROFColors.WARNING,
                )
                view = ShareResultView(self, game, mode, stats, user_id=user_id)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return

            if not game or game.get('date') != today:
                game = {
                    'date': today,
                    'answer': answer,
                    'guesses': [],
                    'finished': False,
                    'won': False,
                }
                self._save_game(user_id, mode, game)
        else:
            if force_new or not game or game.get('finished'):
                game = {
                    'date': self._today_str(),
                    'answer': random.choice(self.answers),
                    'guesses': [],
                    'finished': False,
                    'won': False,
                }
                self._save_game(user_id, mode, game)

        await self._send_board(interaction, user_id, mode, game)

    async def _send_board(self, interaction, user_id, mode, game):
        embed = self._build_embed(mode, game, user_id)
        view = None if game.get('finished') else WordleGameView(self, user_id, mode)

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except discord.HTTPException as e:
            print(f"[WORDLE] send board failed: {e}")

    def _check_cooldown(self, user_id):
        now = time.time()
        last = self.last_guess.get(user_id, 0)
        if now - last < GUESS_COOLDOWN_SEC:
            return int(GUESS_COOLDOWN_SEC - (now - last) + 1)
        self.last_guess[user_id] = now
        return 0

    async def process_guess(self, interaction, user_id, mode, word):
        wait = self._check_cooldown(user_id)
        if wait > 0:
            await interaction.response.send_message(
                f"⏳ Slow down — try again in {wait}s.", ephemeral=True
            )
            return

        # Accept ANY 5-letter alphabetic word as a guess.
        # Players often use probe/trick words (not real dictionary words)
        # to test letters — do NOT block them.
        if not word or len(word) != 5 or not word.isalpha():
            await interaction.response.send_message(
                f"❌ Must be **exactly 5 letters** (A–Z only). "
                f"You sent: `{word or '(empty)'}`",
                ephemeral=True,
            )
            return

        game = self._get_game(user_id, mode)
        if not game:
            await interaction.response.send_message(
                "No active game. Use `/wordle` or `/wordle_practice` first.", ephemeral=True
            )
            return
        if game.get('finished'):
            await interaction.response.send_message("This game is already finished.", ephemeral=True)
            return
        if word in game['guesses']:
            await interaction.response.send_message(
                f"❌ You already guessed **{word.upper()}**.", ephemeral=True
            )
            return

        game['guesses'].append(word)

        if word == game['answer']:
            game['finished'] = True
            game['won'] = True
            self._update_stats_on_finish(user_id, mode, game, interaction.user.display_name)
        elif len(game['guesses']) >= 6:
            game['finished'] = True
            game['won'] = False
            self._update_stats_on_finish(user_id, mode, game, interaction.user.display_name)

        self._save_game(user_id, mode, game)

        embed = self._build_embed(mode, game, user_id)
        if game.get('finished'):
            view = ShareResultView(self, game, mode, self._get_stats(user_id), user_id=user_id)
        else:
            view = WordleGameView(self, user_id, mode)

        await self._safe_edit(interaction, embed, view)

    async def give_up(self, interaction, user_id, mode):
        game = self._get_game(user_id, mode)
        if not game or game.get('finished'):
            await interaction.response.send_message("No active game.", ephemeral=True)
            return
        game['finished'] = True
        game['won'] = False
        self._update_stats_on_finish(user_id, mode, game, interaction.user.display_name)
        self._save_game(user_id, mode, game)
        embed = self._build_embed(mode, game, user_id)
        view = ShareResultView(self, game, mode, self._get_stats(user_id), user_id=user_id)
        await self._safe_edit(interaction, embed, view)

    async def _safe_edit(self, interaction, embed, view):
        try:
            await interaction.response.edit_message(embed=embed, view=view)
            return
        except discord.InteractionResponded:
            pass
        except Exception as e:
            print(f"[WORDLE] edit_message failed: {type(e).__name__}: {e}")

        try:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            return
        except Exception as e:
            print(f"[WORDLE] followup failed: {type(e).__name__}: {e}")

        try:
            if interaction.message:
                await interaction.message.edit(embed=embed, view=view)
                return
        except Exception as e:
            print(f"[WORDLE] message.edit failed: {type(e).__name__}: {e}")

    def _update_stats_on_finish(self, user_id, mode, game, username=""):
        won = bool(game.get('won'))
        attempts = len(game.get('guesses', []))
        pts = max(15, 60 - (attempts - 1) * 8) if won else 5
        score = (7 - attempts) * 20 if won else 0

        # Record into unified ROF database & ArcadeCore
        db.record_game_result(
            user_id=user_id,
            game_name="Wordle",
            result="win" if won else "loss",
            score=score,
            points_earned=pts,
            attempts=attempts,
            mode=mode,
            username=username,
        )
        arcade = self.bot.get_cog("ArcadeCore")
        if arcade:
            arcade.reload_cache()

        if mode != 'daily':
            return
        stats = self._get_stats(user_id)
        stats['games_played'] += 1

        if won:
            stats['wins'] += 1
            n = len(game['guesses'])
            if 1 <= n <= 6:
                stats['guess_distribution'][n - 1] += 1
            stats['total_guesses_on_win'] += n

            today = self._today_str()
            last = stats.get('last_won_date')
            if last:
                try:
                    diff = (
                        datetime.strptime(today, '%Y-%m-%d').date()
                        - datetime.strptime(last, '%Y-%m-%d').date()
                    ).days
                    if diff == 1:
                        stats['current_streak'] += 1
                    elif diff > 1:
                        stats['current_streak'] = 1
                except ValueError:
                    stats['current_streak'] = 1
            else:
                stats['current_streak'] = 1

            stats['last_won_date'] = today
            stats['max_streak'] = max(stats['max_streak'], stats['current_streak'])
        else:
            stats['current_streak'] = 0

        self._save_stats()

    async def send_user_stats(self, interaction: discord.Interaction):
        stats = self._get_stats(interaction.user.id)
        embed = discord.Embed(
            title=f"📊 {interaction.user.display_name}'s Wordle Stats",
            color=ROFColors.ARENA,
        )
        played, wins = stats['games_played'], stats['wins']
        win_rate = round(wins / played * 100) if played else 0
        avg = round(stats['total_guesses_on_win'] / wins, 2) if wins else 0

        embed.add_field(name="Played", value=str(played), inline=True)
        embed.add_field(name="Wins", value=str(wins), inline=True)
        embed.add_field(name="Win Rate", value=f"{win_rate}%", inline=True)
        embed.add_field(name="Current Streak", value=f"🔥 {stats['current_streak']}", inline=True)
        embed.add_field(name="Max Streak", value=f"🏆 {stats['max_streak']}", inline=True)
        embed.add_field(name="Avg. Guesses", value=str(avg) if wins else "—", inline=True)

        dist = stats['guess_distribution']
        if any(dist):
            peak = max(dist) or 1
            bar_lines = []
            for i, c in enumerate(dist):
                bar = '█' * max(1, int(c / peak * 10)) if c else ''
                bar_lines.append(f"`{i+1}` {bar} **{c}**")
            embed.add_field(name="Guess Distribution", value='\n'.join(bar_lines), inline=False)
        else:
            embed.add_field(name="Guess Distribution", value="No wins yet.", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------- commands ----------

    @app_commands.command(name="wordle", description="Play today's daily Wordle")
    async def wordle_cmd(self, interaction: discord.Interaction):
        if not is_authorized(interaction.user.id):
            await interaction.response.send_message("You are not authorized! 🔒", ephemeral=True)
            return
        await self.start_game(interaction, 'daily')

    @app_commands.command(name="wordle_practice", description="Play unlimited practice Wordle")
    async def wordle_practice_cmd(self, interaction: discord.Interaction):
        if not is_authorized(interaction.user.id):
            await interaction.response.send_message("You are not authorized! 🔒", ephemeral=True)
            return
        await self.start_game(interaction, 'practice')

    @app_commands.command(name="wordle_stats", description="View your Wordle statistics")
    async def wordle_stats_cmd(self, interaction: discord.Interaction):
        if not is_authorized(interaction.user.id):
            await interaction.response.send_message("You are not authorized! 🔒", ephemeral=True)
            return
        await self.send_user_stats(interaction)

    @app_commands.command(name="wordle_leaderboard", description="View the ROF Wordle leaderboard")
    async def wordle_leaderboard_cmd(self, interaction: discord.Interaction):
        if not is_authorized(interaction.user.id):
            await interaction.response.send_message("You are not authorized! 🔒", ephemeral=True)
            return
        entries = [(uid, s) for uid, s in self.stats.items() if s.get('games_played', 0) > 0]
        if not entries:
            await interaction.response.send_message("No games played yet. Be the first!", ephemeral=True)
            return
        entries.sort(
            key=lambda x: (x[1].get('wins', 0), x[1].get('current_streak', 0), -x[1].get('games_played', 1)),
            reverse=True,
        )
        embed = discord.Embed(title="🏆 ROF Wordle Leaderboard", color=ROFColors.GOLD)
        lines = []
        for i, (uid, s) in enumerate(entries[:10], 1):
            name = None
            if interaction.guild:
                m = interaction.guild.get_member(int(uid))
                if m:
                    name = m.display_name
            if not name:
                u = self.bot.get_user(int(uid))
                if u:
                    name = u.display_name
            if not name:
                p_prof = db.get_player_profile(int(uid))
                name = p_prof.get("username") or f"User {uid}"

            medal = {1: '🥇', 2: '🥈', 3: '🥉'}.get(i, f"`#{i}`")
            played, wins = s.get('games_played', 0), s.get('wins', 0)
            wr = round(wins / played * 100) if played else 0
            lines.append(
                f"{medal} **{name}** — {wins}W/{played}G ({wr}%) · 🔥{s.get('current_streak', 0)} · 🏆{s.get('max_streak', 0)}"
            )
        embed.description = '\n'.join(lines)
        embed.set_footer(text="Ranked by wins → current streak • ROF Gaming Arena")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="wordle_help", description="Learn how to play ROF Wordle")
    async def wordle_help_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🔤 ROF Wordle — Rules",
            description=(
                "Guess the hidden **5-letter word** in **6 attempts**.\n\n"
                f"{GREEN} — Correct letter, correct position\n"
                f"{YELLOW} — Correct letter, wrong position\n"
                f"{GREY} — Letter not in the word\n\n"
                "**Commands**\n"
                "`/wordle` — Today's daily puzzle\n"
                "`/wordle_practice` — Unlimited practice\n"
                "`/wordle_stats` — Your personal stats\n"
                "`/wordle_leaderboard` — Alliance rankings\n"
                "`/wordle_help` — This message\n\n"
                "**Tips**\n"
                "• Any 5-letter A–Z word is accepted as a guess — even non-dictionary "
                "probe words like `XYLYL`, `FJORD`, `CRWTH`.\n"
                "• Use probe words to test high-value letters early.\n"
                "• Use the **📋 Share Result** button to copy a spoiler-free result.\n"
                "• Only **daily** games count for daily streaks.\n"
                "• New word every day at **00:00 UTC**."
            ),
            color=ROFColors.ARENA,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Wordle(bot))