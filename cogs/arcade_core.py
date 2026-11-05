# cogs/arcade_core.py
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from core.config import RANKS, ROFColors, get_rank
from core.database import ARCADE_FILE, db
from core.permissions import ensure_session_player
from core.ui import rof_embed
import json
import os


def load_arcade():
    if os.path.exists(ARCADE_FILE):
        try:
            with open(ARCADE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


class LeaderboardFilterView(discord.ui.View):
    """Interactive Leaderboard selector for Overall, Weekly, All-Time, and Individual Games (Part 5)."""

    def __init__(self, cog: "ArcadeCore", user_id: int, scope: str = "overall", game_name: Optional[str] = None):
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
            discord.SelectOption(label="Memory Match (Pairs)", value="game:Memory Match"),
            discord.SelectOption(label="Quick Math", value="game:Quick Math"),
            discord.SelectOption(label="Trivia", value="game:Trivia"),
            discord.SelectOption(label="Rock Paper Scissors", value="game:Rock Paper Scissors"),
            discord.SelectOption(label="Number Guessing", value="game:Number Guessing"),
            discord.SelectOption(label="Emoji Guessing", value="game:Emoji Guessing"),
            discord.SelectOption(label="Undercover", value="game:Undercover"),
            discord.SelectOption(label="Connect 4", value="game:Connect 4"),
        ]
        self.select = discord.ui.Select(
            placeholder="Filter Leaderboard (Overall / Weekly / Game)...",
            options=game_options,
        )
        self.select.callback = self._on_select
        self.add_item(self.select)

    async def _on_select(self, interaction: discord.Interaction):
        if not await ensure_session_player(interaction, self.user_id, "change leaderboard filters"):
            return
        val = self.select.values[0]
        if val.startswith("game:"):
            self.scope = "game"
            self.game_name = val.split(":", 1)[1]
        else:
            self.scope = val
            self.game_name = None
        embed = self.cog.build_leaderboard_embed(interaction.guild, self.scope, self.game_name)
        await interaction.response.edit_message(embed=embed, view=self)


