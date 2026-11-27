# core/ui.py
import asyncio
import traceback
import discord
from collections.abc import Callable
from core.config import BRAND_FOOTER, BRAND_NAME, BRAND_SHORT, OWNER_ID, HAVColors
from core.database import db
from core.logger import log
from core.permissions import ensure_session_player

def get_alliance_short() -> str:
    return BRAND_SHORT

def get_alliance_name() -> str:
    return BRAND_NAME

def get_alliance_footer() -> str:
    return BRAND_FOOTER

def hav_embed(
    title: str,
    description: str = "",
    color: int = HAVColors.PRIMARY,
    footer_extra: str = "",
    thumbnail_url: str | None = None,
) -> discord.Embed:
    safe_title = str(title)[:256] if title is not None else ""
    safe_desc = str(description)[:4096] if description is not None else ""
    embed = discord.Embed(title=safe_title, description=safe_desc, color=color)
    base_footer = get_alliance_footer()
    footer = f"{base_footer} • {footer_extra}" if footer_extra else base_footer
    embed.set_footer(text=footer[:2048])
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    return embed

def get_owner_contact_line() -> str:
    """Return a clean owner-contact line tagging OWNER_ID (intended for private/ephemeral messages)."""
    if OWNER_ID:
        return f"🐛 *Found a bug or error in me? Contact the owner: <@{OWNER_ID}>*"
    return "🐛 *Found a bug or error in me? Please contact the bot owner.*"

