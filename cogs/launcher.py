from datetime import datetime, timezone
# cogs/launcher.py
import traceback

import discord
from discord import app_commands
from discord.ext import commands

from core.config import DEFAULT_TZ_OFFSET, HAVColors, format_tz_label
from core.database import db
from core.rooms import room_manager
from core.ui import get_alliance_name, get_alliance_short, hav_embed

SINGLE_PLAYER_CATALOG = [
    ("higher_lower", "⬆️⬇️ Higher or Lower", "Instant 1-click number streak — push your luck or Cash Out!"),
    ("treasure_hunt", "💎 Treasure Hunt (3x3)", "Find 7 safe gems and avoid 2 hidden bombs — instant clicks!"),
    ("wordle_daily", "🔤 Wordle (Daily)", "Guess today's hidden 5-letter word in 6 attempts"),
    ("wordle_practice", "🔤 Wordle (Practice)", "Unlimited 5-letter Wordle practice"),
    ("word_scramble", "🔀 Word Scramble", "Unscramble mixed-up letters before the timer expires"),
    ("memory_sequence", "🔴 Memory Challenge", "Memorize and reproduce a growing colour sequence"),
    ("quick_math", "🧮 Quick Math", "Solve rapid calculations in a 60-second sprint"),
    ("reaction_solo", "⚡ Reaction Speed Test", "Measure your reaction speed in milliseconds"),
    ("trivia_solo", "❓ Trivia Challenge", "Answer general knowledge questions across 8 categories"),
    ("rps_solo", "✂️ Rock Paper Scissors", "Play Single, Best of 3, or Best of 5 against the Bot"),
    ("number_guess", "🔢 Number Guessing", "Find the secret number using Higher/Lower hints"),
    ("emoji_solo", "🎭 Emoji Guessing", "Identify movies, games, phrases, and objects from emojis"),
]

MULTIPLAYER_CATALOG = [
    ("tictactoe", "❌⭕ Tic-Tac-Toe (2p)", "Fast 3x3 grid duel — max 9 moves!"),
    ("closest_wins", "🎯 Closest Wins (2–10p)", "20s simultaneous number guess — closest to target wins!"),
    ("codebreaker", "🔐 Four-Digit Codebreaker", "Priority Race: Crack the 4-digit secret code first!"),
    ("reaction_race", "⚡ Reaction Race (2–10p)", "Compete to click fastest when the green signal appears"),
    ("word_race", "🔤 Word Guessing Race (2–10p)", "Race to unscramble the same word across 3 rounds"),
    ("math_battle", "🧮 Quick Math Battle (2–10p)", "Solve calculations simultaneously with speed bonuses"),
    ("trivia_battle", "❓ Trivia Battle (2–10p)", "Lock in private trivia answers and climb the live scoreboard"),
    ("rps_multi", "✂️ Multiplayer RPS (2p)", "1v1 Best of 3 duel with hidden move selection"),
    ("emoji_race", "🎭 Multiplayer Emoji Guessing (2–10p)", "First player to solve each emoji puzzle wins the round"),
    ("connect4", "🔴 Connect 4 (2p)", "Classic 7x6 grid strategy duel"),
]

# ==============================================================================
# HELPERS
# ==============================================================================

def _disable_all(view: discord.ui.View) -> None:
    for child in view.children:
        try:
            child.disabled = True
        except Exception:
            pass

async def _safe_edit(interaction: discord.Interaction, embed: discord.Embed, view: discord.ui.View) -> None:
    try:
        await interaction.response.edit_message(embed=embed, view=view)
    except (discord.NotFound, discord.InteractionResponded):
        try:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            print(f"[LAUNCHER] safe_edit followup failed: {e}")
    except Exception as e:
        print(f"[LAUNCHER] safe_edit failed: {type(e).__name__}: {e}")

async def _notify_error(interaction: discord.Interaction, message: str = "⚠️ Could not launch that game. Please try again.") -> None:
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)
    except Exception:
        pass

# ==============================================================================
# SINGLE-PLAYER MENU
# ==============================================================================

