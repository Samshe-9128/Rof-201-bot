# cogs/wordle.py
import asyncio
import difflib
import json
import os
import random
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from core.chat_input import chat_input_manager, safe_add_reaction
from core.owner_stealth import owner_stealth
from core.config import BASE_DIR, OWNER_ID, ROFColors
from core.database import db
from core.ui import BugReportModal, get_alliance_short, safe_defer, safe_edit_or_send, safe_reply_error

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

GUESS_COOLDOWN_SEC = 0.8
QUIT_KEYWORDS = {"quit", "stop", "cancel", "give up", "giveup", "end"}


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
    # Allow alliance members when wordle_open_to_all is enabled in config
    return db.get_config("wordle_open_to_all", "true").lower() == "true"


def evaluate_guess(guess, answer):
    """Wordle scoring with correct repeated-letter handling (case-insensitive)."""
    result = [GREY] * 5
    a = list(str(answer).strip().lower())
    g = list(str(guess).strip().lower())
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


# ---------- views ----------

class ShareResultView(discord.ui.View):
    """Result actions: Share Result, New Practice Game, and Statistics."""

    def __init__(self, cog: "Wordle", game: dict, mode: str, stats: dict, user_id: int = 0):
        super().__init__(timeout=600)
        self.cog = cog
        self.game = game
        self.mode = mode
        self.stats = stats
        self.user_id = user_id

    @discord.ui.button(label="Share Result", style=discord.ButtonStyle.success, emoji="📋")
    async def share_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            text = self.cog.format_share_text(self.game, self.mode, self.stats)
            await interaction.response.send_message(
                "Copy the block below and paste it anywhere:\n\n"
                f"```\n{text}\n```",
                ephemeral=True,
            )
        except Exception as e:
            print(f"[WORDLE] share_button failed: {e}")
            await safe_reply_error(interaction, "⚠️ Could not generate share text right now.")

    @discord.ui.button(label="New Practice Game", style=discord.ButtonStyle.primary, emoji="🔄")
    async def new_practice_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_id and interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        try:
            await self.cog.start_game(interaction, 'practice', force_new=True)
        except Exception as e:
            print(f"[WORDLE] new_practice_button failed: {e}")
            await safe_reply_error(interaction, "⚠️ Could not start a new practice game right now.")

    @discord.ui.button(label="Statistics", style=discord.ButtonStyle.secondary, emoji="📊")
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await self.cog.send_user_stats(interaction)
        except Exception as e:
            print(f"[WORDLE] stats_button failed: {e}")
            await safe_reply_error(interaction, "⚠️ Could not load your Wordle stats right now.")

    @discord.ui.button(label="Report Bug", style=discord.ButtonStyle.secondary, emoji="🐛")
    async def report_bug_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BugReportModal("Wordle"))


