# cogs/connect4.py
import discord
from discord import app_commands
from discord.ext import commands
from typing import List, Optional

from core.config import ROFColors
from core.database import db
from core.rooms import MultiplayerRoom, RoomLobbyView, room_manager
from core.ui import rof_embed

EMPTY_CELL = "⚫"
P1_TOKEN = "🔴"
P2_TOKEN = "🟡"
COL_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]


class Connect4View(discord.ui.View):
    def __init__(self, cog: "Connect4", room: MultiplayerRoom):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.room = room
        self.p1 = room.players[0]
        self.p2 = room.players[1]
        self.board: List[List[int]] = [[0] * 7 for _ in range(6)]
        self.turn = 1  # 1 = p1, 2 = p2
        self.moves = 0
        self.finished = False

        for c in range(7):
            btn = discord.ui.Button(
                label=str(c + 1),
                style=discord.ButtonStyle.secondary,
                row=0 if c < 4 else 1,
            )
            btn.callback = self._make_col_cb(c)
            self.add_item(btn)

    def _render_board(self) -> str:
        lines = [" ".join(COL_EMOJIS)]
        for r in range(6):
            row_tokens = []
            for c in range(7):
                v = self.board[r][c]
                row_tokens.append(P1_TOKEN if v == 1 else (P2_TOKEN if v == 2 else EMPTY_CELL))
            lines.append(" ".join(row_tokens))
        return "\n".join(lines)

    def _check_winner(self, token: int) -> bool:
        for r in range(6):
            for c in range(4):
                if all(self.board[r][c + i] == token for i in range(4)):
                    return True
        for r in range(3):
            for c in range(7):
                if all(self.board[r + i][c] == token for i in range(4)):
                    return True
        for r in range(3):
            for c in range(4):
                if all(self.board[r + i][c + i] == token for i in range(4)):
                    return True
                if all(self.board[r + 3 - i][c + i] == token for i in range(4)):
                    return True
        return False

    def build_embed(self, status_text: str = "") -> discord.Embed:
        active_p = self.p1 if self.turn == 1 else self.p2
        active_tok = P1_TOKEN if self.turn == 1 else P2_TOKEN
        top_line = status_text or f"**Current Turn:** {active_tok} {active_p.mention}"
        desc = (
            f"{P1_TOKEN} {self.p1.mention} vs {P2_TOKEN} {self.p2.mention}\n"
            f"{top_line}\n\n"
            f"{self._render_board()}"
        )
        return rof_embed(
            title="🔴 ROF CONNECT 4",
            description=desc,
            color=ROFColors.ARENA if not self.finished else ROFColors.GOLD,
            footer_extra=f"Room {self.room.room_id}",
        )

    def _make_col_cb(self, col: int):
        async def _cb(interaction: discord.Interaction):
            expected_user = self.p1 if self.turn == 1 else self.p2
            if interaction.user.id not in (self.p1.id, self.p2.id):
                return await interaction.response.send_message("You are not in this match!", ephemeral=True)
            if interaction.user.id != expected_user.id:
                return await interaction.response.send_message("⏳ Wait for your opponent's turn!", ephemeral=True)

            target_row = None
            for r in range(5, -1, -1):
                if self.board[r][col] == 0:
                    target_row = r
                    break
            if target_row is None:
                return await interaction.response.send_message("⚠️ That column is full!", ephemeral=True)

            self.board[target_row][col] = self.turn
            self.moves += 1
            if target_row == 0:
                self.children[col].disabled = True

            if self._check_winner(self.turn):
                self.finished = True
                self.stop()
                self.room.status = "finished"
                room_manager.close_room(self.room.room_id)
                for child in self.children:
                    child.disabled = True
                winner = expected_user
                loser = self.p2 if winner.id == self.p1.id else self.p1
                db.record_game_result(winner.id, "Connect 4", "win", 40, 40, self.moves, mode="multi", username=winner.display_name)
                db.record_game_result(loser.id, "Connect 4", "loss", 10, 10, self.moves, mode="multi", username=loser.display_name)
                await interaction.response.edit_message(
                    embed=self.build_embed(f"🏆 **{winner.mention} connected 4 and WON!**"),
                    view=self,
                )
            elif self.moves >= 42:
                self.finished = True
                self.stop()
                self.room.status = "finished"
                room_manager.close_room(self.room.room_id)
                for child in self.children:
                    child.disabled = True
                for p in (self.p1, self.p2):
                    db.record_game_result(p.id, "Connect 4", "draw", 20, 20, self.moves, mode="multi", username=p.display_name)
                await interaction.response.edit_message(
                    embed=self.build_embed("🤝 **Draw Game!** The board is full."),
                    view=self,
                )
            else:
                self.turn = 2 if self.turn == 1 else 1
                await interaction.response.edit_message(embed=self.build_embed(), view=self)

        return _cb


class Connect4(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def open_connect4_room(self, interaction: discord.Interaction):
        existing = room_manager.get_player_active_room(interaction.user.id, "connect4")
        if existing:
            return await interaction.response.send_message(
                f"⚠️ You are already in an active Connect 4 room (`{existing.room_id}`).",
                ephemeral=True,
            )
        room = room_manager.create_room("connect4", "Connect 4", interaction.user, min_players=2, max_players=2)

        async def _on_start(start_inter: discord.Interaction, active_room: MultiplayerRoom):
            view = Connect4View(self, active_room)
            await start_inter.response.edit_message(embed=view.build_embed(), view=view)
            active_room.message = start_inter.message

        lobby = RoomLobbyView(room=room, on_start_callback=_on_start, extra_description="🔴🟡 **2-Player Strategy Duel:** Drop tokens to connect 4 in a row!")
        await interaction.response.send_message(embed=lobby.build_embed(), view=lobby)
        try:
            room.message = await interaction.original_response()
        except Exception:
            pass

    @app_commands.command(name="connect4", description="Start a 2-player Connect 4 duel")
    async def connect4(self, interaction: discord.Interaction):
        await self.open_connect4_room(interaction)


async def setup(bot):
    await bot.add_cog(Connect4(bot))
