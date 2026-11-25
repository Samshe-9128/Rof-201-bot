# cogs/arcade_core.py
import traceback

import discord
from discord import app_commands
from discord.ext import commands

from core.config import RANKS, HAVColors, get_rank
from core.database import db
from core.permissions import ensure_session_player
from core.ui import get_alliance_short, hav_embed

class LeaderboardFilterView(discord.ui.View):
    """Interactive Leaderboard selector for Overall, Weekly, and Individual Games."""

    def __init__(
        self,
        cog: "ArcadeCore",
        user_id: int,
        scope: str = "overall",
        game_name: str | None = None,
    ):
        super().__init__(timeout=180.0)
        self.cog = cog
        self.user_id = user_id
        self.scope = scope
        self.game_name = game_name

        game_options = [
            discord.SelectOption(label="All Games (Overall All-Time)", value="overall"),
            discord.SelectOption(label="Weekly Leaderboard (Last 7 Days)", value="weekly"),
            discord.SelectOption(label="Four-Digit Codebreaker", value="game:Codebreaker"),
            discord.SelectOption(label="Reaction Race", value="game:Reaction Race"),
            discord.SelectOption(label="Reaction Speed Test", value="game:Reaction Speed Test"),
            discord.SelectOption(label="Wordle", value="game:Wordle"),
            discord.SelectOption(label="Word Scramble", value="game:Word Scramble"),
            discord.SelectOption(label="Memory Challenge", value="game:Memory Challenge"),
            discord.SelectOption(label="Higher or Lower", value="game:Higher or Lower"),
            discord.SelectOption(label="Treasure Hunt", value="game:Treasure Hunt"),
            discord.SelectOption(label="Quick Math", value="game:Quick Math"),
            discord.SelectOption(label="Trivia", value="game:Trivia"),
            discord.SelectOption(label="Rock Paper Scissors", value="game:Rock Paper Scissors"),
            discord.SelectOption(label="Number Guessing", value="game:Number Guessing"),
            discord.SelectOption(label="Emoji Guessing", value="game:Emoji Guessing"),
            discord.SelectOption(label="Tic-Tac-Toe", value="game:Tic-Tac-Toe"),
            discord.SelectOption(label="Closest Wins", value="game:Closest Wins"),
            discord.SelectOption(label="Connect 4", value="game:Connect 4"),
        ]
        self.select = discord.ui.Select(
            placeholder="Filter Leaderboard (Overall / Weekly / Game)...",
            options=game_options,
        )
        self.select.callback = self._on_select
        self.add_item(self.select)

    async def _on_select(self, interaction: discord.Interaction):
        if not await ensure_session_player(
            interaction, self.user_id, "change leaderboard filters"
        ):
            return

        val = self.select.values[0] if self.select.values else "overall"
        if val.startswith("game:"):
            scope = "game"
            game_name = val.split(":", 1)[1]
        else:
            scope = val
            game_name = None

        # fix C: guard embed build so a DB hiccup doesn't leave a dead dropdown.
        try:
            embed = self.cog.build_leaderboard_embed(interaction.guild, scope, game_name)
        except Exception as e:
            print(f"[ARCADE] leaderboard embed build failed: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                return await interaction.response.send_message(
                    "⚠️ Could not load that leaderboard right now. Please try again.",
                    ephemeral=True,
                )
            except Exception:
                return

        self.scope = scope
        self.game_name = game_name
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception as e:
            print(f"[ARCADE] leaderboard edit failed: {e}")