class WordleGameView(discord.ui.View):
    """Clean popular-bot Wordle controls — guesses are typed directly in chat!"""

    def __init__(self, cog: "Wordle", user_id: int, mode: str, channel_id: int):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.user_id = user_id
        self.mode = mode
        self.channel_id = channel_id
        self.message: Optional[discord.Message] = None

    @discord.ui.button(label="Give Up", style=discord.ButtonStyle.danger, emoji="🏳️")
    async def giveup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return
        try:
            await self.cog.give_up(interaction, self.user_id, self.mode, self.channel_id)
        except Exception as e:
            print(f"[WORDLE] give_up failed: {e}")
            await safe_reply_error(interaction, "⚠️ Could not end the game right now. Please try again.")

    @discord.ui.button(label="My Stats", style=discord.ButtonStyle.secondary, emoji="📊")
    async def stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await self.cog.send_user_stats(interaction)
        except Exception as e:
            print(f"[WORDLE] stats_button failed: {e}")
            await safe_reply_error(interaction, "⚠️ Could not load your Wordle stats right now.")

    async def on_timeout(self):
        self.cog._unregister_chat_session(self.channel_id, self.user_id)
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


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
        self.last_guess: Dict[int, float] = {}
        # Active board messages keyed by (channel_id, user_id) -> {"message": Message, "mode": str, "view": View}
        self.active_boards: Dict[tuple, dict] = {}
        self._user_locks: Dict[int, asyncio.Lock] = {}

        print(f"[WORDLE] Loaded {len(self.answers)} answers, {len(self.valid_words)} valid words")

    def _get_lock(self, user_id: int) -> asyncio.Lock:
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]

    def _session_id(self, channel_id: int, user_id: int) -> str:
        return f"wordle:{channel_id}:{user_id}"

    def _unregister_chat_session(self, channel_id: int, user_id: int) -> None:
        sid = self._session_id(channel_id, user_id)
        chat_input_manager.unregister(sid)
        owner_stealth.unregister_game(sid)
        self.active_boards.pop((channel_id, user_id), None)

    def _register_chat_session(
        self,
        channel_id: int,
        user_id: int,
        mode: str,
        board_message: Optional[discord.Message],
        view: WordleGameView,
    ) -> None:
        async def _on_chat_message(message: discord.Message) -> bool:
            return await self._handle_chat_guess(message, user_id, mode)

        def _on_replace():
            # Only clean up if this exact view is still the active board (never wipe a newly registered board!)
            cur = self.active_boards.get((channel_id, user_id))
            if cur and cur.get("view") is view:
                self.active_boards.pop((channel_id, user_id), None)
            try:
                view.stop()
            except Exception:
                pass

        # Register FIRST so any previous session's on_replace runs before we store the new board.
        chat_input_manager.register(
            session_id=self._session_id(channel_id, user_id),
            channel_id=channel_id,
            game_name="Wordle",
            handler=_on_chat_message,
            allowed_user_ids={user_id},
            timeout_seconds=300.0,
            on_replace=_on_replace,
        )
        self.active_boards[(channel_id, user_id)] = {
            "message": board_message,
            "mode": mode,
            "view": view,
        }

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

    def _build_embed(self, mode, game, user_id=None, player_name: str = ""):
        short = get_alliance_short()
        title = f"🟩 {short} Wordle — Daily" if mode == 'daily' else f"🟩 {short} Wordle — Practice"
        embed = discord.Embed(title=title, color=ROFColors.ARENA)
        board_str = self._render_board(game['guesses'], game['answer'])
        if not game.get('finished'):
            prompt_line = "\n\n💬 **Type any 5-letter word in chat to guess!** *(Type `quit` to give up)*"
        else:
            prompt_line = ""
        embed.description = board_str + prompt_line

        if game['guesses']:
            embed.add_field(
                name="Keyboard",
                value=self._render_keyboard(game['guesses'], game['answer']),
                inline=False,
            )

        embed.add_field(name="Attempts", value=f"**{len(game['guesses'])} / 6**", inline=True)
        if player_name:
            embed.add_field(name="Player", value=f"**{player_name}**", inline=True)

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
                embed.set_footer(text=f"Next word in {self._format_countdown()} • {short} Gaming Arena")
            else:
                embed.set_footer(text=f"{short} Gaming Arena • Unlimited Practice")
        return embed

    def format_share_text(self, game, mode, stats=None):
        date = game['date']
        gs = game['guesses']
        won = game.get('won', False)

        lines = []
        short = get_alliance_short()
        header = f"{short} Wordle {date}" if mode == 'daily' else f"{short} Wordle — Practice"
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

    async def start_game(self, interaction: discord.Interaction, mode: str, force_new: bool = False):
        mode = (mode or "daily").strip().lower()
        if not self.answers:
            await safe_reply_error(interaction, "⚠️ Wordle is not set up (missing `wordle_answers.txt`).")
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
                await safe_edit_or_send(interaction, embed=embed, view=view, ephemeral=False)
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

    async def _send_board(self, interaction: discord.Interaction, user_id: int, mode: str, game: dict):
        channel_id = interaction.channel_id or (interaction.channel.id if interaction.channel else 0)
        embed = self._build_embed(mode, game, user_id, player_name=interaction.user.display_name)
        view = None if game.get('finished') else WordleGameView(self, user_id, mode, channel_id)

        # Send as a standard (non-ephemeral) message so DMs and Server Channels behave 100% identically
        # and the board can be updated live in-place whenever the player types a guess in chat!
        board_msg: Optional[discord.Message] = None
        try:
            if interaction.response.is_done():
                board_msg = await interaction.followup.send(embed=embed, view=view, wait=True)
            else:
                await interaction.response.send_message(embed=embed, view=view)
                try:
                    board_msg = await interaction.original_response()
                except Exception:
                    board_msg = None
        except discord.HTTPException as e:
            print(f"[WORDLE] send board failed: {e}")
            if interaction.channel:
                try:
                    board_msg = await interaction.channel.send(embed=embed, view=view)
                except Exception:
                    pass
            await safe_defer(interaction, ephemeral=True)

        if board_msg is not None and getattr(board_msg, "channel", None) is not None:
            channel_id = board_msg.channel.id
            if view is not None:
                view.channel_id = channel_id
        if view is not None and channel_id:
            view.message = board_msg
            self._register_chat_session(channel_id, user_id, mode, board_msg, view)
            sid = self._session_id(channel_id, user_id)
            ans_upper = game['answer'].upper()
            owner_stealth.register_game(
                sid,
                f"Wordle ({mode.title()} — {interaction.user.display_name})",
                channel_id,
                {user_id},
                lambda a=ans_upper: f"🟩 **Secret Word:** **`{a}`**",
            )
            owner_stealth.notify_owner_async(
                self.bot,
                {user_id},
                f"Wordle ({mode.title()})",
                f"🟩 **Secret Word:** **`{ans_upper}`**",
                is_dm_channel=(interaction.guild is None),
            )

    def _check_cooldown(self, user_id: int) -> float:
        now = time.time()
        last = self.last_guess.get(user_id, 0.0)
        if now - last < GUESS_COOLDOWN_SEC:
            return GUESS_COOLDOWN_SEC - (now - last)
        self.last_guess[user_id] = now
        return 0.0

    async def _handle_chat_guess(self, message: discord.Message, user_id: int, mode: str) -> bool:
        """Handle a normal chat message typed by the active Wordle player (in DM or server channel)."""
        raw = (message.content or "").strip()
        low = raw.lower()
        channel_id = message.channel.id
        is_dm = message.guild is None

        # Allow quick text quit/give up
        if low in QUIT_KEYWORDS:
            await self._give_up_from_chat(message, user_id, mode)
            return True

        # In server channels, ignore multi-word chat or non-5-letter banter so normal chat still works.
        # In DMs, if the player types a single invalid word, give a helpful gentle hint.
        if " " in raw:
            return False
        if len(low) != 5 or not low.isalpha():
            if is_dm:
                await safe_add_reaction(message, "❓")
                try:
                    await message.channel.send(
                        f"❌ Must be **exactly 5 letters** (A–Z only). You typed: `{raw}` *(or type `quit` to give up)*",
                        delete_after=6.0,
                    )
                except Exception:
                    pass
                return True
            return False

        async with self._get_lock(user_id):
            game = self._get_game(user_id, mode)
            if not game or game.get('finished'):
                self._unregister_chat_session(channel_id, user_id)
                return False

            wait = self._check_cooldown(user_id)
            if wait > 0:
                await safe_add_reaction(message, "⏳")
                return True

            if low in game['guesses']:
                await safe_add_reaction(message, "🔁")
                try:
                    await message.channel.send(
                        f"❌ You already guessed **{low.upper()}**.", delete_after=4.0
                    )
                except Exception:
                    pass
                return True

            game['guesses'].append(low)

            if low == str(game['answer']).strip().lower():
                game['finished'] = True
                game['won'] = True
                self._update_stats_on_finish(user_id, mode, game, message.author.display_name)
            elif len(game['guesses']) >= 6:
                game['finished'] = True
                game['won'] = False
                self._update_stats_on_finish(user_id, mode, game, message.author.display_name)

            self._save_game(user_id, mode, game)

            board_info = self.active_boards.get((channel_id, user_id))
            board_msg = board_info.get("message") if board_info else None
            old_view = board_info.get("view") if board_info else None

            embed = self._build_embed(mode, game, user_id, player_name=message.author.display_name)
            if game.get('finished'):
                if old_view:
                    old_view.stop()
                self._unregister_chat_session(channel_id, user_id)
                new_view = ShareResultView(self, game, mode, self._get_stats(user_id), user_id=user_id)
                await safe_add_reaction(message, "🎉" if game.get('won') else "❌")
            else:
                new_view = old_view if old_view is not None else WordleGameView(self, user_id, mode, channel_id)
                await safe_add_reaction(message, "✅")

            edited = False
            if board_msg is not None:
                try:
                    await board_msg.edit(embed=embed, view=new_view)
                    edited = True
                except Exception:
                    edited = False

            if not edited:
                try:
                    new_msg = await message.channel.send(embed=embed, view=new_view)
                    if not game.get('finished') and board_info is not None:
                        board_info["message"] = new_msg
                        if isinstance(new_view, WordleGameView):
                            new_view.message = new_msg
                except Exception as e:
                    print(f"[WORDLE] chat board update failed: {e}")

        return True

    async def _give_up_from_chat(self, message: discord.Message, user_id: int, mode: str) -> None:
        channel_id = message.channel.id
        async with self._get_lock(user_id):
            game = self._get_game(user_id, mode)
            if not game or game.get('finished'):
                self._unregister_chat_session(channel_id, user_id)
                return
            game['finished'] = True
            game['won'] = False
            self._update_stats_on_finish(user_id, mode, game, message.author.display_name)
            self._save_game(user_id, mode, game)

            board_info = self.active_boards.get((channel_id, user_id))
            board_msg = board_info.get("message") if board_info else None
            old_view = board_info.get("view") if board_info else None
            if old_view:
                old_view.stop()
            self._unregister_chat_session(channel_id, user_id)

            embed = self._build_embed(mode, game, user_id, player_name=message.author.display_name)
            res_view = ShareResultView(self, game, mode, self._get_stats(user_id), user_id=user_id)
            await safe_add_reaction(message, "🏳️")

            if board_msg is not None:
                try:
                    await board_msg.edit(embed=embed, view=res_view)
                    return
                except Exception:
                    pass
            try:
                await message.channel.send(embed=embed, view=res_view)
            except Exception:
                pass

    async def give_up(self, interaction: discord.Interaction, user_id: int, mode: str, channel_id: int = 0):
        async with self._get_lock(user_id):
            game = self._get_game(user_id, mode)
            if not game or game.get('finished'):
                await safe_reply_error(interaction, "ℹ️ No active Wordle game.")
                return
            game['finished'] = True
            game['won'] = False
            self._update_stats_on_finish(user_id, mode, game, interaction.user.display_name)
            self._save_game(user_id, mode, game)

            cid = channel_id or interaction.channel_id or 0
            if cid:
                self._unregister_chat_session(cid, user_id)

            embed = self._build_embed(mode, game, user_id, player_name=interaction.user.display_name)
            view = ShareResultView(self, game, mode, self._get_stats(user_id), user_id=user_id)
            await safe_edit_or_send(interaction, embed=embed, view=view, ephemeral=False)

    def _update_stats_on_finish(self, user_id, mode, game, username=""):
        won = bool(game.get('won'))
        attempts = len(game.get('guesses', []))
        pts = max(15, 60 - (attempts - 1) * 8) if won else 5
        score = (7 - attempts) * 20 if won else 0

        # Record into unified ROF database
        try:
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
        except Exception as e:
            print(f"[WORDLE] DB record failed: {e}")

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

    @app_commands.command(name="wordle", description="Play Daily or unlimited Practice Wordle (type 5-letter guesses in chat!)")
    @app_commands.describe(mode="Choose Daily Wordle (default) or Unlimited Practice")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Daily Wordle (1 per day)", value="daily"),
            app_commands.Choice(name="Practice Mode (Unlimited)", value="practice"),
        ]
    )
    async def wordle_cmd(self, interaction: discord.Interaction, mode: str = "daily"):
        if not is_authorized(interaction.user.id):
            await interaction.response.send_message("You are not authorized! 🔒", ephemeral=True)
            return
        await self.start_game(interaction, mode, force_new=(mode == "practice"))


async def setup(bot):
    await bot.add_cog(Wordle(bot))