class SinglePlayerMenuView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user: discord.abc.User):
        super().__init__(timeout=300.0)
        self.bot = bot
        self.user = user

        options = [
            discord.SelectOption(label=title, value=key, description=desc[:100])
            for key, title, desc in SINGLE_PLAYER_CATALOG
        ]
        self.select = discord.ui.Select(
            placeholder="Select a Single-Player Game to launch...",
            options=options,
            row=0,
        )
        self.select.callback = self._on_select
        self.add_item(self.select)

    def build_embed(self) -> discord.Embed:
        lines = [f"• **{title}** — {desc}" for _, title, desc in SINGLE_PLAYER_CATALOG]
        return hav_embed(
            title=f"🎯 {get_alliance_short()} GAMING ARENA — SINGLE PLAYER",
            description="Select any game from the menu below to start playing immediately:\n\n" + "\n".join(lines),
            color=HAVColors.ARENA,
            footer_extra=f"Player: {self.user.display_name}",
        )

    async def _on_select(self, interaction: discord.Interaction):
        # fix F: user-match guard (defense in depth).
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "This isn't your menu!", ephemeral=True
            )
        if not self.select.values:
            return
        choice = self.select.values[0]

        # fix B: guard the whole dispatch — a failed launch must not hang the interaction.
        try:
            await self._dispatch(interaction, choice)
        except Exception as e:
            print(f"[LAUNCHER] single dispatch error ({choice}): {type(e).__name__}: {e}")
            traceback.print_exc()
            await _notify_error(interaction)
            return

        # Reset dropdown selection so the user can launch the same game again from /games.
        if interaction.response.is_done() and interaction.message:
            try:
                for opt in self.select.options:
                    opt.default = False
                await interaction.followup.edit_message(interaction.message.id, view=self)
            except Exception:
                pass

    async def _dispatch(self, interaction: discord.Interaction, choice: str) -> None:
        sp_cog = self.bot.get_cog("SinglePlayerGames")
        wordle_cog = self.bot.get_cog("Wordle")
        mem_cog = self.bot.get_cog("Memory")
        qd_cog = self.bot.get_cog("QuickDraw")

        # fix A: explicit per-choice routing with clear "cog unavailable" feedback.
        if choice == "wordle_daily":
            if not wordle_cog:
                return await _notify_error(interaction, "⚠️ Wordle is currently unavailable.")
            await wordle_cog.start_game(interaction, "daily")

        elif choice == "wordle_practice":
            if not wordle_cog:
                return await _notify_error(interaction, "⚠️ Wordle is currently unavailable.")
            await wordle_cog.start_game(interaction, "practice", force_new=True)

        elif choice == "word_scramble":
            if not sp_cog:
                return await _notify_error(interaction, "⚠️ Word Scramble is currently unavailable.")
            await sp_cog.launch_word_scramble(interaction)

        elif choice == "higher_lower":
            fast_cog = self.bot.get_cog("FastGames")
            if not fast_cog:
                return await _notify_error(interaction, "⚠️ Higher or Lower is currently unavailable.")
            await fast_cog.start_higher_lower(interaction)

        elif choice == "treasure_hunt":
            fast_cog = self.bot.get_cog("FastGames")
            if not fast_cog:
                return await _notify_error(interaction, "⚠️ Treasure Hunt is currently unavailable.")
            await fast_cog.start_treasure_hunt(interaction)

        elif choice == "memory_sequence":
            if not mem_cog:
                return await _notify_error(interaction, "⚠️ Memory is currently unavailable.")
            await mem_cog.start_sequence_memory(interaction)

        elif choice == "quick_math":
            if not sp_cog:
                return await _notify_error(interaction, "⚠️ Quick Math is currently unavailable.")
            await sp_cog.launch_quick_math(interaction)

        elif choice == "reaction_solo":
            if not qd_cog:
                return await _notify_error(interaction, "⚠️ Reaction Speed Test is currently unavailable.")
            await qd_cog.launch_single_reaction_menu(interaction)

        elif choice == "trivia_solo":
            if not sp_cog:
                return await _notify_error(interaction, "⚠️ Trivia is currently unavailable.")
            await sp_cog.launch_trivia(interaction)

        elif choice == "rps_solo":
            if not sp_cog:
                return await _notify_error(interaction, "⚠️ Rock Paper Scissors is currently unavailable.")
            await sp_cog.launch_rps(interaction)

        elif choice == "number_guess":
            if not sp_cog:
                return await _notify_error(interaction, "⚠️ Number Guessing is currently unavailable.")
            await sp_cog.launch_number_guessing(interaction)

        elif choice == "emoji_solo":
            if not sp_cog:
                return await _notify_error(interaction, "⚠️ Emoji Guessing is currently unavailable.")
            await sp_cog.launch_emoji_guessing(interaction)

        else:
            await _notify_error(interaction, "⚠️ Unknown game selection.")

    @discord.ui.button(label="Back to Arena", style=discord.ButtonStyle.secondary, emoji="⬅️", row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "This isn't your menu!", ephemeral=True
            )
        main_view = GamingArenaMainView(self.bot, interaction.user)
        await _safe_edit(interaction, main_view.build_embed(), main_view)

    async def on_timeout(self):
        # fix G: disable stale buttons on timeout.
        _disable_all(self)

