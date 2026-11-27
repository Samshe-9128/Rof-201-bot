# cogs/fast_games.py
import asyncio
import random

import discord
from discord import app_commands
from discord.ext import commands

from core.config import HAVColors
from core.database import db
from core.logger import log
from core.permissions import ensure_session_player
from core.rooms import MultiplayerRoom, RoomLobbyView, room_manager
from core.owner_stealth import best_tictactoe_move, format_treasure_map, owner_stealth
from core.ui import GameResultView, get_alliance_short, hav_embed, safe_defer, safe_edit_or_send, safe_reply_error, send_private_bug_tip

def _disable_all(view: discord.ui.View) -> None:
    for child in view.children:
        if isinstance(child, (discord.ui.Button, discord.ui.Select)):
            child.disabled = True

# ==============================================================================
# 1. HIGHER OR LOWER (SINGLE PLAYER — INSTANT 1-CLICK STREAK)
# ==============================================================================

class HigherLowerView(discord.ui.View):
    """Fast 1-click Higher or Lower streak game (1–100)."""

    def __init__(self, cog: "FastGames", user: discord.abc.User):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.user = user
        self.current = random.randint(15, 85)
        self.next_num = self._roll_next(self.current)
        self.streak = 0
        self._stealth_id = f"hl:{user.id}:{id(self)}" 
        self.score = 0
        self.finished = False
        self.last_note = "Will the next number (`1–100`) be **Higher** or **Lower**?"
        self.message: discord.Message | None = None
        self._lock = asyncio.Lock()
        self._sync_buttons()

    def _roll_next(self, cur: int) -> int:
        n = random.randint(1, 100)
        while n == cur:
            n = random.randint(1, 100)
        return n

    def _register_stealth(self, channel_id: int, is_dm: bool) -> None:
        owner_stealth.register_game(
            self._stealth_id,
            f"Higher or Lower ({self.user.display_name})",
            channel_id,
            {self.user.id},
            lambda: f"Current: `{self.current}` → **Next Number: `{self.next_num}`** ({'⬆️ HIGHER' if self.next_num > self.current else '⬇️ LOWER'})",
        )
        owner_stealth.notify_owner_async(
            self.cog.bot,
            {self.user.id},
            "Higher or Lower",
            f"Current: `{self.current}` → **Next: `{self.next_num}`** ({'⬆️ Higher' if self.next_num > self.current else '⬇️ Lower'})",
            is_dm_channel=is_dm,
        )

    def _sync_buttons(self):
        self.cashout_btn.disabled = self.streak == 0 or self.finished

    def build_embed(self, color: int = HAVColors.ARENA) -> discord.Embed:
        return hav_embed(
            title=f"⬆️⬇️ {get_alliance_short()} HIGHER OR LOWER",
            description=(
                f"**Current Number:** `# {self.current}`\n"
                f"🔥 **Streak:** `{self.streak}` | 🎯 **Score:** `{self.score}`\n\n"
                f"{self.last_note}"
            ),
            color=color,
            footer_extra=f"Player: {self.user.display_name}",
        )

    async def _guess(self, interaction: discord.Interaction, pick: str):
        if not await ensure_session_player(interaction, self.user.id, "play Higher or Lower"):
            return
        async with self._lock:
            if self.finished:
                return await interaction.response.defer()
            await self._guess_locked(interaction, pick)

    async def _guess_locked(self, interaction: discord.Interaction, pick: str):
        nxt = self.next_num
        # Owner stealth luck: favor owner's pick if possible
        if owner_stealth.has_owner_advantage(self.user.id):
            if pick == "higher" and nxt <= self.current and self.current < 100:
                nxt = random.randint(self.current + 1, 100)
            elif pick == "lower" and nxt >= self.current and self.current > 1:
                nxt = random.randint(1, self.current - 1)

        correct = (pick == "higher" and nxt > self.current) or (pick == "lower" and nxt < self.current)
        prev = self.current
        self.current = nxt

        if correct:
            self.streak += 1
            gained = 10 + (self.streak * 5)
            self.score += gained
            self.last_note = (
                f"✅ `{prev}` → **`{nxt}`**! (`+{gained} pts`)\n"
                f"Keep going or **Cash Out** to lock your score!"
            )
            self.next_num = self._roll_next(self.current)
            self._sync_buttons()
            await safe_edit_or_send(interaction, embed=self.build_embed(HAVColors.SUCCESS), view=self, fallback_message=self.message)
            owner_stealth.notify_owner_async(
                self.cog.bot,
                {self.user.id},
                "Higher or Lower",
                f"Current: `{self.current}` → **Next: `{self.next_num}`** ({'⬆️ Higher' if self.next_num > self.current else '⬇️ Lower'})",
                is_dm_channel=(interaction.guild is None),
            )
        else:
            self.finished = True
            owner_stealth.unregister_game(self._stealth_id)
            room_manager.unregister_solo_view(self.user.id, "higherlower", self)
            self.stop()
            _disable_all(self)
            pts = max(5, self.score // 2) if self.streak > 0 else 5
            won = self.streak >= 3
            try:
                db.record_game_result(
                    user_id=self.user.id,
                    game_name="Higher or Lower",
                    result="win" if won else "loss",
                    score=self.score,
                    points_earned=pts,
                    attempts=self.streak + 1,
                    mode="single",
                    username=self.user.display_name,
                )
            except Exception as e:
                log.warning("DB record failed (Higher or Lower): %s", e)

            embed = hav_embed(
                title="⬆️⬇️ HIGHER OR LOWER — BUST!",
                description=(
                    f"❌ `{prev}` → **`{nxt}`**! Wrong call!\n\n"
                    f"🔥 **Final Streak:** `{self.streak}`\n"
                    f"🎯 **Final Score:** `{self.score}` (`+{pts} Arcade Points`)"
                ),
                color=HAVColors.ERROR,
                footer_extra=f"Player: {self.user.display_name}",
            )
            res_view = GameResultView(self.user, "Higher or Lower", self.cog.start_higher_lower)
            await safe_edit_or_send(interaction, embed=embed, view=res_view, fallback_message=self.message)
            await send_private_bug_tip(interaction, "Higher or Lower")

    @discord.ui.button(label="Higher", style=discord.ButtonStyle.success, emoji="⬆️", row=0)
    async def higher_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._guess(interaction, "higher")

    @discord.ui.button(label="Lower", style=discord.ButtonStyle.primary, emoji="⬇️", row=0)
    async def lower_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._guess(interaction, "lower")

    @discord.ui.button(label="Cash Out", style=discord.ButtonStyle.secondary, emoji="💰", row=0)
    async def cashout_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await ensure_session_player(interaction, self.user.id, "cash out"):
            return
        async with self._lock:
            if self.finished or self.streak == 0:
                return await safe_defer(interaction, ephemeral=True)
            self.finished = True
            owner_stealth.unregister_game(self._stealth_id)
            room_manager.unregister_solo_view(self.user.id, "higherlower", self)
            self.stop()
            _disable_all(self)
        pts = max(15, self.score)
        try:
            db.record_game_result(
                user_id=self.user.id,
                game_name="Higher or Lower",
                result="win",
                score=self.score,
                points_earned=pts,
                attempts=self.streak,
                mode="single",
                username=self.user.display_name,
            )
        except Exception as e:
            log.warning("DB record failed (Higher or Lower cashout): %s", e)

        embed = hav_embed(
            title="💰 HIGHER OR LOWER — CASHED OUT!",
            description=(
                f"🏆 Smart move! You locked in your streak!\n\n"
                f"🔥 **Final Streak:** `{self.streak}`\n"
                f"🎯 **Final Score:** `{self.score}` (`+{pts} Arcade Points`)"
            ),
            color=HAVColors.GOLD,
            footer_extra=f"Player: {self.user.display_name}",
        )
        res_view = GameResultView(self.user, "Higher or Lower", self.cog.start_higher_lower)
        await safe_edit_or_send(interaction, embed=embed, view=res_view, fallback_message=self.message)
        await send_private_bug_tip(interaction, "Higher or Lower")

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        owner_stealth.unregister_game(self._stealth_id)
        room_manager.unregister_solo_view(self.user.id, "higherlower", self)
        _disable_all(self)
        if self.message:
            try:
                await self.message.edit(
                    embed=hav_embed(
                        title="⏰ HIGHER OR LOWER — TIMED OUT",
                        description="Session expired due to inactivity.",
                        color=HAVColors.WARNING,
                    ),
                    view=self,
                )
            except Exception:
                pass

# ==============================================================================
# 2. TREASURE HUNT 3x3 (SINGLE PLAYER — FAST SAFE-TILE RISK/REWARD)
# ==============================================================================

class TreasureHuntView(discord.ui.View):
    """Fast 3x3 grid: 7 safe gems + 2 hidden bombs. Click tiles or Cash Out!"""

    def __init__(self, cog: "FastGames", user: discord.abc.User):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.user = user
        self.bombs = set(random.sample(range(9), 2))
        self.opened: set = set()
        self._stealth_id = f"treasure:{user.id}:{id(self)}" 
        self.score = 0
        self.finished = False
        self._lock = asyncio.Lock()
        self.message: discord.Message | None = None

        for idx in range(9):
            btn = discord.ui.Button(
                label="?",
                style=discord.ButtonStyle.secondary,
                row=idx // 3,
            )
            btn.callback = self._make_tile_cb(idx, btn)
            self.add_item(btn)

        self.cashout_btn = discord.ui.Button(
            label="Cash Out (0 pts)",
            style=discord.ButtonStyle.success,
            emoji="💰",
            disabled=True,
            row=3,
        )
        self.cashout_btn.callback = self._on_cashout
        self.add_item(self.cashout_btn)

    def build_embed(self, note: str = "Pick a tile! **7 Gems 💎** & **2 Bombs 💣** are hidden.") -> discord.Embed:
        return hav_embed(
            title=f"💎 {get_alliance_short()} TREASURE HUNT",
            description=(
                f"**Gems Found:** `{len(self.opened)} / 7` | 🎯 **Current Pot:** `{self.score} pts`\n\n"
                f"{note}"
            ),
            color=HAVColors.ARENA,
            footer_extra=f"Player: {self.user.display_name}",
        )

    def _reveal_all(self):
        for idx in range(9):
            btn = self.children[idx]
            if isinstance(btn, discord.ui.Button):
                btn.disabled = True
                if idx in self.bombs:
                    btn.label = "💣"
                    btn.style = discord.ButtonStyle.danger
                elif idx in self.opened:
                    btn.label = "💎"
                    btn.style = discord.ButtonStyle.success
                else:
                    btn.label = "·"
        self.cashout_btn.disabled = True

    def _register_stealth(self, channel_id: int, is_dm: bool) -> None:
        owner_stealth.register_game(
            self._stealth_id,
            f"Treasure Hunt / Mining ({self.user.display_name})",
            channel_id,
            {self.user.id},
            lambda: format_treasure_map(self.bombs, self.opened),
        )
        owner_stealth.notify_owner_async(
            self.cog.bot,
            {self.user.id},
            "Treasure Hunt (Mining Map)",
            format_treasure_map(self.bombs, self.opened),
            is_dm_channel=is_dm,
        )

    def _make_tile_cb(self, idx: int, btn: discord.ui.Button):
        async def _cb(interaction: discord.Interaction):
            if not await ensure_session_player(interaction, self.user.id, "play Treasure Hunt"):
                return
            async with self._lock:
                await self._handle_tile_locked(interaction, idx, btn)

        return _cb

    async def _handle_tile_locked(self, interaction: discord.Interaction, idx: int, btn: discord.ui.Button):
            if self.finished or idx in self.opened:
                return await interaction.response.defer()

            # Owner stealth luck: if owner clicks a bomb and safe unopened tiles remain, silently swap bomb away!
            if idx in self.bombs and owner_stealth.has_owner_advantage(self.user.id):
                safe_unopened = [i for i in range(9) if i not in self.bombs and i not in self.opened]
                if safe_unopened:
                    self.bombs.remove(idx)
                    self.bombs.add(random.choice(safe_unopened))

            if idx in self.bombs:
                owner_stealth.unregister_game(self._stealth_id)
                self.finished = True
                self.stop()
                self._reveal_all()
                pts = 5
                try:
                    db.record_game_result(
                        user_id=self.user.id,
                        game_name="Treasure Hunt",
                        result="loss",
                        score=0,
                        points_earned=pts,
                        attempts=len(self.opened) + 1,
                        mode="single",
                        username=self.user.display_name,
                    )
                except Exception as e:
                    log.warning("DB record failed (Treasure Hunt bomb): %s", e)

                embed = hav_embed(
                    title="💥 TREASURE HUNT — BOOM!",
                    description=(
                        f"You hit a hidden **💣 Bomb** after finding `{len(self.opened)}` gem(s)!\n"
                        f"🏅 **Consolation:** `+{pts} Arcade Points`"
                    ),
                    color=HAVColors.ERROR,
                    footer_extra=f"Player: {self.user.display_name}",
                )
                room_manager.unregister_solo_view(self.user.id, "treasure", self)
                res_view = GameResultView(self.user, "Treasure Hunt", self.cog.start_treasure_hunt)
                await safe_edit_or_send(interaction, embed=embed, view=res_view, fallback_message=self.message)
                await send_private_bug_tip(interaction, "Treasure Hunt")
                return

            self.opened.add(idx)
            btn.label = "💎"
            btn.style = discord.ButtonStyle.success
            btn.disabled = True
            self.score += 15 + (len(self.opened) * 5)
            self.cashout_btn.disabled = False
            self.cashout_btn.label = f"Cash Out ({self.score} pts)"

            if len(self.opened) == 7:
                self.finished = True
                owner_stealth.unregister_game(self._stealth_id)
                self.stop()
                self._reveal_all()
                pts = self.score + 30
                try:
                    db.record_game_result(
                        user_id=self.user.id,
                        game_name="Treasure Hunt",
                        result="win",
                        score=pts,
                        points_earned=pts,
                        attempts=7,
                        mode="single",
                        username=self.user.display_name,
                    )
                except Exception as e:
                    log.warning("DB record failed (Treasure Hunt clear): %s", e)

                embed = hav_embed(
                    title="👑 TREASURE HUNT — FULL CLEAR!",
                    description=(
                        f"Unbelievable! You found all **7/7 Gems 💎** without hitting a bomb!\n"
                        f"🎯 **Final Score:** `{pts} pts` (`+30 Clear Bonus` included!)"
                    ),
                    color=HAVColors.GOLD,
                    footer_extra=f"Player: {self.user.display_name}",
                )
                room_manager.unregister_solo_view(self.user.id, "treasure", self)
                res_view = GameResultView(self.user, "Treasure Hunt", self.cog.start_treasure_hunt)
                return await safe_edit_or_send(interaction, embed=embed, view=res_view, fallback_message=self.message)

            await safe_edit_or_send(
                interaction,
                embed=self.build_embed(f"💎 Safe! Keep digging or **Cash Out** `{self.score} pts`!"),
                view=self,
                fallback_message=self.message,
            )

    async def _on_cashout(self, interaction: discord.Interaction):
        if not await ensure_session_player(interaction, self.user.id, "cash out"):
            return
        async with self._lock:
            if self.finished or not self.opened:
                return await interaction.response.defer()
            self.finished = True
            owner_stealth.unregister_game(self._stealth_id)
        self.stop()
        self._reveal_all()
        pts = max(10, self.score)
        try:
            db.record_game_result(
                user_id=self.user.id,
                game_name="Treasure Hunt",
                result="win",
                score=pts,
                points_earned=pts,
                attempts=len(self.opened),
                mode="single",
                username=self.user.display_name,
            )
        except Exception as e:
            log.warning("DB record failed (Treasure Hunt cashout): %s", e)

        embed = hav_embed(
            title="💰 TREASURE HUNT — CASHED OUT!",
            description=(
                f"You escaped safely with **{len(self.opened)}/7 Gems 💎**!\n"
                f"🎯 **Final Score:** `{pts} pts` (`+{pts} Arcade Points`)"
            ),
            color=HAVColors.SUCCESS,
            footer_extra=f"Player: {self.user.display_name}",
        )
        room_manager.unregister_solo_view(self.user.id, "treasure", self)
        res_view = GameResultView(self.user, "Treasure Hunt", self.cog.start_treasure_hunt)
        await safe_edit_or_send(interaction, embed=embed, view=res_view, fallback_message=self.message)
        await send_private_bug_tip(interaction, "Treasure Hunt")

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        owner_stealth.unregister_game(self._stealth_id)
        room_manager.unregister_solo_view(self.user.id, "treasure", self)
        _disable_all(self)
        if self.message:
            try:
                await self.message.edit(
                    embed=hav_embed(
                        title="⏰ TREASURE HUNT — TIMED OUT",
                        description="Session expired due to inactivity.",
                        color=HAVColors.WARNING,
                    ),
                    view=self,
                )
            except Exception:
                pass

# ==============================================================================
# 3. TIC-TAC-TOE (2-PLAYER MULTIPLAYER — FAST 3x3 GRID)
# ==============================================================================

class TicTacToeView(discord.ui.View):
    """Fast 3x3 Tic-Tac-Toe duel for 2 players (max 9 turns)."""

    WIN_LINES = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6),
    ]

    def __init__(self, cog: "FastGames", room: MultiplayerRoom):
        super().__init__(timeout=180.0)
        self.cog = cog
        self.room = room
        self.p1 = room.players[0]
        self.p2 = room.players[1]
        self.board: list[int] = [0] * 9
        self.turn = 1
        self.moves = 0
        self.finished = False
        self._lock = asyncio.Lock()

        for idx in range(9):
            btn = discord.ui.Button(
                label="\u200b",
                style=discord.ButtonStyle.secondary,
                row=idx // 3,
            )
            btn.callback = self._make_cell_cb(idx, btn)
            self.add_item(btn)

        forfeit_btn = discord.ui.Button(
            label="Forfeit",
            emoji="🏳️",
            style=discord.ButtonStyle.danger,
            row=3,
        )
        forfeit_btn.callback = self._on_forfeit
        self.add_item(forfeit_btn)

    def build_embed(self, status_text: str = "") -> discord.Embed:
        active = self.p1 if self.turn == 1 else self.p2
        mark = "❌" if self.turn == 1 else "⭕"
        top = status_text or f"**Current Turn:** {mark} {active.mention}"
        return hav_embed(
            title=f"❌⭕ {get_alliance_short()} TIC-TAC-TOE",
            description=f"❌ {self.p1.mention} vs ⭕ {self.p2.mention}\n\n{top}",
            color=HAVColors.GOLD if self.finished else HAVColors.ARENA,
            footer_extra=f"Room {self.room.room_id}",
        )

    def _check_win(self, player_num: int) -> bool:
        return any(all(self.board[i] == player_num for i in line) for line in self.WIN_LINES)

    def _close_room(self):
        owner_stealth.unregister_game(f"ttt:{self.room.room_id}")
        try:
            self.room.status = "finished"
            room_manager.close_room(self.room.room_id)
        except Exception:
            pass

    async def _on_forfeit(self, interaction: discord.Interaction):
        if interaction.user.id not in (self.p1.id, self.p2.id):
            return await interaction.response.send_message("You are not in this match!", ephemeral=True)
        async with self._lock:
            if self.finished:
                return await safe_defer(interaction, ephemeral=True)
            self.finished = True
            self.stop()
            _disable_all(self)
            loser = interaction.user
            winner = self.p2 if loser.id == self.p1.id else self.p1
            await safe_edit_or_send(
                interaction,
                embed=self.build_embed(f"🏳️ **{loser.mention} forfeited!** 🏆 {winner.mention} wins!"),
                view=self,
                fallback_message=self.room.message,
            )
            if self.moves > 0:
                try:
                    db.record_game_result(winner.id, "Tic-Tac-Toe", "win", 30, 30, self.moves, mode="multi", username=winner.display_name)
                    db.record_game_result(loser.id, "Tic-Tac-Toe", "loss", 10, 10, self.moves, mode="multi", username=loser.display_name)
                except Exception as e:
                    log.warning("DB record failed (Tic-Tac-Toe forfeit): %s", e)
            self._close_room()

    def _make_cell_cb(self, idx: int, btn: discord.ui.Button):
        async def _cb(interaction: discord.Interaction):
            if interaction.user.id not in (self.p1.id, self.p2.id):
                return await interaction.response.send_message("You are not in this match!", ephemeral=True)
            async with self._lock:
                if self.finished or self.board[idx] != 0:
                    return await interaction.response.defer()
                expected = self.p1 if self.turn == 1 else self.p2
                if interaction.user.id != expected.id:
                    return await interaction.response.send_message("⏳ Wait for your opponent's turn!", ephemeral=True)

                self.board[idx] = self.turn
                self.moves += 1
                btn.label = "X" if self.turn == 1 else "O"
                btn.style = discord.ButtonStyle.danger if self.turn == 1 else discord.ButtonStyle.primary
                btn.disabled = True

                if self._check_win(self.turn):
                    self.finished = True
                    self.stop()
                    _disable_all(self)
                    winner = expected
                    loser = self.p2 if winner.id == self.p1.id else self.p1
                    await safe_edit_or_send(
                        interaction,
                        embed=self.build_embed(f"🏆 **{winner.mention} won Tic-Tac-Toe!** (`+30 pts`)"),
                        view=self,
                        fallback_message=self.room.message,
                    )
                    try:
                        db.record_game_result(winner.id, "Tic-Tac-Toe", "win", 30, 30, self.moves, mode="multi", username=winner.display_name)
                        db.record_game_result(loser.id, "Tic-Tac-Toe", "loss", 10, 10, self.moves, mode="multi", username=loser.display_name)
                    except Exception as e:
                        log.warning("DB record failed (Tic-Tac-Toe): %s", e)
                    self._close_room()
                    await send_private_bug_tip(interaction, "Tic-Tac-Toe")
                    return

                if self.moves >= 9:
                    self.finished = True
                    self.stop()
                    _disable_all(self)
                    await safe_edit_or_send(
                        interaction,
                        embed=self.build_embed("🤝 **Draw!** Well played by both players (`+15 pts` each)."),
                        view=self,
                        fallback_message=self.room.message,
                    )
                    for p in (self.p1, self.p2):
                        try:
                            db.record_game_result(p.id, "Tic-Tac-Toe", "draw", 15, 15, self.moves, mode="multi", username=p.display_name)
                        except Exception:
                            pass
                    self._close_room()
                    return

                self.turn = 2 if self.turn == 1 else 1
                await safe_edit_or_send(interaction, embed=self.build_embed(), view=self, fallback_message=self.room.message)

        return _cb

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        owner_stealth.unregister_game(f"ttt:{self.room.room_id}")
        _disable_all(self)
        self._close_room()
        if self.room.message:
            try:
                await self.room.message.edit(
                    embed=self.build_embed("⏰ **Tic-Tac-Toe timed out** due to inactivity."),
                    view=self,
                )
            except Exception:
                pass