class BugReportModal(discord.ui.Modal, title="🐛 Report a Bug to the Bot Owner"):
    details = discord.ui.Label(
        text="What bug or error did you find?",
        component=discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            placeholder="Describe what happened (only you and the bot owner will see this)...",
            min_length=3,
            max_length=1000,
            required=True,
        ),
    )

    def __init__(self, context_label: str = "HAV Bot"):
        super().__init__()
        self.context_label = context_label

    async def on_submit(self, interaction: discord.Interaction):
        report_text = (self.details.component.value or "").strip()
        owner_tag = f"<@{OWNER_ID}>" if OWNER_ID else "the bot owner"

        # Privately DM the bot owner (only reporter + owner see this; never posted publicly)
        dm_sent = False
        if OWNER_ID:
            client = getattr(interaction, "client", None)
            if client is None:
                try:
                    import bot as _bot_mod
                    client = getattr(_bot_mod, "bot", None)
                except Exception:
                    client = None
            if client is not None:
                try:
                    owner_user = client.get_user(int(OWNER_ID)) or await client.fetch_user(int(OWNER_ID))
                    if owner_user:
                        where = (
                            f"#{interaction.channel.name} ({interaction.guild.name})"
                            if interaction.guild and interaction.channel
                            else "Direct Message"
                        )
                        emb = hav_embed(
                            title="🐛 PRIVATE BUG REPORT",
                            description=report_text[:3500],
                            color=HAVColors.WARNING,
                            footer_extra=f"Context: {self.context_label}",
                        )
                        emb.add_field(
                            name="Reported By",
                            value=f"{interaction.user.mention} (`{interaction.user.display_name}` / `{interaction.user.id}`)",
                            inline=True,
                        )
                        emb.add_field(name="Location", value=where, inline=True)
                        await owner_user.send(embed=emb)
                        dm_sent = True
                except Exception:
                    dm_sent = False

        if dm_sent:
            reply = (
                f"✅ **Bug report sent privately to {owner_tag}!**\n"
                f"Only you and {owner_tag} can see this report. You can also DM {owner_tag} directly anytime."
            )
        else:
            reply = (
                f"🐛 **Thanks for reporting!** Please contact the bot owner directly: {owner_tag}\n"
                f"*(Only you can see this message.)*"
            )
        try:
            await interaction.response.send_message(reply, ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send(reply, ephemeral=True)
            except Exception:
                pass

class BugReportPromptView(discord.ui.View):
    """Lightweight private button so a player can send a bug report directly to the Owner."""

    def __init__(self, context_label: str = "HAV Bot", timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.context_label = context_label

    @discord.ui.button(label="Report Bug to Owner", style=discord.ButtonStyle.secondary, emoji="🐛")
    async def report_bug_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BugReportModal(self.context_label))

    async def on_timeout(self):
        for child in self.children:
            try:
                child.disabled = True
            except Exception:
                pass

async def send_private_bug_tip(
    interaction: discord.Interaction | None,
    context_label: str = "Game Session",
) -> None:
    """
    Send a private (ephemeral) post-game message visible ONLY to the player,
    tagging the Owner and offering a private 'Report Bug to Owner' button.
    """
    if interaction is None or not interaction.response.is_done():
        return
    try:
        owner_tag = f"<@{OWNER_ID}>" if OWNER_ID else "the bot owner"
        msg = (
            f"🐛 Found any bug or error in me during **{context_label}**? "
            f"Contact the owner {owner_tag} or click **Report Bug to Owner** below! *(Only you can see this.)*"
        )
        await interaction.followup.send(
            msg,
            view=BugReportPromptView(context_label),
            ephemeral=True,
        )
    except Exception:
        pass

async def safe_reply_error(
    interaction: discord.Interaction | None,
    message: str = "⚠️ Something went wrong while running that action. Please try again.",
) -> None:
    """Always send a visible ephemeral error (with private owner contact tag) so Discord never hangs."""
    if interaction is None:
        return
    contact_line = get_owner_contact_line()
    full_msg = message if "Contact the owner:" in message else f"{message}\n{contact_line}"
    if len(full_msg) > 1990:
        full_msg = full_msg[:1990]
    view = BugReportPromptView("Bot Error")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(full_msg, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(full_msg, view=view, ephemeral=True)
    except Exception:
        pass

async def safe_defer(interaction: discord.Interaction | None, ephemeral: bool = False) -> None:
    """Safely acknowledge an interaction if it hasn't been responded to yet."""
    if interaction is None:
        return
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral)
    except Exception:
        pass

async def safe_edit_or_send(
    interaction: discord.Interaction | None,
    *,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
    content: str | None = None,
    ephemeral: bool = False,
    fallback_message: discord.Message | None = None,
) -> discord.Message | None:
    """
    Reliably update an interaction message or send a fresh one without ever leaving
    the interaction unacknowledged ('The application did not respond').
    """
    kwargs = {}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if view is not None:
        kwargs["view"] = view

    if interaction is not None:
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(**kwargs)
                return interaction.message
        except Exception:
            pass

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(**kwargs, ephemeral=ephemeral)
                try:
                    return await interaction.original_response()
                except Exception:
                    return None
            else:
                return await interaction.followup.send(**kwargs, ephemeral=ephemeral, wait=True)
        except Exception:
            pass

    if fallback_message is not None:
        try:
            await fallback_message.edit(**kwargs)
            return fallback_message
        except Exception:
            pass

    if interaction is not None and interaction.channel is not None:
        try:
            return await interaction.channel.send(**kwargs)
        except Exception:
            pass
    return None

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
        difficulties: list[str] | None = None,
        default_difficulty: str = "Medium",
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.user = user
        self.game_title = game_title
        self.short_desc = short_desc
        self.how_to_play = how_to_play
        self.timer_info = timer_info
        self.start_callback = start_callback
        self.selected_difficulty = default_difficulty
        self.message: discord.Message | None = None
        self._started = False
        self._lock = asyncio.Lock()

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
        try:
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        except Exception:
            await safe_reply_error(interaction, "⚠️ Could not update difficulty. Please try again.")

    def build_embed(self) -> discord.Embed:
        embed = hav_embed(
            title=f"🎮 {self.game_title}",
            description=self.short_desc,
            color=HAVColors.ARENA,
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
        async with self._lock:
            if self._started:
                return await safe_defer(interaction, ephemeral=True)
            self._started = True
            self.stop()
        try:
            await self.start_callback(interaction, self.selected_difficulty.lower())
        except Exception as e:
            self._started = False
            log.error("GameStartView start_callback error (%s): %s: %s", self.game_title, type(e).__name__, e)
            traceback.print_exc()
            await safe_reply_error(interaction, "⚠️ Could not start the game right now. Please try again.")

    @discord.ui.button(label="How to Play", style=discord.ButtonStyle.secondary, emoji="ℹ️", row=1)
    async def help_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = hav_embed(
            title=f"ℹ️ {self.game_title} — Instructions",
            description=self.how_to_play,
            color=HAVColors.INFO,
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
        embed = hav_embed(title=f"🎮 {self.game_title}", description="*Session closed.*", color=HAVColors.PRIMARY)
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            await safe_defer(interaction, ephemeral=True)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

class GameResultView(discord.ui.View):
    """Standardized Part 4.3 Result Screen actions: [Play Again] [View Stats] [Close]."""

    def __init__(
        self,
        user: discord.abc.User,
        game_name: str,
        play_again_callback: Callable,
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.user = user
        self.game_name = game_name
        self.play_again_callback = play_again_callback
        self._started = False
        self._lock = asyncio.Lock()

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.success, emoji="🔄")
    async def play_again_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user.id, "start a rematch"):
            return
        async with self._lock:
            if self._started:
                return await safe_defer(interaction, ephemeral=True)
            self._started = True
            self.stop()
        try:
            await self.play_again_callback(interaction)
        except Exception as e:
            self._started = False
            log.error("GameResultView play_again error (%s): %s: %s", self.game_name, type(e).__name__, e)
            traceback.print_exc()
            await safe_reply_error(interaction, "⚠️ Could not start a new game right now. Please try `/games`.")

    @discord.ui.button(label="View Stats", style=discord.ButtonStyle.primary, emoji="📊")
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            prof = db.get_player_profile(interaction.user.id)
            gstat = prof["game_stats"].get(self.game_name, {})
            embed = hav_embed(
                title=f"📊 {interaction.user.display_name} — {self.game_name} Statistics",
                color=HAVColors.ARENA,
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
        except Exception as e:
            log.warning("GameResultView stats error: %s: %s", type(e).__name__, e)
            await safe_reply_error(interaction, "⚠️ Could not load your stats right now.")

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
            await safe_defer(interaction, ephemeral=True)

    @discord.ui.button(label="Report Bug", style=discord.ButtonStyle.secondary, emoji="🐛")
    async def report_bug_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BugReportModal(self.game_name))

    async def on_timeout(self):
        for child in self.children:
            try:
                child.disabled = True
            except Exception:
                pass

class PaginatedEmbedView(discord.ui.View):
    """Reusable pagination control for events, leaderboards, and knowledge lists."""

    def __init__(self, user_id: int, pages: list[discord.Embed], timeout: float = 300.0):
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

    async def on_timeout(self):
        for child in self.children:
            try:
                child.disabled = True
            except Exception:
                pass

def install_global_ui_error_handlers() -> None:
    """Ensure every View (Buttons/Selects) and Modal replies cleanly if an unexpected error occurs."""
    from core.logger import log

    async def _view_on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        log.error("UI View error in %s (%s): %s", type(self).__name__, type(item).__name__, error)
        traceback.print_exception(type(error), error, error.__traceback__)
        await safe_reply_error(
            interaction,
            "⚠️ That button or menu hit an unexpected error. Please run the command again.",
        )

    async def _modal_on_error(self, interaction: discord.Interaction, error: Exception):
        log.error("UI Modal error in %s: %s", type(self).__name__, error)
        traceback.print_exception(type(error), error, error.__traceback__)
        await safe_reply_error(
            interaction,
            "⚠️ Something went wrong while submitting that form. Please check your input and try again.",
        )

    discord.ui.View.on_error = _view_on_error
    discord.ui.Modal.on_error = _modal_on_error
