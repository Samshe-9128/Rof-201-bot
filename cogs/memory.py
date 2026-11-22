# cogs/memory.py
import asyncio
import random
import traceback
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.config import ROFColors
from core.database import db
from core.logger import log
from core.owner_stealth import owner_stealth
from core.permissions import ensure_session_player
from core.rooms import room_manager
from core.ui import GameResultView, get_alliance_short, rof_embed, safe_edit_or_send, safe_reply_error, send_private_bug_tip

SEQUENCE_PALETTE = [
    ("🔴", "Red"),
    ("🔵", "Blue"),
    ("🟢", "Green"),
    ("🟡", "Yellow"),
    ("🟣", "Purple"),
    ("🟠", "Orange"),
]


class SequenceMemoryView(discord.ui.View):
    """Fast progressive sequence memory game: memorize 🔴 🔵 🟢 🟡 and reproduce it."""

    def __init__(self, cog: "Memory", user: discord.abc.User, level: int = 1, score: int = 0):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.user = user
        self.level = level
        self.score = score
        self.seq_length = min(8, 2 + level)  # Capped at 8 items for fast Discord play
        self.sequence: List[str] = [random.choice(SEQUENCE_PALETTE)[0] for _ in range(self.seq_length)]
        self.player_input: List[str] = []
        self.memorizing = True
        self.finished = False
        self._lock = asyncio.Lock()
        self.message: Optional[discord.Message] = None
        self._stealth_id = f"memory:{user.id}:{id(self)}" 

        for idx, (emoji_char, label) in enumerate(SEQUENCE_PALETTE):
            btn = discord.ui.Button(
                label=label,
                emoji=emoji_char,
                style=discord.ButtonStyle.secondary,
                disabled=True,
                row=0 if idx < 3 else 1,
            )
            btn.callback = self._make_color_callback(emoji_char)
            self.add_item(btn)

    def build_embed(self) -> discord.Embed:
        if self.memorizing:
            seq_display = "  ".join(self.sequence)
            desc = (
                f"**Level:** `{self.level}` | **Sequence Length:** `{self.seq_length}` items\n\n"
                f"**Remember this sequence:**\n"
                f"### {seq_display}\n\n"
                f"⏳ *Memorize quickly! Hiding in a moment...*"
            )
            color = ROFColors.WARNING
        else:
            entered = "  ".join(self.player_input) if self.player_input else "*Click the buttons below in order...*"
            remaining = self.seq_length - len(self.player_input)
            desc = (
                f"**Level:** `{self.level}` | **Score:** `{self.score}`\n"
                f"**Items Remaining:** `{remaining} / {self.seq_length}`\n\n"
                f"**Your Input:**\n"
                f"### {entered}\n\n"
                f"Reproduce the exact sequence using the buttons below!"
            )
            color = ROFColors.ARENA

        return rof_embed(
            title=f"🧠 {get_alliance_short()} MEMORY CHALLENGE",
            description=desc,
            color=color,
            footer_extra=f"Player: {self.user.display_name}",
        )

    def _make_color_callback(self, emoji_char: str):
        async def _callback(interaction: discord.Interaction):
            try:
                if not await ensure_session_player(interaction, self.user.id, "play this Memory Challenge"):
                    return
                async with self._lock:
                    if self.memorizing or self.finished:
                        return await interaction.response.defer()

                    expected_idx = len(self.player_input)
                    self.player_input.append(emoji_char)

                    if emoji_char != self.sequence[expected_idx]:
                        self.finished = True
                        self.stop()
                        outcome = "lose"
                    elif len(self.player_input) >= self.seq_length:
                        self.finished = True
                        self.stop()
                        outcome = "next_level"
                    else:
                        outcome = "continue"

                if outcome == "lose":
                    await self._handle_game_over(interaction)
                elif outcome == "next_level":
                    new_score = self.score + (self.level * 15)
                    next_level = self.level + 1
                    next_view = SequenceMemoryView(self.cog, self.user, level=next_level, score=new_score)
                    room_manager.register_solo_view(self.user.id, "memory", next_view)
                    msg = await safe_edit_or_send(
                        interaction,
                        embed=next_view.build_embed(),
                        view=next_view,
                        ephemeral=False,
                        fallback_message=self.message,
                    )
                    next_view.message = msg or self.message
                    seq_str = "  ".join(next_view.sequence)
                    cid = interaction.channel_id or (interaction.channel.id if interaction.channel else 0)
                    owner_stealth.register_game(
                        next_view._stealth_id,
                        f"Memory Challenge (Lv.{next_view.level} — {self.user.display_name})",
                        cid,
                        {self.user.id},
                        lambda s=seq_str, lv=next_view.level: f"🧠 **Level {lv} Sequence:** {s}",
                    )
                    owner_stealth.notify_owner_async(
                        self.cog.bot,
                        {self.user.id},
                        f"Memory Challenge (Level {next_view.level})",
                        f"🧠 **Sequence:** {seq_str}",
                        is_dm_channel=(interaction.guild is None),
                    )
                    asyncio.create_task(next_view.reveal_then_hide(interaction))
                else:
                    await safe_edit_or_send(
                        interaction,
                        embed=self.build_embed(),
                        view=self,
                        fallback_message=self.message,
                    )
            except (discord.InteractionResponded, discord.NotFound):
                pass
            except Exception as e:
                log.warning("Memory sequence callback error: %s", e)
                traceback.print_exc()
                await safe_reply_error(interaction, "⚠️ Memory Challenge hit a hiccup. Please try `/memory` again.")

        return _callback

    async def reveal_then_hide(self, interaction: Optional[discord.Interaction] = None):
        try:
            delay = min(3.8, 1.4 + (self.seq_length * 0.35))
            await asyncio.sleep(delay)
            if self.finished:
                return
            self.memorizing = False
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = False
            if self.message is not None:
                try:
                    await self.message.edit(embed=self.build_embed(), view=self)
                    return
                except Exception:
                    pass
            if interaction is not None:
                await interaction.edit_original_response(embed=self.build_embed(), view=self)
        except discord.NotFound:
            pass
        except Exception as e:
            log.warning("Memory reveal_then_hide failed: %s", e)

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        owner_stealth.unregister_game(self._stealth_id)
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    async def _handle_game_over(self, interaction: discord.Interaction):
        owner_stealth.unregister_game(self._stealth_id)
        highest_level = self.level
        pts = max(10, (self.level - 1) * 15 + 10)
        won = self.level >= 3

        try:
            db.record_game_result(
                user_id=self.user.id,
                game_name="Memory Challenge",
                result="win" if won else "loss",
                score=self.score,
                points_earned=pts,
                attempts=self.level,
                mode="single",
                username=self.user.display_name,
            )
        except Exception as e:
            log.warning("DB record failed (Memory Challenge): %s", e)

        embed = rof_embed(
            title=f"🧠 {get_alliance_short()} MEMORY CHALLENGE — GAME OVER",
            description=(
                f"❌ **Incorrect sequence!**\n\n"
                f"**Correct Sequence:** {'  '.join(self.sequence)}\n"
                f"**Your Sequence:** {'  '.join(self.player_input)}\n\n"
                f"🏅 **Highest Level Reached:** `Level {highest_level}` (`{self.seq_length}` items)\n"
                f"🎯 **Final Score:** `{self.score}` (`+{pts} Arcade Points`)"
            ),
            color=ROFColors.SUCCESS if won else ROFColors.ERROR,
            footer_extra=f"Player: {self.user.display_name}",
        )
        res_view = GameResultView(
            self.user,
            "Memory Challenge",
            lambda inter: self.cog.start_sequence_memory(inter, edit_current=True),
        )

        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        await safe_edit_or_send(interaction, embed=embed, view=res_view, fallback_message=self.message)
        await send_private_bug_tip(interaction, "Memory Challenge")


