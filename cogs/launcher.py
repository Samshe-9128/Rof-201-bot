# cogs/launcher.py
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from core.config import ROFColors, get_rank
from core.database import db
from core.rooms import room_manager
from core.ui import rof_embed


SINGLE_PLAYER_CATALOG = [
    ("wordle_daily", "🔤 Wordle (Daily)", "Guess today's hidden 5-letter word in 6 attempts"),
    ("wordle_practice", "🔤 Wordle (Practice)", "Unlimited 5-letter Wordle practice"),
    ("word_scramble", "🔀 Word Scramble", "Unscramble mixed-up letters before the timer expires"),
    ("memory_sequence", "🔴 Memory Challenge", "Memorize and reproduce a growing colour sequence"),
    ("memory_pairs", "🃏 Emoji Memory Match", "Memorize and match 8 animal emoji pairs"),
    ("quick_math", "🧮 Quick Math", "Solve rapid calculations in a 60-second sprint"),
    ("reaction_solo", "⚡ Reaction Speed Test", "Measure your reaction speed in milliseconds"),
    ("trivia_solo", "❓ Trivia Challenge", "Answer general knowledge questions across 8 categories"),
    ("rps_solo", "✂️ Rock Paper Scissors", "Play Single, Best of 3, or Best of 5 against ROF Bot"),
    ("number_guess", "🔢 Number Guessing", "Find the secret number using Higher/Lower hints"),
    ("emoji_solo", "🎭 Emoji Guessing", "Identify movies, games, phrases, and objects from emojis"),
]

MULTIPLAYER_CATALOG = [
    ("codebreaker", "🔐 Four-Digit Codebreaker", "Priority Race: Crack the 4-digit secret code first!"),
    ("reaction_race", "⚡ Reaction Race (2–10p)", "Compete to click fastest when the green signal appears"),
    ("word_race", "🔤 Word Guessing Race (2–10p)", "Race to unscramble the same word across 3 rounds"),
    ("math_battle", "🧮 Quick Math Battle (2–10p)", "Solve calculations simultaneously with speed bonuses"),
    ("trivia_battle", "❓ Trivia Battle (2–10p)", "Lock in private trivia answers and climb the live scoreboard"),
    ("rps_multi", "✂️ Multiplayer RPS (2p)", "1v1 Best of 3 duel with hidden move selection"),
    ("emoji_race", "🎭 Multiplayer Emoji Guessing (2–10p)", "First player to solve each emoji puzzle wins the round"),
    ("undercover", "🕵️ Undercover Spy (3–6p)", "Social deduction: discover who received the spy word"),
    ("connect4", "🔴 Connect 4 (2p)", "Classic 7x6 grid strategy duel"),
]