class ProfileView(discord.ui.View):
    """Interactive 1-click Match History button attached to /profile."""

    def __init__(self, target: discord.abc.User, viewer_id: int, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.target = target
        self.viewer_id = viewer_id

    @discord.ui.button(label="Match History", style=discord.ButtonStyle.secondary, emoji="📜")
    async def history_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            rows = db.get_player_history(self.target.id, limit=10)
        except Exception as e:
            print(f"[ARCADE] get_player_history failed: {type(e).__name__}: {e}")
            return await interaction.response.send_message(
                "⚠️ Could not load match history right now. Please try again.",
                ephemeral=True,
            )
        if not rows:
            return await interaction.response.send_message(
                f"ℹ️ No recorded matches yet for **{self.target.display_name}**. Use `/games` to play!",
                ephemeral=True,
            )
        lines = []
        for r in rows:
            result = r.get("result", "?")
            icon = {"win": "🟢 WIN", "loss": "🔴 LOSS", "draw": "🟡 DRAW"}.get(result, result)
            reaction = r.get("reaction_ms")
            react_note = f" · ⚡ `{reaction} ms`" if reaction else ""
            played_at = r.get("played_at")
            timestamp = f"<t:{played_at}:R>" if played_at else "unknown"
            lines.append(
                f"• {timestamp} — **{r.get('game_name', '?')}** ({icon}) · "
                f"Score: `{r.get('score', 0)}` (`+{r.get('points_earned', 0)} pts`){react_note}"
            )
        embed = hav_embed(
            title=f"📜 {self.target.display_name} — RECENT MATCH HISTORY",
            description="\n".join(lines) or "*No matches to display.*",
            color=HAVColors.ARENA,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ArcadeCore(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = {}

    def reload_cache(self):
        try:
            self.data = {}
        except Exception as e:
            print(f"[ARCADE] reload_cache failed: {e}")
            self.data = {}

    # ---------- points ----------

    def add_points(
        self,
        user_id: int,
        points: int,
        game_name: str,
        won: bool = False,
    ) -> int:
        """
        Preserved legacy method — backed by unified SQLite DB.
        Signature kept identical to avoid breaking existing callers.
        """
        # fix E: never let a DB failure cascade into the caller's flow.
        try:
            new_pts = db.record_game_result(
                user_id=user_id,
                game_name=game_name,
                result="win" if won else "loss",
                score=points,
                points_earned=points,
                attempts=1,
            )
        except Exception as e:
            print(f"[ARCADE] add_points DB failure ({user_id} on {game_name}): {e}")
            return 0

        try:
            self.reload_cache()
        except Exception:
            pass
        return new_pts if new_pts is not None else 0

    # ---------- profile ----------

    def build_profile_embed(self, target: discord.abc.User) -> discord.Embed:
        # fix A: never trust DB not to throw.
        try:
            prof = db.get_player_profile(target.id) or {}
        except Exception as e:
            print(f"[ARCADE] get_player_profile failed ({target.id}): {e}")
            traceback.print_exc()
            prof = {}

        # fix B + H: safe access everywhere.
        points = int(prof.get("points", 0) or 0)
        best_reaction_ms = prof.get("best_reaction_ms")
        games_played = int(prof.get("games_played", 0) or 0)
        wins = int(prof.get("wins", 0) or 0)
        losses = int(prof.get("losses", 0) or 0)
        draws = int(prof.get("draws", 0) or 0)
        win_rate = prof.get("win_rate", 0)
        best_score = prof.get("best_score", 0)
        favourite_game = prof.get("favourite_game", "—")
        game_stats = prof.get("game_stats") or {}

        short = get_alliance_short()
        rank_name, rank_emoji = get_rank(points, alliance_short=short)
        react_str = f"{best_reaction_ms} ms" if best_reaction_ms is not None else "—"

        desc = (
            f"**Player:** {target.display_name}\n"
            f"**Rank:** {rank_emoji} **{rank_name}** (`{points} pts`)\n"
            f"**Games Played:** `{games_played}`\n"
            f"**Wins:** `{wins}` | **Losses:** `{losses}` | **Draws:** `{draws}`\n"
            f"**Win Rate:** `{win_rate}%`\n"
            f"**Best Score:** `{best_score}`\n"
            f"**Favourite Game:** `{favourite_game}`\n"
            f"**Best Reaction:** `{react_str}`"
        )
        embed = hav_embed(
            title=f"🛡️ {short} PLAYER PROFILE — {target.display_name.upper()}",
            description=desc,
            color=HAVColors.ARENA,
            thumbnail_url=(
                target.display_avatar.url
                if hasattr(target, "display_avatar")
                else None
            ),
        )

        if game_stats:
            # fix G: sort by most-played so the top 8 slots show the games
            # the player actually engages with, not the first ones they tried.
            try:
                sorted_stats = sorted(
                    game_stats.items(),
                    key=lambda kv: int((kv[1] or {}).get("played", 0) or 0),
                    reverse=True,
                )[:8]
            except Exception:
                sorted_stats = list(game_stats.items())[:8]

            lines = []
            for gname, st in sorted_stats:
                st = st or {}
                lines.append(
                    f"• **{gname}:** `{int(st.get('wins', 0) or 0)}W` / "
                    f"`{int(st.get('played', 0) or 0)}G` "
                    f"(Best: `{st.get('best_score', 0)}`)"
                )
            embed.add_field(name="🎮 Game Breakdown", value="\n".join(lines), inline=False)
        else:
            embed.add_field(
                name="🎮 Game Breakdown",
                value=f"No games played yet. Use `/games` to enter the {short} Gaming Arena!",
                inline=False,
            )

        # fix F: robust rank lookup that works for 2- or 3-tuples.
        next_rank = None
        for entry in RANKS:
            try:
                threshold, name = entry[0], entry[1]
            except (TypeError, IndexError):
                continue
            if points < threshold:
                next_rank = (threshold, f"{short} Legend" if name == "HAV Legend" else name)
                break

        if next_rank:
            pts_needed = next_rank[0] - points
            embed.set_footer(
                text=f"{pts_needed} points to reach {next_rank[1]} • {short} Gaming Arena"
            )
        else:
            embed.set_footer(text=f"Maximum Rank Achieved ({short} Legend) • {short} Gaming Arena")

        return embed

    async def send_profile_embed(
        self,
        interaction: discord.Interaction,
        target: discord.abc.User,
        ephemeral: bool = False,
    ):
        try:
            embed = self.build_profile_embed(target)
        except Exception as e:
            print(f"[ARCADE] build_profile_embed crashed: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                return await interaction.response.send_message(
                    "⚠️ Could not load that profile right now. Please try again.",
                    ephemeral=True,
                )
            except Exception:
                return

        view = ProfileView(target, interaction.user.id)
        try:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)
        except Exception as e:
            print(f"[ARCADE] send_profile_embed failed: {e}")

    # ---------- leaderboard ----------

    def _resolve_display_name(
        self,
        guild: discord.Guild | None,
        user_id: int,
        fallback_name: str = "",
    ) -> str:
        # fix I: guard the int cast.
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            return fallback_name or "Unknown Warrior"

        if guild:
            try:
                m = guild.get_member(uid)
                if m:
                    return m.display_name
            except Exception:
                pass
        try:
            u = self.bot.get_user(uid)
            if u:
                return u.display_name
        except Exception:
            pass
        return fallback_name or f"Warrior #{str(uid)[-4:]}"

    def build_leaderboard_embed(
        self,
        guild: discord.Guild | None,
        scope: str = "overall",
        game_name: str | None = None,
    ) -> discord.Embed:
        # fix A: DB hiccup must not kill the command.
        try:
            rows = db.get_leaderboard(scope=scope, game_name=game_name, limit=10)
        except Exception as e:
            print(f"[ARCADE] get_leaderboard failed: {type(e).__name__}: {e}")
            traceback.print_exc()
            rows = []

        short = get_alliance_short()
        if scope == "weekly":
            title = f"🏆 {short} LEADERBOARD — WEEKLY (LAST 7 DAYS)"
        elif scope == "game" and game_name:
            title = f"🏆 {short} LEADERBOARD — {game_name.upper()}"
        else:
            title = f"🏆 {short} LEADERBOARD — ALL-TIME OVERALL"

        if not rows:
            return hav_embed(
                title=title,
                description=(
                    "No recorded matches for this category yet! "
                    "Use `/games` to claim the #1 spot."
                ),
                color=HAVColors.GOLD,
            )

        lines = []
        for idx, r in enumerate(rows, 1):
            # fix D: tolerate malformed rows instead of crashing the whole list.
            try:
                uid = int(r.get("user_id", 0) or 0)
            except (TypeError, ValueError):
                uid = 0
            name = self._resolve_display_name(guild, uid, r.get("username", ""))
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"`#{idx}`")

            if scope == "game":
                wins = int(r.get("wins", 0) or 0)
                gp = int(r.get("games_played", 0) or 0)
                best_reaction = r.get("best_reaction_ms")
                react_part = f" · ⚡ `{best_reaction} ms`" if best_reaction else ""
                lines.append(
                    f"{medal} **{name}** — `{wins}W / {gp}G` · "
                    f"Best: `{r.get('best_score', 0)}`{react_part}"
                )
            else:
                pts = int(r.get("points", 0) or 0)
                wins = int(r.get("wins", 0) or 0)
                gp = int(r.get("games_played", 0) or 0)
                rank_name, rank_emoji = get_rank(pts, alliance_short=short)
                lines.append(
                    f"{medal} **{name}** — {rank_emoji} **`{pts} pts`** "
                    f"({rank_name}) · `{wins}W/{gp}G`"
                )

        return hav_embed(
            title=title,
            description="\n".join(lines),
            color=HAVColors.GOLD,
        )

    async def send_leaderboard_interactive(
        self,
        interaction: discord.Interaction,
        scope: str = "overall",
        game_name: str | None = None,
        ephemeral: bool = False,
    ):
        try:
            embed = self.build_leaderboard_embed(
                interaction.guild, scope=scope, game_name=game_name
            )
        except Exception as e:
            print(f"[ARCADE] leaderboard build crashed: {e}")
            traceback.print_exc()
            try:
                return await interaction.response.send_message(
                    "⚠️ Could not load the leaderboard right now. Please try again.",
                    ephemeral=True,
                )
            except Exception:
                return

        view = LeaderboardFilterView(
            self, interaction.user.id, scope=scope, game_name=game_name
        )
        try:
            await interaction.response.send_message(
                embed=embed, view=view, ephemeral=ephemeral
            )
        except Exception as e:
            print(f"[ARCADE] send_leaderboard_interactive failed: {e}")

    # ---------- commands ----------

    @app_commands.command(
        name="profile",
        description="View your Player Profile, gaming statistics, and match history",
    )
    @app_commands.checks.cooldown(1, 3.0)
    async def profile_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.User | None = None,
    ):
        target = member or interaction.user
        await self.send_profile_embed(interaction, target, ephemeral=False)

    @app_commands.command(
        name="leaderboard",
        description="View the Gaming Leaderboard (Overall, Weekly, and Per-Game)",
    )
    @app_commands.checks.cooldown(1, 3.0)
    @app_commands.describe(scope="Choose Overall All-Time or Weekly")
    @app_commands.choices(
        scope=[
            app_commands.Choice(name="Overall All-Time", value="overall"),
            app_commands.Choice(name="Weekly (Last 7 Days)", value="weekly"),
        ]
    )
    async def leaderboard_cmd(
        self,
        interaction: discord.Interaction,
        scope: str = "overall",
    ):
        await self.send_leaderboard_interactive(interaction, scope=scope, ephemeral=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(ArcadeCore(bot))