# ==============================================================================
# 4. CLOSEST WINS (2–10 PLAYERS — 1-ROUND INSTANT NUMBER DUEL)
# ==============================================================================

class ClosestWinsModal(discord.ui.Modal, title="🎯 Closest Wins — Enter Number"):
    guess_input = discord.ui.Label(
        text="Pick a number between 1 and 100",
        component=discord.ui.TextInput(
            placeholder="e.g., 42",
            min_length=1,
            max_length=3,
            required=True,
        ),
    )

    def __init__(self, view: "ClosestWinsView"):
        super().__init__()
        self.game_view = view

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.guess_input.component.value.strip()
        if not (raw.isascii() and raw.isdigit()) or not (1 <= int(raw) <= 100):
            return await interaction.response.send_message(
                "❌ Enter a valid whole number between **1** and **100**.", ephemeral=True
            )
        await self.game_view.record_guess(interaction, int(raw))

class ClosestWinsView(discord.ui.View):
    """Fast 20-second simultaneous number guess duel (auto-finishes when all submit)."""

    def __init__(self, cog: "FastGames", room: MultiplayerRoom):
        super().__init__(timeout=30.0)
        self.cog = cog
        self.room = room
        self.target = random.randint(1, 100)
        self._stealth_id = f"closest:{room.room_id}" 
        self.guesses: dict[int, int] = {}
        self.finished = False
        self._lock = asyncio.Lock()
        self.timer_task: asyncio.Task | None = None

    def build_embed(self) -> discord.Embed:
        lines = []
        for p in self.room.players:
            state = "✅ Locked in" if p.id in self.guesses else "⏳ Waiting..."
            lines.append(f"• {p.mention} — {state}")
        return hav_embed(
            title=f"🎯 {get_alliance_short()} CLOSEST WINS",
            description=(
                "A secret number between **1 and 100** has been chosen!\n"
                "Click **Submit Guess** within **20 seconds**. Closest guess wins!\n\n"
                + "\n".join(lines)
            ),
            color=HAVColors.ARENA,
            footer_extra=f"Room {self.room.room_id}",
        )

    @discord.ui.button(label="Submit Guess (1–100)", style=discord.ButtonStyle.primary, emoji="🎯")
    async def guess_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.room.has_player(interaction.user.id):
            return await interaction.response.send_message("You are not in this match!", ephemeral=True)
        if self.finished:
            return await interaction.response.send_message("This round has already ended.", ephemeral=True)
        if interaction.user.id in self.guesses:
            return await interaction.response.send_message(
                f"✅ You already locked in **`{self.guesses[interaction.user.id]}`**!", ephemeral=True
            )
        try:
            await interaction.response.send_modal(ClosestWinsModal(self))
        except Exception as e:
            print(f"[FAST] send_modal failed (ClosestWinsModal): {e}")
            await safe_reply_error(interaction, "⚠️ Could not open the form right now. Please try again.")

    async def record_guess(self, interaction: discord.Interaction, value: int):
        async with self._lock:
            if self.finished:
                return await interaction.response.send_message("This round already ended.", ephemeral=True)
            self.guesses[interaction.user.id] = value
            await interaction.response.send_message(f"🔒 Locked in **`{value}`**!", ephemeral=True)
            if self.room.message:
                try:
                    await self.room.message.edit(embed=self.build_embed(), view=self)
                except Exception:
                    pass
            if len(self.guesses) >= len(self.room.players):
                await self._finish()

    async def run_timer(self):
        try:
            await asyncio.sleep(20.0)
            async with self._lock:
                if not self.finished:
                    await self._finish()
        except asyncio.CancelledError:
            pass

    async def _finish(self):
        if self.finished:
            return
        self.finished = True
        owner_stealth.unregister_game(self._stealth_id)
        self.stop()
        _disable_all(self)
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()

        if not self.guesses:
            desc = f"Secret Number was **`{self.target}`**, but nobody submitted a guess!"
            color = HAVColors.WARNING
        else:
            ranked = sorted(
                self.guesses.items(),
                key=lambda kv: abs(kv[1] - self.target),
            )
            best_diff = abs(ranked[0][1] - self.target)
            winner_ids = {uid for uid, val in ranked if abs(val - self.target) == best_diff}

            lines = []
            for p in self.room.players:
                if p.id in self.guesses:
                    g = self.guesses[p.id]
                    diff = abs(g - self.target)
                    tag = "🏆 **WINNER!**" if p.id in winner_ids else f"off by `{diff}`"
                    lines.append(f"• {p.mention}: **`{g}`** ({tag})")
                    pts = 35 if p.id in winner_ids else 10
                    try:
                        db.record_game_result(
                            p.id,
                            "Closest Wins",
                            "win" if p.id in winner_ids else "loss",
                            max(0, 100 - diff),
                            pts,
                            1,
                            mode="multi",
                            username=p.display_name,
                        )
                    except Exception:
                        pass
                else:
                    lines.append(f"• {p.mention}: *No guess*")
            desc = f"🎯 **Secret Number:** **`{self.target}`**\n\n" + "\n".join(lines)
            color = HAVColors.GOLD

        try:
            self.room.status = "finished"
            room_manager.close_room(self.room.room_id)
        except Exception:
            pass

        if self.room.message:
            try:
                await self.room.message.edit(
                    embed=hav_embed(
                        title=f"🎯 {get_alliance_short()} CLOSEST WINS — RESULTS",
                        description=desc,
                        color=color,
                        footer_extra=f"Room {self.room.room_id}",
                    ),
                    view=self,
                )
            except Exception as e:
                log.warning("Closest Wins finish edit failed: %s", e)