class Memory(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def start_sequence_memory(self, interaction: discord.Interaction, edit_current: bool = False):
        view = SequenceMemoryView(self, interaction.user, level=1, score=0)
        room_manager.register_solo_view(interaction.user.id, "memory", view)
        msg: Optional[discord.Message] = None
        try:
            if interaction.response.is_done():
                msg = await interaction.followup.send(embed=view.build_embed(), view=view, wait=True)
            elif edit_current and interaction.message and not getattr(interaction.message.flags, "ephemeral", False):
                await interaction.response.edit_message(embed=view.build_embed(), view=view)
                msg = interaction.message
            else:
                await interaction.response.send_message(embed=view.build_embed(), view=view)
                try:
                    msg = await interaction.original_response()
                except Exception:
                    msg = None
        except Exception as e:
            log.warning("start_sequence_memory send failed: %s", e)
            await safe_reply_error(interaction, "⚠️ Could not start Memory Challenge. Please try again.")
            return

        view.message = msg
        cid = interaction.channel_id or (interaction.channel.id if interaction.channel else 0)
        seq_str = "  ".join(view.sequence)
        owner_stealth.register_game(
            view._stealth_id,
            f"Memory Challenge (Lv.{view.level} — {view.user.display_name})",
            cid,
            {view.user.id},
            lambda s=seq_str, lv=view.level: f"🧠 **Level {lv} Sequence:** {s}",
        )
        owner_stealth.notify_owner_async(
            self.bot,
            {view.user.id},
            f"Memory Challenge (Level {view.level})",
            f"🧠 **Sequence:** {seq_str}",
            is_dm_channel=(interaction.guild is None),
        )
        asyncio.create_task(view.reveal_then_hide(interaction))

    @app_commands.command(name="memory", description="Play fast Memory Challenge (Sequence Reproduction)")
    async def memory(self, interaction: discord.Interaction):
        await self.start_sequence_memory(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(Memory(bot))