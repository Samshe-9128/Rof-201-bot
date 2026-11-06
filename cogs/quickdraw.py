# cogs/quickdraw.py
import asyncio
import random
import time
import traceback
import discord
from discord import app_commands
from discord.ext import commands
from typing import Dict, List, Optional

from core.config import ROFColors
from core.database import db
from core.permissions import ensure_session_player
from core.rooms import MultiplayerRoom, RoomLobbyView, room_manager
from core.ui import GameResultView, GameStartView, rof_embed


# ---------- SINGLE-PLAYER REACTION SPEED TEST (SPEC 2.2 GAME 5) ----------

class SingleReactionActiveView(discord.ui.View):
    def __init__(self, cog: "QuickDraw", user: discord.abc.User):
        super().__init__(timeout=20.0)
        self.cog = cog
        self.user = user
        self.ready = False
        self.signal_ts: float = 0.0
        self.finished = False
        self.wait_task: Optional[asyncio.Task] = None

    @discord.ui.button(label="WAIT...", style=discord.ButtonStyle.secondary, emoji="🛑")
    async def react_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(
            interaction, self.user.id, "click this reaction button"
        ):
            return
        if self.finished:
            return await interaction.response.defer()

        now = time.perf_counter()
        self.finished = True
        self.stop()
        if self.wait_task and not self.wait_task.done():
            self.wait_task.cancel()

        # False start check.
        if not self.ready:
            embed = rof_embed(
                title="⚠️ ROF REACTION SPEED TEST — FALSE START!",
                description=(
                    "WAIT...\n"
                    "You clicked **before** the signal turned to **READY!**\n\n"
                    "False starts do not count as valid records. Click **Play Again** to retry!"
                ),
                color=ROFColors.ERROR,
                footer_extra=f"Player: {self.user.display_name}",
            )
            res_view = GameResultView(
                self.user, "Reaction Speed Test", self.cog.start_single_reaction
            )
            return await interaction.response.edit_message(embed=embed, view=res_view)

        reaction_ms = max(1, int((now - self.signal_ts) * 1000))
        pts = max(10, 45 - (reaction_ms // 20))

        # fix B: DB failure must not block the result screen.
        try:
            db.record_game_result(
                user_id=self.user.id,
                game_name="Reaction Speed Test",
                result="win",
                score=max(10, 1000 - reaction_ms),
                points_earned=pts,
                attempts=1,
                duration_sec=round(reaction_ms / 1000.0, 3),
                reaction_ms=reaction_ms,
                mode="single",
                username=self.user.display_name,
            )
        except Exception as e:
            print(f"[QUICKDRAW] DB record failed (solo): {type(e).__name__}: {e}")

        # fix G: best-effort reload.
        arcade = self.cog.bot.get_cog("ArcadeCore")
        if arcade:
            try:
                arcade.reload_cache()
            except Exception as e:
                print(f"[QUICKDRAW] arcade reload failed: {e}")

        # fix C: safe profile access.
        try:
            prof = db.get_player_profile(self.user.id) or {}
        except Exception as e:
            print(f"[QUICKDRAW] profile fetch failed: {e}")
            prof = {}

        best_ms = prof.get("best_reaction_ms") or reaction_ms
        avg_ms = prof.get("avg_reaction_ms") or reaction_ms

        embed = rof_embed(
            title="⚡ ROF REACTION SPEED TEST — RESULT",
            description=(
                f"**READY!**\n"
                f"⚡ **Your Reaction:** `{reaction_ms} ms`\n"
                f"🏆 **Personal Best:** `{best_ms} ms`\n"
                f"📊 **Average Reaction:** `{avg_ms} ms`\n"
                f"🏅 **Points Earned:** `+{pts} pts`"
            ),
            color=ROFColors.SUCCESS,
            footer_extra=f"Player: {self.user.display_name}",
        )
        res_view = GameResultView(
            self.user, "Reaction Speed Test", self.cog.start_single_reaction
        )
        try:
            await interaction.response.edit_message(embed=embed, view=res_view)
        except Exception as e:
            print(f"[QUICKDRAW] solo result edit failed: {e}")

    async def trigger_signal(self, interaction: discord.Interaction):
        try:
            delay = random.uniform(2.0, 5.5)
            await asyncio.sleep(delay)
            if self.finished or self.ready:
                return

            # Mutate button + embed *before* the edit so the message
            # renders the READY state exactly once.
            self.react_btn.label = "READY! CLICK NOW!"
            self.react_btn.style = discord.ButtonStyle.success
            self.react_btn.emoji = "⚡"

            embed = rof_embed(
                title="🟢 ROF REACTION SPEED TEST — READY!",
                description="**READY!**\nClick the green button immediately!",
                color=ROFColors.SUCCESS,
                footer_extra=f"Player: {self.user.display_name}",
            )

            # fix A: only mark ready AFTER the message edit succeeds, so a click
            # on the still-visible WAIT button correctly becomes a false start.
            await interaction.edit_original_response(embed=embed, view=self)

            if self.finished:
                return
            self.signal_ts = time.perf_counter()
            self.ready = True

        except asyncio.CancelledError:
            pass
        except Exception as e:
            # fix H: log instead of swallowing.
            print(f"[QUICKDRAW] trigger_signal error: {type(e).__name__}: {e}")
            traceback.print_exc()

    async def on_timeout(self):
        # fix F: safety net if the user never clicks / signal task is lost.
        if self.finished:
            return
        self.finished = True
        try:
            if self.wait_task and not self.wait_task.done():
                self.wait_task.cancel()
        except Exception:
            pass
        # Try to nudge the message so the player knows to retry.
        try:
            embed = rof_embed(
                title="⏰ ROF REACTION SPEED TEST — TIMED OUT",
                description="No click registered. Click **Play Again** to retry!",
                color=ROFColors.ERROR,
                footer_extra=f"Player: {self.user.display_name}",
            )
            res_view = GameResultView(
                self.user, "Reaction Speed Test", self.cog.start_single_reaction
            )
            await self.message.edit(embed=embed, view=res_view)
        except Exception as e:
            print(f"[QUICKDRAW] solo on_timeout edit failed: {e}")


# ---------- MULTIPLAYER REACTION RACE (SPEC 3.2, 2–10 PLAYERS) ----------

class ReactionRaceActiveView(discord.ui.View):
    def __init__(self, cog: "QuickDraw", room: MultiplayerRoom):
        super().__init__(timeout=25.0)
        self.cog = cog
        self.room = room
        self.ready = False
        self.signal_ts: float = 0.0
        self.false_starts: Dict[int, discord.abc.User] = {}
        self.reactions: Dict[int, int] = {}
        self.finished = False
        self._finished_guard = False
        self.signal_task: Optional[asyncio.Task] = None
        self.message: Optional[discord.Message] = None

    def build_embed(self) -> discord.Embed:
        if not self.ready and not self.finished:
            title = "🛑 ROF REACTION RACE — READY SOON..."
            desc = (
                "**WAIT...**\n"
                "Watch closely! The button will turn green when the signal appears.\n"
                "⚠️ *Clicking before READY is a False Start and disqualifies you for this round!*"
            )
            color = ROFColors.WARNING
        elif self.ready and not self.finished:
            title = "🟢 ROF REACTION RACE — CLICK NOW!"
            desc = "⚡ **READY!** Click the button as fast as possible!"
            color = ROFColors.SUCCESS
        else:
            title = "🏁 ROF REACTION RACE — FINAL RANKINGS"
            desc = "Match complete! Here are the official reaction results:"
            color = ROFColors.GOLD

        embed = rof_embed(
            title=title, description=desc, color=color,
            footer_extra=f"Room {self.room.room_id}",
        )

        status_lines = []
        sorted_valid = sorted(self.reactions.items(), key=lambda x: x[1])
        rank_map = {uid: idx for idx, (uid, _) in enumerate(sorted_valid, 1)}

        for p in self.room.players:
            if p.id in self.false_starts:
                status_lines.append(f"❌ {p.mention} — **FALSE START** (Disqualified)")
            elif p.id in self.reactions:
                rk = rank_map[p.id]
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rk, f"`#{rk}`")
                status_lines.append(f"{medal} {p.mention} — ⚡ **`{self.reactions[p.id]} ms`**")
            else:
                status_lines.append(
                    f"⏳ {p.mention} — *Waiting...*"
                    if not self.finished
                    else f"💤 {p.mention} — *Did not click*"
                )

        embed.add_field(
            name="👥 Players & Live Results", value="\n".join(status_lines), inline=False
        )
        return embed

    @discord.ui.button(label="WAIT FOR SIGNAL...", style=discord.ButtonStyle.secondary, emoji="🛑")
    async def race_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.room.has_player(interaction.user.id):
            return await interaction.response.send_message(
                "⚠️ You are not a participant in this Reaction Race.", ephemeral=True
            )

        click_ts = time.perf_counter()
        async with self.room.lock:
            if self.finished:
                return await interaction.response.send_message(
                    "ℹ️ This race has already finished!", ephemeral=True
                )
            if interaction.user.id in self.false_starts:
                return await interaction.response.send_message(
                    "❌ You already false-started this round!", ephemeral=True
                )
            if interaction.user.id in self.reactions:
                return await interaction.response.send_message(
                    f"✅ Your reaction (`{self.reactions[interaction.user.id]} ms`) "
                    f"is already recorded!",
                    ephemeral=True,
                )

            if not self.ready:
                self.false_starts[interaction.user.id] = interaction.user
                if len(self.false_starts) >= len(self.room.players):
                    self.finished = True
                    if self.signal_task and not self.signal_task.done():
                        self.signal_task.cancel()
                await interaction.response.send_message(
                    "❌ **False Start!** You clicked before the READY signal and are "
                    "disqualified from this round.",
                    ephemeral=True,
                )
                if self.finished:
                    await self.finish_race()
                elif self.message:
                    try:
                        await self.message.edit(embed=self.build_embed(), view=self)
                    except Exception:
                        pass
                return

            ms = max(1, int((click_ts - self.signal_ts) * 1000))
            self.reactions[interaction.user.id] = ms
            is_first = len(self.reactions) == 1
            all_done = (len(self.reactions) + len(self.false_starts)) >= len(self.room.players)
            if all_done:
                self.finished = True

        await interaction.response.send_message(
            f"⚡ Reaction recorded: **`{ms} ms`**"
            f"{' (First click! 🥇)' if is_first else ''}!",
            ephemeral=True,
        )

        if self.finished:
            await self.finish_race()
        elif self.message:
            try:
                await self.message.edit(embed=self.build_embed(), view=self)
            except Exception:
                pass

    async def run_race_sequence(self):
        try:
            delay = random.uniform(2.2, 5.8)
            await asyncio.sleep(delay)
            if self.finished:
                return

            self.race_btn.label = "🔥 READY! CLICK NOW! 🔥"
            self.race_btn.style = discord.ButtonStyle.success
            self.race_btn.emoji = "⚡"

            if self.message:
                try:
                    await self.message.edit(embed=self.build_embed(), view=self)
                except Exception as e:
                    print(f"[QUICKDRAW] race signal edit failed: {e}")
                    return

            # fix A: only mark ready AFTER the message edit succeeds.
            if self.finished:
                return
            self.signal_ts = time.perf_counter()
            self.ready = True

            # 6-second window for reactions.
            await asyncio.sleep(6.0)
            if self.finished:
                return
            async with self.room.lock:
                if self.finished:
                    return
                self.finished = True
            await self.finish_race()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            # fix H: log instead of swallowing.
            print(f"[QUICKDRAW] run_race_sequence error: {type(e).__name__}: {e}")
            traceback.print_exc()

    async def on_timeout(self):
        # fix F: safety net.
        if self.finished:
            return
        try:
            await self.finish_race()
        except Exception as e:
            print(f"[QUICKDRAW] race on_timeout finish failed: {e}")

    def _disable_all_children(self):
        for child in self.children:
            try:
                child.disabled = True
            except Exception:
                pass

    async def finish_race(self):
        # fix I: idempotent.
        if self._finished_guard:
            return
        self._finished_guard = True

        self._disable_all_children()
        self.stop()
        self.room.status = "finished"

        # fix L: cancel leftover timer.
        if self.signal_task and not self.signal_task.done():
            try:
                self.signal_task.cancel()
            except Exception:
                pass

        # fix D: capture message before close_room may clear it.
        message = self.room.message or self.message
        try:
            room_manager.close_room(self.room.room_id)
        except Exception as e:
            print(f"[QUICKDRAW] close_room failed: {e}")

        sorted_valid = sorted(self.reactions.items(), key=lambda x: x[1])
        winner_id = sorted_valid[0][0] if sorted_valid else None
        arcade = self.cog.bot.get_cog("ArcadeCore")

        # fix B: per-player DB guards.
        for p in self.room.players:
            won = winner_id is not None and p.id == winner_id
            r_ms = self.reactions.get(p.id)
            pts = 45 if won else (15 if r_ms is not None else 5)
            try:
                db.record_game_result(
                    user_id=p.id,
                    game_name="Reaction Race",
                    result="win" if won else "loss",
                    score=max(10, 1000 - r_ms) if r_ms else 0,
                    points_earned=pts,
                    attempts=1,
                    duration_sec=round((r_ms or 0) / 1000.0, 3),
                    reaction_ms=r_ms,
                    mode="multi",
                    username=p.display_name,
                )
            except Exception as e:
                print(f"[QUICKDRAW] DB record failed ({p.id}): {e}")

        # fix G: reload once, guarded.
        if arcade:
            try:
                arcade.reload_cache()
            except Exception as e:
                print(f"[QUICKDRAW] arcade reload failed: {e}")

        embed = self.build_embed()
        if winner_id:
            # fix E: safe lookup.
            winner_user = discord.utils.get(self.room.players, id=winner_id)
            if winner_user:
                embed.add_field(
                    name="🏆 Winner",
                    value=(
                        f"🎉 **{winner_user.mention}** won the race with "
                        f"**`{self.reactions[winner_id]} ms`**!"
                    ),
                    inline=False,
                )
            else:
                embed.add_field(
                    name="🏆 Winner",
                    value=f"🎉 User `{winner_id}` finished first with "
                          f"**`{self.reactions[winner_id]} ms`**!",
                    inline=False,
                )
        else:
            embed.add_field(
                name="🏁 Result",
                value="⚠️ No valid clicks were recorded this round!",
                inline=False,
            )

        rematch_view = ReactionRaceRematchView(self.cog)
        if message is not None:
            try:
                await message.edit(embed=embed, view=rematch_view)
            except Exception as e:
                print(f"[QUICKDRAW] race final embed edit failed: {e}")


class ReactionRaceRematchView(discord.ui.View):
    def __init__(self, cog: "QuickDraw"):
        super().__init__(timeout=180)
        self.cog = cog

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.success, emoji="🔄")
    async def rematch_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await self.cog.open_reaction_race_room(interaction)
        except Exception as e:
            print(f"[QUICKDRAW] rematch failed: {e}")

    @discord.ui.button(label="View Stats", style=discord.ButtonStyle.primary, emoji="📊")
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # fix J: safe profile access.
        try:
            prof = db.get_player_profile(interaction.user.id) or {}
        except Exception as e:
            print(f"[QUICKDRAW] stats profile fetch failed: {e}")
            prof = {}

        best = prof.get("best_reaction_ms")
        avg = prof.get("avg_reaction_ms")
        points = prof.get("points", 0)

        embed = rof_embed(
            title=f"⚡ {interaction.user.display_name} — Reaction Stats",
            description=(
                f"**Best Reaction:** `{best if best is not None else '—'} ms`\n"
                f"**Average Reaction:** `{avg if avg is not None else '—'} ms`\n"
                f"**Total Points:** `{points}`"
            ),
            color=ROFColors.ARENA,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class QuickDraw(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def launch_single_reaction_menu(self, interaction: discord.Interaction):
        async def _start(inter: discord.Interaction, _diff: str):
            await self.start_single_reaction(inter)

        start_view = GameStartView(
            user=interaction.user,
            game_title="ROF REACTION SPEED TEST",
            short_desc="Measure how quickly you react to a visual signal in milliseconds.",
            how_to_play=(
                "1. Click **Start Game**.\n"
                "2. The screen will show **WAIT...** for a random interval.\n"
                "3. As soon as it turns green (**READY!**), click the button immediately!\n"
                "4. Clicking before READY is a **False Start**."
            ),
            timer_info="Random signal delay (2–6s) • Millisecond accuracy",
            start_callback=_start,
        )
        await interaction.response.send_message(
            embed=start_view.build_embed(), view=start_view, ephemeral=True
        )

    async def start_single_reaction(self, interaction: discord.Interaction):
        view = SingleReactionActiveView(self, interaction.user)
        embed = rof_embed(
            title="🛑 ROF REACTION SPEED TEST",
            description=(
                "**WAIT...**\n**WAIT...**\n"
                "*Click the button as soon as this screen turns GREEN!*"
            ),
            color=ROFColors.WARNING,
            footer_extra=f"Player: {interaction.user.display_name}",
        )
        try:
            await interaction.response.edit_message(embed=embed, view=view)
            # Keep a message reference for on_timeout.
            try:
                view.message = await interaction.original_response()
            except Exception:
                pass
            view.wait_task = asyncio.create_task(view.trigger_signal(interaction))
        except Exception as e:
            print(f"[QUICKDRAW] start_single_reaction failed: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⚠️ Could not start the Reaction Test. Please try again.",
                        ephemeral=True,
                    )
            except Exception:
                pass

    async def open_reaction_race_room(self, interaction: discord.Interaction):
        existing = room_manager.get_player_active_room(interaction.user.id, "reaction_race")
        if existing:
            return await interaction.response.send_message(
                f"⚠️ You are already in an active Reaction Race room (`{existing.room_id}`).",
                ephemeral=True,
            )

        room = room_manager.create_room(
            game_key="reaction_race",
            game_title="Reaction Race",
            host=interaction.user,
            min_players=2,
            max_players=10,
        )

        async def _on_start(start_inter: discord.Interaction, active_room: MultiplayerRoom):
            # fix K: guard view construction / first edit.
            try:
                race_view = ReactionRaceActiveView(self, active_room)
                await start_inter.response.edit_message(
                    embed=race_view.build_embed(), view=race_view
                )
                active_room.message = start_inter.message
                race_view.message = start_inter.message
                race_view.signal_task = asyncio.create_task(race_view.run_race_sequence())
            except Exception as e:
                print(f"[QUICKDRAW] _on_start failed: {type(e).__name__}: {e}")
                traceback.print_exc()
                try:
                    room_manager.close_room(active_room.room_id)
                except Exception:
                    pass
                try:
                    await start_inter.channel.send(
                        "⚠️ Failed to start the Reaction Race. Please try again."
                    )
                except Exception:
                    pass

        lobby = RoomLobbyView(
            room=room,
            on_start_callback=_on_start,
            extra_description=(
                "⚡ **Players:** 2–10 players\n"
                "🛑 **Rule:** Wait for the green **READY** signal. Early clicks are False Starts!"
            ),
        )
        await interaction.response.send_message(embed=lobby.build_embed(), view=lobby)
        try:
            room.message = await interaction.original_response()
        except Exception:
            pass

    @app_commands.command(
        name="quickdraw",
        description="Start a multiplayer Reaction Race (2-10 players) or solo Reaction Speed Test",
    )
    @app_commands.describe(
        mode="Choose 'multiplayer' (2-10 players) or 'solo' (personal reaction test)"
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Multiplayer Reaction Race (2-10 Players)", value="multi"),
            app_commands.Choice(name="Solo Reaction Speed Test", value="solo"),
        ]
    )
    async def quickdraw(self, interaction: discord.Interaction, mode: str = "multi"):
        if mode == "solo":
            await self.launch_single_reaction_menu(interaction)
        else:
            await self.open_reaction_race_room(interaction)


async def setup(bot):
    await bot.add_cog(QuickDraw(bot))