# ==============================================================================
# MULTIPLAYER MENU
# ==============================================================================

class MultiplayerMenuView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user: discord.abc.User):
        super().__init__(timeout=300.0)
        self.bot = bot
        self.user = user

        options = [
            discord.SelectOption(label=title, value=key, description=desc[:100])
            for key, title, desc in MULTIPLAYER_CATALOG
        ]
        self.select = discord.ui.Select(
            placeholder="Select a Multiplayer Game to create a room...",
            options=options,
            row=0,
        )
        self.select.callback = self._on_select
        self.add_item(self.select)

    def build_embed(self) -> discord.Embed:
        lines = [f"• **{title}** — {desc}" for _, title, desc in MULTIPLAYER_CATALOG]
        return hav_embed(
            title=f"🏟️ {get_alliance_short()} GAMING ARENA — MULTIPLAYER",
            description=(
                "Choose a multiplayer game below to create a **Public Game Room** "
                "in this channel so alliance members can join:\n\n" + "\n".join(lines)
            ),
            color=HAVColors.ARENA,
            footer_extra=f"Host: {self.user.display_name}",
        )

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "This isn't your menu!", ephemeral=True
            )
        if not self.select.values:
            return
        choice = self.select.values[0]

        try:
            await self._dispatch(interaction, choice)
        except Exception as e:
            print(f"[LAUNCHER] multi dispatch error ({choice}): {type(e).__name__}: {e}")
            traceback.print_exc()
            await _notify_error(interaction)
            return

        # Reset dropdown selection so the user can launch the same game again from /games.
        if interaction.response.is_done() and interaction.message:
            try:
                for opt in self.select.options:
                    opt.default = False
                await interaction.followup.edit_message(interaction.message.id, view=self)
            except Exception:
                pass

    async def _dispatch(self, interaction: discord.Interaction, choice: str) -> None:
        cb_cog = self.bot.get_cog("Codebreaker")
        qd_cog = self.bot.get_cog("QuickDraw")
        mp_cog = self.bot.get_cog("MultiplayerGames")
        fast_cog = self.bot.get_cog("FastGames")
        c4_cog = self.bot.get_cog("Connect4")

        if choice == "codebreaker":
            if not cb_cog:
                return await _notify_error(interaction, "⚠️ Codebreaker is currently unavailable.")
            await cb_cog.open_room(interaction, min_players=1)

        elif choice == "reaction_race":
            if not qd_cog:
                return await _notify_error(interaction, "⚠️ Reaction Race is currently unavailable.")
            await qd_cog.open_reaction_race_room(interaction)

        elif choice in ("word_race", "math_battle", "trivia_battle", "rps_multi", "emoji_race"):
            if not mp_cog:
                return await _notify_error(interaction, "⚠️ Multiplayer games are currently unavailable.")
            await mp_cog.open_multiplayer_room(interaction, choice)

        elif choice == "tictactoe":
            if not fast_cog:
                return await _notify_error(interaction, "⚠️ Tic-Tac-Toe is currently unavailable.")
            await fast_cog.open_tictactoe_room(interaction)

        elif choice == "closest_wins":
            if not fast_cog:
                return await _notify_error(interaction, "⚠️ Closest Wins is currently unavailable.")
            await fast_cog.open_closest_wins_room(interaction)

        elif choice == "connect4":
            if not c4_cog:
                return await _notify_error(interaction, "⚠️ Connect 4 is currently unavailable.")
            await c4_cog.open_connect4_room(interaction)

        else:
            await _notify_error(interaction, "⚠️ Unknown game selection.")

    @discord.ui.button(label="Back to Arena", style=discord.ButtonStyle.secondary, emoji="⬅️", row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "This isn't your menu!", ephemeral=True
            )
        main_view = GamingArenaMainView(self.bot, interaction.user)
        await _safe_edit(interaction, main_view.build_embed(), main_view)

    async def on_timeout(self):
        _disable_all(self)