class SinglePlayerMenuView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user: discord.abc.User):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.user = user

        options = [
            discord.SelectOption(label=title, value=key, description=desc[:100])
            for key, title, desc in SINGLE_PLAYER_CATALOG
        ]
        self.select = discord.ui.Select(placeholder="Select a Single-Player Game to launch...", options=options, row=0)
        self.select.callback = self._on_select
        self.add_item(self.select)

    def build_embed(self) -> discord.Embed:
        lines = [f"• **{title}** — {desc}" for _, title, desc in SINGLE_PLAYER_CATALOG]
        return rof_embed(
            title="🎯 ROF GAMING ARENA — SINGLE PLAYER",
            description="Select any game from the menu below to start playing immediately:\n\n" + "\n".join(lines),
            color=ROFColors.ARENA,
            footer_extra=f"Player: {self.user.display_name}",
        )

    async def _on_select(self, interaction: discord.Interaction):
        choice = self.select.values[0]
        sp_cog = self.bot.get_cog("SinglePlayerGames")
        wordle_cog = self.bot.get_cog("Wordle")
        mem_cog = self.bot.get_cog("Memory")
        qd_cog = self.bot.get_cog("QuickDraw")

        if choice == "wordle_daily" and wordle_cog:
            await wordle_cog.start_game(interaction, "daily")
        elif choice == "wordle_practice" and wordle_cog:
            await wordle_cog.start_game(interaction, "practice", force_new=True)
        elif choice == "word_scramble" and sp_cog:
            await sp_cog.launch_word_scramble(interaction)
        elif choice == "memory_sequence" and mem_cog:
            await mem_cog.memory(interaction)
        elif choice == "memory_pairs" and mem_cog:
            await mem_cog.memory(interaction)
        elif choice == "quick_math" and sp_cog:
            await sp_cog.launch_quick_math(interaction)
        elif choice == "reaction_solo" and qd_cog:
            await qd_cog.launch_single_reaction_menu(interaction)
        elif choice == "trivia_solo" and sp_cog:
            await sp_cog.launch_trivia(interaction)
        elif choice == "rps_solo" and sp_cog:
            await sp_cog.launch_rps(interaction)
        elif choice == "number_guess" and sp_cog:
            await sp_cog.launch_number_guessing(interaction)
        elif choice == "emoji_solo" and sp_cog:
            await sp_cog.launch_emoji_guessing(interaction)

    @discord.ui.button(label="Back to Arena", style=discord.ButtonStyle.secondary, emoji="⬅️", row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        main_view = GamingArenaMainView(self.bot, interaction.user)
        await interaction.response.edit_message(embed=main_view.build_embed(), view=main_view)


class MultiplayerMenuView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user: discord.abc.User):
        super().__init__(timeout=180.0)
        self.bot = bot
        self.user = user

        options = [
            discord.SelectOption(label=title, value=key, description=desc[:100])
            for key, title, desc in MULTIPLAYER_CATALOG
        ]
        self.select = discord.ui.Select(placeholder="Select a Multiplayer Game to create a room...", options=options, row=0)
        self.select.callback = self._on_select
        self.add_item(self.select)

    def build_embed(self) -> discord.Embed:
        lines = [f"• **{title}** — {desc}" for _, title, desc in MULTIPLAYER_CATALOG]
        return rof_embed(
            title="🏟️ ROF GAMING ARENA — MULTIPLAYER",
            description=(
                "Choose a multiplayer game below to create a **Public Game Room** in this channel so alliance members can join:\n\n"
                + "\n".join(lines)
            ),
            color=ROFColors.ARENA,
            footer_extra=f"Host: {self.user.display_name}",
        )

    async def _on_select(self, interaction: discord.Interaction):
        choice = self.select.values[0]
        cb_cog = self.bot.get_cog("Codebreaker")
        qd_cog = self.bot.get_cog("QuickDraw")
        mp_cog = self.bot.get_cog("MultiplayerGames")
        uc_cog = self.bot.get_cog("Undercover")
        c4_cog = self.bot.get_cog("Connect4")

        if choice == "codebreaker" and cb_cog:
            await cb_cog.open_room(interaction, min_players=1)
        elif choice == "reaction_race" and qd_cog:
            await qd_cog.open_reaction_race_room(interaction)
        elif choice in ("word_race", "math_battle", "trivia_battle", "rps_multi", "emoji_race") and mp_cog:
            await mp_cog.open_multiplayer_room(interaction, choice)
        elif choice == "undercover" and uc_cog:
            await uc_cog.open_undercover_room(interaction)
        elif choice == "connect4" and c4_cog:
            await c4_cog.open_connect4_room(interaction)

    @discord.ui.button(label="Back to Arena", style=discord.ButtonStyle.secondary, emoji="⬅️", row=1)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        main_view = GamingArenaMainView(self.bot, interaction.user)
        await interaction.response.edit_message(embed=main_view.build_embed(), view=main_view)