class ArcadeCore(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = load_arcade()

    def reload_cache(self):
        self.data = load_arcade()

    def add_points(self, user_id: int, points: int, game_name: str, won: bool = False) -> int:
        """Preserved method used by legacy/existing cogs, now backed by unified SQLite database."""
        new_pts = db.record_game_result(
            user_id=user_id,
            game_name=game_name,
            result="win" if won else "loss",
            score=points,
            points_earned=points,
            attempts=1,
        )
        self.reload_cache()
        return new_pts

    def build_profile_embed(self, target: discord.abc.User) -> discord.Embed:
        prof = db.get_player_profile(target.id)
        rank_name, rank_emoji = get_rank(prof["points"])
        react_str = f"{prof['best_reaction_ms']} ms" if prof["best_reaction_ms"] is not None else "—"

        desc = (
            f"**Player:** {target.display_name}\n"
            f"**Rank:** {rank_emoji} **{rank_name}** (`{prof['points']} pts`)\n"
            f"**Games Played:** `{prof['games_played']}`\n"
            f"**Wins:** `{prof['wins']}` | **Losses:** `{prof['losses']}` | **Draws:** `{prof['draws']}`\n"
            f"**Win Rate:** `{prof['win_rate']}%`\n"
            f"**Best Score:** `{prof['best_score']}`\n"
            f"**Favourite Game:** `{prof['favourite_game']}`\n"
            f"**Best Reaction:** `{react_str}`"
        )
        embed = rof_embed(
            title=f"🛡️ ROF PLAYER PROFILE — {target.display_name.upper()}",
            description=desc,
            color=ROFColors.ARENA,
            thumbnail_url=target.display_avatar.url if hasattr(target, "display_avatar") else None,
        )

        if prof["game_stats"]:
            lines = []
            for gname, st in list(prof["game_stats"].items())[:8]:
                lines.append(
                    f"• **{gname}:** `{st['wins']}W` / `{st['played']}G` (Best: `{st['best_score']}`)"
                )
            embed.add_field(name="🎮 Game Breakdown", value="\n".join(lines), inline=False)
        else:
            embed.add_field(
                name="🎮 Game Breakdown",
                value="No games played yet. Use `/games` to enter the ROF Gaming Arena!",
                inline=False,
            )

        next_rank = None
        for threshold, name, _ in RANKS:
            if prof["points"] < threshold:
                next_rank = (threshold, name)
                break
        if next_rank:
            pts_needed = next_rank[0] - prof["points"]
            embed.set_footer(text=f"{pts_needed} points to reach {next_rank[1]} • ROF Gaming Arena")
        else:
            embed.set_footer(text="Maximum Rank Achieved (ROF Legend) • ROF Gaming Arena")

        return embed

    async def send_profile_embed(
        self,
        interaction: discord.Interaction,
        target: discord.abc.User,
        ephemeral: bool = False,
    ):
        embed = self.build_profile_embed(target)
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    def _resolve_display_name(self, guild: Optional[discord.Guild], user_id: int, fallback_name: str = "") -> str:
        if guild:
            m = guild.get_member(int(user_id))
            if m:
                return m.display_name
        u = self.bot.get_user(int(user_id))
        if u:
            return u.display_name
        return fallback_name or f"Warrior #{str(user_id)[-4:]}"

    def build_leaderboard_embed(
        self,
        guild: Optional[discord.Guild],
        scope: str = "overall",
        game_name: Optional[str] = None,
    ) -> discord.Embed:
        rows = db.get_leaderboard(scope=scope, game_name=game_name, limit=10)
        if scope == "weekly":
            title = "🏆 ROF LEADERBOARD — WEEKLY (LAST 7 DAYS)"
        elif scope == "game" and game_name:
            title = f"🏆 ROF LEADERBOARD — {game_name.upper()}"
        else:
            title = "🏆 ROF LEADERBOARD — ALL-TIME OVERALL"

        if not rows:
            return rof_embed(
                title=title,
                description="No recorded matches for this category yet! Use `/games` to claim the #1 spot.",
                color=ROFColors.GOLD,
            )

        lines = []
        for idx, r in enumerate(rows, 1):
            uid = int(r["user_id"])
            name = self._resolve_display_name(guild, uid, r.get("username", ""))
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"`#{idx}`")
            pts = int(r.get("points", 0))
            wins = int(r.get("wins", 0))
            gp = int(r.get("games_played", 0))
            rank_name, rank_emoji = get_rank(pts)

            if scope == "game":
                react_part = f" · ⚡ `{r['best_reaction_ms']} ms`" if r.get("best_reaction_ms") else ""
                lines.append(
                    f"{medal} **{name}** — `{wins}W / {gp}G` · Best: `{r.get('best_score', 0)}`{react_part}"
                )
            else:
                lines.append(
                    f"{medal} **{name}** — {rank_emoji} **`{pts} pts`** ({rank_name}) · `{wins}W/{gp}G`"
                )

        return rof_embed(
            title=title,
            description="\n".join(lines),
            color=ROFColors.GOLD,
        )

    async def send_leaderboard_interactive(
        self,
        interaction: discord.Interaction,
        scope: str = "overall",
        game_name: Optional[str] = None,
        ephemeral: bool = False,
    ):
        embed = self.build_leaderboard_embed(interaction.guild, scope=scope, game_name=game_name)
        view = LeaderboardFilterView(self, interaction.user.id, scope=scope, game_name=game_name)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)

    # ---------- COMMANDS (Part 5 & Part 11: /profile, /leaderboard + preserved /arcade_profile, /arcade_leaderboard) ----------

    @app_commands.command(name="profile", description="View your ROF Player Profile and gaming statistics")
    async def profile_cmd(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        await self.send_profile_embed(interaction, target, ephemeral=False)

    @app_commands.command(name="arcade_profile", description="View your ROF Arcade profile and rank")
    async def arcade_profile_cmd(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        await self.send_profile_embed(interaction, target, ephemeral=False)

    @app_commands.command(name="leaderboard", description="View the ROF Gaming Leaderboard (Overall, Weekly, and Per-Game)")
    @app_commands.describe(scope="Choose Overall All-Time or Weekly")
    @app_commands.choices(
        scope=[
            app_commands.Choice(name="Overall All-Time", value="overall"),
            app_commands.Choice(name="Weekly (Last 7 Days)", value="weekly"),
        ]
    )
    async def leaderboard_cmd(self, interaction: discord.Interaction, scope: str = "overall"):
        await self.send_leaderboard_interactive(interaction, scope=scope, ephemeral=False)

    @app_commands.command(name="arcade_leaderboard", description="View the global ROF Arcade leaderboard")
    async def arcade_leaderboard_cmd(self, interaction: discord.Interaction):
        await self.send_leaderboard_interactive(interaction, scope="overall", ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(ArcadeCore(bot))