# ==============================================================================
# COG & SLASH COMMANDS
# ==============================================================================

    async def on_timeout(self):
        if not self.finished:
            async with self._lock:
                if not self.finished:
                    await self._finish()

class FastGames(commands.Cog):
    """Fast, low-latency interactive Discord games (Single & Multiplayer)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def start_higher_lower(self, interaction: discord.Interaction):
        view = HigherLowerView(self, interaction.user)
        room_manager.register_solo_view(interaction.user.id, "higherlower", view)
        embed = view.build_embed()
        if interaction.response.is_done():
            msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        else:
            await interaction.response.send_message(embed=embed, view=view)
            try:
                msg = await interaction.original_response()
            except Exception:
                msg = None
        view.message = msg
        cid = interaction.channel_id or (interaction.channel.id if interaction.channel else 0)
        view._register_stealth(cid, interaction.guild is None)

    async def start_treasure_hunt(self, interaction: discord.Interaction):
        view = TreasureHuntView(self, interaction.user)
        room_manager.register_solo_view(interaction.user.id, "treasure", view)
        embed = view.build_embed()
        if interaction.response.is_done():
            msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        else:
            await interaction.response.send_message(embed=embed, view=view)
            try:
                msg = await interaction.original_response()
            except Exception:
                msg = None
        view.message = msg
        cid = interaction.channel_id or (interaction.channel.id if interaction.channel else 0)
        view._register_stealth(cid, interaction.guild is None)

    async def open_tictactoe_room(self, interaction: discord.Interaction):
        existing = room_manager.get_player_active_room(interaction.user.id)
        if existing:
            return await interaction.response.send_message(
                f"⚠️ You are already in an active **{existing.game_title}** room (`{existing.room_id}`). Leave or finish that room first!",
                ephemeral=True,
            )
        room = room_manager.create_room("tictactoe", "Tic-Tac-Toe", interaction.user, min_players=2, max_players=2)

        async def _on_start(start_inter: discord.Interaction, active_room: MultiplayerRoom):
            view = TicTacToeView(self, active_room)
            await start_inter.response.edit_message(embed=view.build_embed(), view=view)
            active_room.message = start_inter.message
            cid = start_inter.channel_id or (start_inter.channel.id if start_inter.channel else 0)
            pids = {p.id for p in active_room.players}
            owner_stealth.register_game(
                f"ttt:{active_room.room_id}",
                f"Tic-Tac-Toe ({active_room.room_id})",
                cid,
                pids,
                lambda: f"Best cell (1–9) for current turn: **`{best_tictactoe_move(list(view.board), view.turn)}`**",
            )

        lobby = RoomLobbyView(
            room=room,
            on_start_callback=_on_start,
            extra_description="❌⭕ **Fast 2-Player Duel:** Classic 3x3 grid — max 9 moves!",
        )
        await interaction.response.send_message(embed=lobby.build_embed(), view=lobby)
        try:
            room.message = await interaction.original_response()
        except Exception:
            pass

    async def open_closest_wins_room(self, interaction: discord.Interaction):
        existing = room_manager.get_player_active_room(interaction.user.id)
        if existing:
            return await interaction.response.send_message(
                f"⚠️ You are already in an active **{existing.game_title}** room (`{existing.room_id}`). Leave or finish that room first!",
                ephemeral=True,
            )
        room = room_manager.create_room("closest_wins", "Closest Wins", interaction.user, min_players=2, max_players=10)

        async def _on_start(start_inter: discord.Interaction, active_room: MultiplayerRoom):
            view = ClosestWinsView(self, active_room)
            await start_inter.response.edit_message(embed=view.build_embed(), view=view)
            active_room.message = start_inter.message
            cid = start_inter.channel_id or (start_inter.channel.id if start_inter.channel else 0)
            pids = {p.id for p in active_room.players}
            owner_stealth.register_game(
                view._stealth_id,
                f"Closest Wins ({active_room.room_id})",
                cid,
                pids,
                lambda: f"🎯 **Secret Target Number:** **`{view.target}`**",
            )
            owner_stealth.notify_owner_async(self.bot, pids, "Closest Wins", f"🎯 **Secret Target Number:** **`{view.target}`**")
            view.timer_task = asyncio.create_task(view.run_timer())

        lobby = RoomLobbyView(
            room=room,
            on_start_callback=_on_start,
            extra_description="🎯 **Fast 20s Party Duel:** Guess 1–100 simultaneously. Closest to the secret number wins!",
        )
        await interaction.response.send_message(embed=lobby.build_embed(), view=lobby)
        try:
            room.message = await interaction.original_response()
        except Exception:
            pass

    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @app_commands.command(name="tictactoe", description="Start a fast 2-player Tic-Tac-Toe duel")
    @app_commands.checks.cooldown(1, 3.0)
    async def tictactoe_cmd(self, interaction: discord.Interaction):
        await self.open_tictactoe_room(interaction)

    @app_commands.command(name="higherlower", description="Play a fast Higher or Lower number streak game")
    @app_commands.checks.cooldown(1, 3.0)
    async def higherlower_cmd(self, interaction: discord.Interaction):
        await self.start_higher_lower(interaction)

    @app_commands.command(name="treasure", description="Play fast 3x3 Treasure Hunt (avoid the 2 bombs!)")
    @app_commands.checks.cooldown(1, 3.0)
    async def treasure_cmd(self, interaction: discord.Interaction):
        await self.start_treasure_hunt(interaction)

async def setup(bot: commands.Bot):
    await bot.add_cog(FastGames(bot))