class GamingArenaMainView(discord.ui.View):
    """Part 2.1 Central Gaming Main Menu (/games)."""

    def __init__(self, bot: commands.Bot, user: discord.abc.User):
        super().__init__(timeout=240.0)
        self.bot = bot
        self.user = user

    def build_embed(self) -> discord.Embed:
        active_rooms = room_manager.list_active_rooms()
        return rof_embed(
            title="🎮 ROF GAMING ARENA",
            description=(
                "Welcome to the **ROF Gaming Arena**!\n"
                "Choose how you want to play using the controls below.\n\n"
                "🎯 **Single Player** — 10 solo skill, puzzle, trivia, and reflex games\n"
                "🏟️ **Multiplayer** — Create or join live alliance game rooms\n"
                f"🔥 **Active Games** — `{len(active_rooms)}` room(s) currently active\n"
                "🏆 **Leaderboard** — Overall, Weekly, and Per-Game rankings\n"
                "👤 **My Profile** — Personal win rate, best score, and reaction stats\n"
                "📖 **Game Help** — Rules and tips for every ROF game"
            ),
            color=ROFColors.ARENA,
            footer_extra=f"Player: {self.user.display_name}",
        )

    @discord.ui.button(label="Single Player", style=discord.ButtonStyle.primary, emoji="🎯", row=0)
    async def single_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = SinglePlayerMenuView(self.bot, interaction.user)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    @discord.ui.button(label="Multiplayer", style=discord.ButtonStyle.success, emoji="🏟️", row=0)
    async def multi_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MultiplayerMenuView(self.bot, interaction.user)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    @discord.ui.button(label="Active Games", style=discord.ButtonStyle.secondary, emoji="🔥", row=1)
    async def active_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        rooms = room_manager.list_active_rooms()
        if not rooms:
            embed = rof_embed(
                title="🔥 ROF ACTIVE GAMES",
                description="There are no open multiplayer rooms right now.\nClick **Multiplayer** to host a new room!",
                color=ROFColors.INFO,
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        lines = []
        for r in rooms:
            lines.append(
                f"• **`{r.room_id}`** — **{r.game_title}** | Host: {r.host.mention} | "
                f"Players: `{len(r.players)}/{r.max_players}` | Status: `{r.status.upper()}`"
            )
        embed = rof_embed(
            title="🔥 ROF ACTIVE MULTIPLAYER ROOMS",
            description="\n".join(lines),
            color=ROFColors.ARENA,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Leaderboard", style=discord.ButtonStyle.secondary, emoji="🏆", row=1)
    async def lb_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        arcade = self.bot.get_cog("ArcadeCore")
        if arcade:
            await arcade.send_leaderboard_interactive(interaction, ephemeral=True)

    @discord.ui.button(label="My Profile", style=discord.ButtonStyle.secondary, emoji="👤", row=2)
    async def profile_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        arcade = self.bot.get_cog("ArcadeCore")
        if arcade:
            await arcade.send_profile_embed(interaction, interaction.user, ephemeral=True)

    @discord.ui.button(label="Game Help", style=discord.ButtonStyle.secondary, emoji="📖", row=2)
    async def help_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_game_help_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)


def build_game_help_embed() -> discord.Embed:
    embed = rof_embed(
        title="📖 ROF GAMING ARENA — COMPLETE GUIDE",
        description="Every ROF game is designed for fast, interactive play on both desktop and mobile Discord.",
        color=ROFColors.INFO,
    )
    embed.add_field(
        name="🎯 Single-Player Games",
        value=(
            "• **Wordle (`/wordle`, `/wordle_practice`):** Guess a 5-letter word in 6 tries (`🟩` exact, `🟨` misplaced).\n"
            "• **Word Scramble:** Unscramble shuffled letters across 3 timed rounds.\n"
            "• **Memory Challenge (`/memory`):** Reproduce a growing colour sequence (`🔴 🔵 🟢 🟡`) or match 4x4 emoji pairs.\n"
            "• **Quick Math:** 60-second calculation sprint across Easy, Medium, and Hard modes.\n"
            "• **Reaction Speed Test:** Wait for the green **READY** signal and click for millisecond reaction records.\n"
            "• **Trivia:** 8 categories with instant explanations after every question.\n"
            "• **Rock Paper Scissors:** Single, Best of 3, or Best of 5 vs the ROF Bot.\n"
            "• **Number Guessing:** Use Higher/Lower hints to pinpoint the secret number.\n"
            "• **Emoji Guessing:** Decode movies, games, animals, food, and phrases from emojis."
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
            "• **Undercover (`/undercover`) & Connect 4 (`/connect4`):** Classic party & board duels."
        ),
        inline=False,
    )
    return embed


class Launcher(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="games", description="Open the central ROF Gaming Arena menu")
    async def games_cmd(self, interaction: discord.Interaction):
        view = GamingArenaMainView(self.bot, interaction.user)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    @app_commands.command(name="help", description="View the complete ROF Bot command & feature guide")
    async def help_cmd(self, interaction: discord.Interaction):
        embed = rof_embed(
            title="🛡️ ROF ALLIANCE BOT — COMMAND CENTER",
            description="Welcome to the official **Rise of Farkers (ROF)** gaming and alliance assistant!",
            color=ROFColors.ARENA,
        )
        embed.add_field(
            name="🎮 Gaming Commands",
            value=(
                "`/games` — Open the ROF Gaming Arena (Single Player & Multiplayer)\n"
                "`/codebreaker` — Start a Four-Digit Codebreaker Room or 1v1 Duel\n"
                "`/quickdraw` — Start a Reaction Race (2–10p) or Solo Reaction Test\n"
                "`/wordle` & `/wordle_practice` — Daily & unlimited 5-letter Wordle\n"
                "`/memory` — Sequence Memory Challenge & Emoji Pair Match\n"
                "`/undercover` & `/connect4` — Multiplayer party & strategy games\n"
                "`/game stats`, `/game history`, `/game help` — Detailed gaming info"
            ),
            inline=False,
        )
        embed.add_field(
            name="📊 Profiles & Leaderboards",
            value=(
                "`/profile [member]` — View player profile, win rate, favourite game & reaction record\n"
                "`/leaderboard` — View Overall, Weekly, All-Time, and Per-Game rankings"
            ),
            inline=False,
        )
        embed.add_field(
            name="📅 Alliance Events & Rules",
            value=(
                "`/events` — View upcoming alliance events in Game Time (`UTC-2`) & India Time (`IST`)\n"
                "`/event view <id>` — View detailed countdown for a specific event\n"
                "`/rules` — Read the official ROF Alliance rules"
            ),
            inline=False,
        )
        embed.add_field(
            name="🤖 Alliance AI Assistant",
            value="Send me a Direct Message (or ask in the configured alliance channel) about upcoming events, rules, strategies, or how to play any game!",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /game command group (Part 11: /game stats, /game history, /game help)
    game_group = app_commands.Group(name="game", description="ROF Gaming statistics, match history, and help")

    @game_group.command(name="stats", description="View your gaming statistics")
    async def game_stats_cmd(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        arcade = self.bot.get_cog("ArcadeCore")
        if arcade:
            await arcade.send_profile_embed(interaction, target, ephemeral=True)

    @game_group.command(name="history", description="View your recent match history")
    async def game_history_cmd(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        rows = db.get_player_history(target.id, limit=10)
        if not rows:
            return await interaction.response.send_message(
                f"ℹ️ No recorded matches yet for **{target.display_name}**. Use `/games` to play!",
                ephemeral=True,
            )
        lines = []
        for r in rows:
            icon = {"win": "🟢 WIN", "loss": "🔴 LOSS", "draw": "🟡 DRAW"}.get(r["result"], r["result"])
            react_note = f" · ⚡ `{r['reaction_ms']} ms`" if r.get("reaction_ms") else ""
            lines.append(
                f"• <t:{r['played_at']}:R> — **{r['game_name']}** ({icon}) · Score: `{r['score']}` (`+{r['points_earned']} pts`){react_note}"
            )
        embed = rof_embed(
            title=f"📜 {target.display_name} — RECENT MATCH HISTORY",
            description="\n".join(lines),
            color=ROFColors.ARENA,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @game_group.command(name="help", description="View instructions for all ROF games")
    async def game_help_cmd(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=build_game_help_embed(), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Launcher(bot))