# ==============================================================================
# MAIN ARENA MENU
# ==============================================================================

class GamingArenaMainView(discord.ui.View):
    """Part 2.1 Central Gaming Main Menu (/games)."""

    def __init__(self, bot: commands.Bot, user: discord.abc.User):
        super().__init__(timeout=300.0)
        self.bot = bot
        self.user = user

    def build_embed(self) -> discord.Embed:
        # fix I: never let room_manager hiccup kill the whole menu.
        try:
            active_rooms = room_manager.list_active_rooms()
            room_count = len(active_rooms)
        except Exception as e:
            print(f"[LAUNCHER] list_active_rooms failed: {type(e).__name__}: {e}")
            room_count = 0

        short = get_alliance_short()
        return hav_embed(
            title=f"🎮 {short} GAMING ARENA",
            description=(
                f"Welcome to the **{short} Gaming Arena**!\n"
                "Choose how you want to play using the controls below.\n\n"
                "🎯 **Single Player** — 12 solo skill, puzzle, trivia, and reflex games\n"
                "🏟️ **Multiplayer** — Create or join live alliance game rooms\n"
                f"🔥 **Active Games** — `{room_count}` room(s) currently active\n"
                "🏆 **Leaderboard** — Overall, Weekly, and Per-Game rankings\n"
                "👤 **My Profile** — Personal win rate, best score, reaction stats & match history\n"
                f"📖 **Game Help** — Rules and tips for every {short} game"
            ),
            color=HAVColors.ARENA,
            footer_extra=f"Player: {self.user.display_name}",
        )

    def _is_owner(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id

    @discord.ui.button(label="Single Player", style=discord.ButtonStyle.primary, emoji="🎯", row=0)
    async def single_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._is_owner(interaction):
            return await interaction.response.send_message(
                "This isn't your menu!", ephemeral=True
            )
        view = SinglePlayerMenuView(self.bot, interaction.user)
        await _safe_edit(interaction, view.build_embed(), view)

    @discord.ui.button(label="Multiplayer", style=discord.ButtonStyle.success, emoji="🏟️", row=0)
    async def multi_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "🏟️ Multiplayer rooms need a server channel! Click **Single Player** to play solo games here in DMs.",
                ephemeral=True,
            )
        if not self._is_owner(interaction):
            return await interaction.response.send_message(
                "This isn't your menu!", ephemeral=True
            )
        view = MultiplayerMenuView(self.bot, interaction.user)
        await _safe_edit(interaction, view.build_embed(), view)

    @discord.ui.button(label="Active Games", style=discord.ButtonStyle.secondary, emoji="🔥", row=1)
    async def active_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._is_owner(interaction):
            return await interaction.response.send_message(
                "This isn't your menu!", ephemeral=True
            )
        # fix E: safe iteration over rooms.
        try:
            rooms = room_manager.list_active_rooms()
        except Exception as e:
            print(f"[LAUNCHER] list_active_rooms failed: {type(e).__name__}: {e}")
            rooms = []

        if not rooms:
            embed = hav_embed(
                title=f"🔥 {get_alliance_short()} ACTIVE GAMES",
                description=(
                    "There are no open multiplayer rooms right now.\n"
                    "Click **Multiplayer** to host a new room!"
                ),
                color=HAVColors.INFO,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        lines = []
        for r in rooms:
            try:
                host_mention = getattr(r.host, "mention", str(r.host))
                max_players = getattr(r, "max_players", "?")
                status = str(getattr(r, "status", "unknown")).upper()
                players_count = len(getattr(r, "players", []))
                lines.append(
                    f"• **`{r.room_id}`** — **{r.game_title}** | Host: {host_mention} | "
                    f"Players: `{players_count}/{max_players}` | Status: `{status}`"
                )
            except Exception as e:
                print(f"[LAUNCHER] room render failed: {e}")

        embed = hav_embed(
            title=f"🔥 {get_alliance_short()} ACTIVE MULTIPLAYER ROOMS",
            description="\n".join(lines) or "*No rooms to display.*",
            color=HAVColors.ARENA,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Leaderboard", style=discord.ButtonStyle.secondary, emoji="🏆", row=1)
    async def lb_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._is_owner(interaction):
            return await interaction.response.send_message(
                "This isn't your menu!", ephemeral=True
            )
        # fix H: don't silently no-op if ArcadeCore is missing.
        arcade = self.bot.get_cog("ArcadeCore")
        if not arcade:
            return await interaction.response.send_message(
                "⚠️ Leaderboard is currently unavailable.", ephemeral=True
            )
        try:
            await arcade.send_leaderboard_interactive(interaction, ephemeral=True)
        except Exception as e:
            print(f"[LAUNCHER] leaderboard failed: {type(e).__name__}: {e}")
            await _notify_error(interaction, "⚠️ Could not open the leaderboard right now.")

    @discord.ui.button(label="My Profile", style=discord.ButtonStyle.secondary, emoji="👤", row=2)
    async def profile_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._is_owner(interaction):
            return await interaction.response.send_message(
                "This isn't your menu!", ephemeral=True
            )
        arcade = self.bot.get_cog("ArcadeCore")
        if not arcade:
            return await interaction.response.send_message(
                "⚠️ Player profiles are currently unavailable.", ephemeral=True
            )
        try:
            await arcade.send_profile_embed(interaction, interaction.user, ephemeral=True)
        except Exception as e:
            print(f"[LAUNCHER] profile failed: {type(e).__name__}: {e}")
            await _notify_error(interaction, "⚠️ Could not open your profile right now.")

    @discord.ui.button(label="Game Help", style=discord.ButtonStyle.secondary, emoji="📖", row=2)
    async def help_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._is_owner(interaction):
            return await interaction.response.send_message(
                "This isn't your menu!", ephemeral=True
            )
        embed = build_game_help_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def on_timeout(self):
        _disable_all(self)

def build_game_help_embed() -> discord.Embed:
    short = get_alliance_short()
    embed = hav_embed(
        title=f"📖 {short} GAMING ARENA — COMPLETE GUIDE",
        description=f"Every {short} game is designed for fast, interactive play on both desktop and mobile Discord.",
        color=HAVColors.INFO,
    )
    embed.add_field(
        name="🎯 Single-Player Games",
        value=(
            "• **Higher or Lower (`/higherlower`):** 1-click streak risk/reward game (1–100).\n"
            "• **Treasure Hunt (`/treasure`):** 3x3 mining grid — find 7 gems and dodge 2 bombs!\n"
            "• **Wordle (`/wordle` Daily or Practice):** Just type 5-letter words directly in chat or DM (6 tries: `🟩` exact, `🟨` misplaced).\n"
            "• **Word Scramble:** Type unscrambled words directly in chat across 3 timed rounds.\n"
            "• **Memory Challenge (`/memory`):** Reproduce a growing colour sequence (`🔴 🔵 🟢 🟡 🟣 🟠`).\n"
            "• **Quick Math:** 60-second sprint — just type numbers directly in chat!\n"
            "• **Reaction Speed Test:** Wait for the green **READY** signal and click for millisecond reaction records.\n"
            "• **Trivia:** 8 categories with instant explanations after every question.\n"
            f"• **Rock Paper Scissors:** Single, Best of 3, or Best of 5 vs the {short} Bot.\n"
            "• **Number Guessing:** Type numbers directly in chat using Higher/Lower hints.\n"
            "• **Emoji Guessing:** Type your answer directly in chat to decode the emojis."
        ),
        inline=False,
    )
    embed.add_field(
        name="🏟️ Multiplayer Room Games",
        value=(
            "• **Four-Digit Codebreaker (`/codebreaker`):** Race 2–8 players to crack a 4-digit secret code (`🟢` right spot, `🟡` wrong spot).\n"
            "• **Reaction Race (`/quickdraw`):** 2–10 players compete for the fastest valid click without false-starting.\n"
            "• **Word Guessing Race:** First player to unscramble each round's secret word scores.\n"
            "• **Quick Math Battle:** Simultaneous math rounds with speed bonuses.\n"
            "• **Trivia Battle:** Private locked-in answers with live scoreboard & tie handling.\n"
            "• **Multiplayer RPS:** 1v1 Best of 3/5 with hidden move selection.\n"
            "• **Multiplayer Emoji Guessing:** Multi-round emoji puzzle race.\n"
            "• **Tic-Tac-Toe (`/tictactoe`) & Closest Wins:** Fast 3x3 duels & 20s party number guesses.\n"
            "• **Connect 4 (`/connect4`):** Classic 7x6 grid strategy duel."
        ),
        inline=False,
    )
    return embed

# ==============================================================================
# COG
# ==============================================================================

class Launcher(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="games", description="Open the central Gaming Arena menu")
    @app_commands.checks.cooldown(1, 3.0)
    async def games_cmd(self, interaction: discord.Interaction):
        try:
            view = GamingArenaMainView(self.bot, interaction.user)
            await interaction.response.send_message(
                embed=view.build_embed(), view=view, ephemeral=True
            )
        except Exception as e:
            print(f"[LAUNCHER] /games failed: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⚠️ Could not open the Gaming Arena right now. Please try again.",
                        ephemeral=True,
                    )
            except Exception:
                pass

    @app_commands.command(name="help", description="View the complete Alliance Bot command & feature guide")
    @app_commands.checks.cooldown(1, 3.0)
    async def help_cmd(self, interaction: discord.Interaction):
        short = get_alliance_short()
        full_name = get_alliance_name()
        try:
            tz_off = float(db.get_config("game_tz_offset", str(DEFAULT_TZ_OFFSET)))
        except Exception:
            tz_off = float(DEFAULT_TZ_OFFSET)
        tz_label = format_tz_label(tz_off)

        embed = hav_embed(
            title=f"🛡️ {short} ALLIANCE BOT — COMMAND CENTER",
            description=f"Welcome to the official **{full_name}** gaming and alliance assistant!",
            color=HAVColors.ARENA,
        )
        embed.add_field(
            name="🎮 Gaming Commands",
            value=(
                f"`/games` — Open the {short} Gaming Arena (12 Single-Player & 10 Multiplayer + Game Help)\n"
                "`/wordle [mode]` — Daily or unlimited Practice 5-letter Wordle\n"
                "`/codebreaker` — Four-Digit Codebreaker Room or 1v1 Duel\n"
                "`/quickdraw` — Reaction Race (2–10p) or Solo Reaction Test\n"
                "`/memory` — Sequence Memory Challenge\n"
                "`/tictactoe`, `/connect4`, `/higherlower`, `/treasure` — Fast strategy & streak games"
            ),
            inline=False,
        )
        embed.add_field(
            name="📊 Profiles & Leaderboards",
            value=(
                "`/profile [member]` — View player profile, stats, reaction record & 1-click Match History\n"
                "`/leaderboard` — View Overall, Weekly, and Per-Game rankings"
            ),
            inline=False,
        )
        embed.add_field(
            name="📅 Alliance Events & Rules",
            value=(
                f"`/events` — View upcoming alliance events in Game Time (`{tz_label}`) & India Time (`IST`)\n"
                "`/event add|edit|view|delete` — Create (with repeat & alert options), edit, mute, or delete events\n"
                f"`/rules view` — Read the official {short} Alliance rules"
            ),
            inline=False,
        )
        embed.add_field(
            name="💬 Haven Chat Assistant",
            value=(
                "DM me, `@mention` me, or ask in a configured alliance channel about "
                "upcoming event timings, alliance rules, or how to play any game!"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ping", description="Check bot latency, uptime, and database status")
    @app_commands.checks.cooldown(1, 3.0)
    async def ping_cmd(self, interaction: discord.Interaction):
        latency_ms = round(self.bot.latency * 1000)
        started = getattr(self.bot, "started_at", None)
        if started is not None:
            secs = max(0, int((datetime.now(timezone.utc) - started).total_seconds()))
            days, rem = divmod(secs, 86400)
            hrs, rem = divmod(rem, 3600)
            mins, s = divmod(rem, 60)
            uptime_str = f"{days}d {hrs}h {mins}m {s}s" if days else f"{hrs}h {mins}m {s}s"
        else:
            uptime_str = "Online"

        backend = getattr(db, "backend", "SQLite")
        short = get_alliance_short()
        embed = hav_embed(
            title=f"🏓 {short} BOT STATUS",
            description=(
                f"• **Latency:** `{latency_ms} ms`\n"
                f"• **Uptime:** `{uptime_str}`\n"
                f"• **Database:** `{backend}`\n"
                f"• **Active Rooms:** `{len(room_manager.get_all_rooms())}`"
            ),
            color=HAVColors.SUCCESS if latency_ms < 250 else HAVColors.WARNING,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Launcher(bot))
