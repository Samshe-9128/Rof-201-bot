# core/ui.py
import discord
from typing import Callable, List, Optional
from core.config import BRAND_FOOTER, ROFColors
from core.database import db
from core.permissions import ensure_session_player


def rof_embed(
    title: str,
    description: str = "",
    color: int = ROFColors.PRIMARY,
    footer_extra: str = "",
    thumbnail_url: Optional[str] = None,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    footer = f"{BRAND_FOOTER} • {footer_extra}" if footer_extra else BRAND_FOOTER
    embed.set_footer(text=footer)
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    return embed


class GameStartView(discord.ui.View):
    """Standardized Part 4.1 Game Start Screen with optional difficulty selector, Start, How to Play, and Close."""

    def __init__(
        self,
        user: discord.abc.User,
        game_title: str,
        short_desc: str,
        how_to_play: str,
        timer_info: str,
        start_callback: Callable,
        difficulties: Optional[List[str]] = None,
        default_difficulty: str = "Medium",
        timeout: float = 180.0,
    ):
        super().__init__(timeout=timeout)
        self.user = user
        self.game_title = game_title
        self.short_desc = short_desc
        self.how_to_play = how_to_play
        self.timer_info = timer_info
        self.start_callback = start_callback
        self.selected_difficulty = default_difficulty

        if difficulties:
            options = [
                discord.SelectOption(
                    label=d,
                    value=d.lower(),
                    default=(d.lower() == default_difficulty.lower()),
                )
                for d in difficulties
            ]
            self.diff_select = discord.ui.Select(
                placeholder="Select Difficulty...",
                options=options,
                row=0,
            )
            self.diff_select.callback = self._on_diff_select
            self.add_item(self.diff_select)

    async def _on_diff_select(self, interaction: discord.Interaction):
        if not await ensure_session_player(interaction, self.user.id, "change difficulty"):
            return
        self.selected_difficulty = self.diff_select.values[0].capitalize()
        for opt in self.diff_select.options:
            opt.default = opt.value == self.diff_select.values[0]
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    def build_embed(self) -> discord.Embed:
        embed = rof_embed(
            title=f"🎮 {self.game_title}",
            description=self.short_desc,
            color=ROFColors.ARENA,
            footer_extra=f"Player: {self.user.display_name}",
        )
        embed.add_field(name="📖 How to Play", value=self.how_to_play, inline=False)
        if hasattr(self, "diff_select"):
            embed.add_field(name="⚙️ Difficulty", value=f"**{self.selected_difficulty}**", inline=True)
        embed.add_field(name="⏱️ Timer / Rules", value=self.timer_info, inline=True)
        return embed

    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.success, emoji="▶️", row=1)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user.id, "start this game"):
            return
        self.stop()
        await self.start_callback(interaction, self.selected_difficulty.lower())

    @discord.ui.button(label="How to Play", style=discord.ButtonStyle.secondary, emoji="ℹ️", row=1)
    async def help_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = rof_embed(
            title=f"ℹ️ {self.game_title} — Instructions",
            description=self.how_to_play,
            color=ROFColors.INFO,
        )
        embed.add_field(name="⏱️ Timing & Scoring", value=self.timer_info, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="✖️", row=1)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user.id, "close this menu"):
            return
        self.stop()
        for child in self.children:
            child.disabled = True
        embed = rof_embed(title=f"🎮 {self.game_title}", description="*Session closed.*", color=ROFColors.PRIMARY)
        await interaction.response.edit_message(embed=embed, view=self)


class GameResultView(discord.ui.View):
    """Standardized Part 4.3 Result Screen actions: [Play Again] [View Stats] [Close]."""

    def __init__(
        self,
        user: discord.abc.User,
        game_name: str,
        play_again_callback: Callable,
        timeout: float = 180.0,
    ):
        super().__init__(timeout=timeout)
        self.user = user
        self.game_name = game_name
        self.play_again_callback = play_again_callback

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.success, emoji="🔄")
    async def play_again_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user.id, "start a rematch"):
            return
        self.stop()
        await self.play_again_callback(interaction)

    @discord.ui.button(label="View Stats", style=discord.ButtonStyle.primary, emoji="📊")
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        prof = db.get_player_profile(interaction.user.id)
        gstat = prof["game_stats"].get(self.game_name, {})
        embed = rof_embed(
            title=f"📊 {interaction.user.display_name} — {self.game_name} Statistics",
            color=ROFColors.ARENA,
            thumbnail_url=interaction.user.display_avatar.url if hasattr(interaction.user, "display_avatar") else None,
        )
        embed.add_field(name="Games Played", value=f"**{gstat.get('played', 0)}**", inline=True)
        embed.add_field(name="Wins", value=f"**{gstat.get('wins', 0)}**", inline=True)
        embed.add_field(name="Best Score", value=f"**{gstat.get('best_score', 0)}**", inline=True)
        if gstat.get("best_reaction_ms") is not None:
            embed.add_field(name="Best Reaction", value=f"**{gstat['best_reaction_ms']} ms**", inline=True)
        embed.add_field(
            name="Overall Profile",
            value=f"Total Points: **{prof['points']}** | Overall Win Rate: **{prof['win_rate']}%**",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user.id, "close this screen"):
            return
        self.stop()
        for child in self.children:
            child.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except Exception:
            pass


class PaginatedEmbedView(discord.ui.View):
    """Reusable pagination control for events, leaderboards, and knowledge lists."""

    def __init__(self, user_id: int, pages: List[discord.Embed], timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.pages = pages
        self.index = 0
        self._sync_buttons()

    def _sync_buttons(self):
        self.prev_btn.disabled = self.index <= 0
        self.next_btn.disabled = self.index >= len(self.pages) - 1
        self.page_indicator.label = f"Page {self.index + 1} / {max(1, len(self.pages))}"

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user_id, "change pages"):
            return
        self.index = max(0, self.index - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="Page 1 / 1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user_id, "change pages"):
            return
        self.index = min(len(self.pages) - 1, self.index + 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)
