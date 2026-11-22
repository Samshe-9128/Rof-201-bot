# core/rooms.py
import asyncio
import random
import string
import time
import discord
from typing import Callable, Dict, List, Optional
from core.config import ROFColors
from core.ui import get_alliance_short, rof_embed


class MultiplayerRoom:
    """Represents a single multiplayer game session with atomic lock and full player lifecycle."""

    def __init__(
        self,
        room_id: str,
        game_key: str,
        game_title: str,
        host: discord.abc.User,
        min_players: int = 2,
        max_players: int = 6,
        config: Optional[ dict ] = None,
    ):
        self.room_id = room_id
        self.game_key = game_key
        self.game_title = game_title
        self.host = host
        self.min_players = min_players
        self.max_players = max_players
        self.config = config or {}
        self.players: List[discord.abc.User] = [host]
        self.status = "waiting"  # 'waiting', 'active', 'finished', 'closed'
        self.created_at = time.time()
        self.lock = asyncio.Lock()
        self.message: Optional[discord.Message] = None

    def has_player(self, user_id: int) -> bool:
        return any(p.id == user_id for p in self.players)


class RoomManager:
    """Central registry preventing duplicate session participation and managing active rooms."""

    def __init__(self):
        self.rooms: Dict[str, MultiplayerRoom] = {}
        self.single_player_sessions: Dict[str, set] = {}  # game_key -> set of user_ids
        self.active_solo_views: Dict[tuple, discord.ui.View] = {}  # (user_id, game_key) -> active View

    def generate_room_id(self) -> str:
        raw_tag = "".join(ch for ch in get_alliance_short().upper() if ch.isalnum())[:6] or "ALLIANCE"
        while True:
            rid = f"{raw_tag}-" + "".join(random.choices(string.digits, k=4))
            if rid not in self.rooms:
                return rid

    def purge_stale_rooms(self) -> None:
        now = time.time()
        for rid, room in list(self.rooms.items()):
            age = now - room.created_at
            if (
                room.status in ("finished", "closed")
                or (room.status == "waiting" and age > 300)
                or (room.status == "active" and age > 1800)
            ):
                room.status = "closed"
                self.rooms.pop(rid, None)

    def get_player_active_room(self, user_id: int, game_key: Optional[str] = None) -> Optional[MultiplayerRoom]:
        self.purge_stale_rooms()
        for room in list(self.rooms.values()):
            if room.status in ("waiting", "active"):
                if game_key is None or room.game_key == game_key:
                    if room.has_player(user_id):
                        return room
        return None

    def start_single_session(self, user_id: int, game_key: str) -> bool:
        active = self.single_player_sessions.setdefault(game_key, set())
        if user_id in active:
            return False
        active.add(user_id)
        return True

    def end_single_session(self, user_id: int, game_key: str):
        if game_key in self.single_player_sessions:
            self.single_player_sessions[game_key].discard(user_id)

    def register_solo_view(self, user_id: int, game_key: str, view: discord.ui.View) -> Optional[discord.ui.View]:
        """Register an active solo game view, cleanly cancelling any previous active session of the same game."""
        key = (user_id, game_key)
        old = self.active_solo_views.get(key)
        if old is not None and old is not view:
            try:
                if hasattr(old, "finished"):
                    old.finished = True
                if hasattr(old, "_ended"):
                    old._ended = True
                old.stop()
                for child in getattr(old, "children", []):
                    try:
                        child.disabled = True
                    except Exception:
                        pass
                stealth_id = getattr(old, "_stealth_id", None)
                if stealth_id:
                    from core.owner_stealth import owner_stealth
                    owner_stealth.unregister_game(stealth_id)
            except Exception:
                pass
        self.active_solo_views[key] = view
        return old

    def unregister_solo_view(self, user_id: int, game_key: str, view: Optional[discord.ui.View] = None) -> None:
        key = (user_id, game_key)
        cur = self.active_solo_views.get(key)
        if cur is not None and (view is None or cur is view):
            self.active_solo_views.pop(key, None)

    async def remove_player_from_all_rooms(self, user_id: int) -> None:
        """Cleanly evict a user who left the Discord server from all waiting/active rooms."""
        self.purge_stale_rooms()
        for rid, room in list(self.rooms.items()):
            if not room.has_player(user_id):
                continue
            async with room.lock:
                if not room.has_player(user_id):
                    continue
                room.players = [p for p in room.players if p.id != user_id]
                if not room.players or (room.status == "active" and len(room.players) < room.min_players):
                    room.status = "closed"
                    self.rooms.pop(rid, None)
                    if room.message:
                        try:
                            embed = rof_embed(
                                title=f"🏟️ {get_alliance_short()} GAME ROOM — {room.game_title.upper()}",
                                description=f"🔒 Room `{room.room_id}` closed because a player left the server.",
                                color=ROFColors.ERROR,
                            )
                            await room.message.edit(embed=embed, view=None)
                        except Exception:
                            pass
                else:
                    if room.host.id == user_id:
                        room.host = room.players[0]

    def create_room(
        self,
        game_key: str,
        game_title: str,
        host: discord.abc.User,
        min_players: int = 2,
        max_players: int = 6,
        config: Optional[dict] = None,
    ) -> MultiplayerRoom:
        rid = self.generate_room_id()
        room = MultiplayerRoom(
            room_id=rid,
            game_key=game_key,
            game_title=game_title,
            host=host,
            min_players=min_players,
            max_players=max_players,
            config=config,
        )
        self.rooms[rid] = room
        return room

    def close_room(self, room_id: str):
        room = self.rooms.pop(room_id, None)
        if room:
            room.status = "closed"

    def list_active_rooms(self) -> List[MultiplayerRoom]:
        self.purge_stale_rooms()
        return list(self.rooms.values())


room_manager = RoomManager()


class RoomLobbyView(discord.ui.View):
    """Consistent Part 3.1 Multiplayer Room Invitation & Lobby UI."""

    def __init__(
        self,
        room: MultiplayerRoom,
        on_start_callback: Callable,
        extra_description: str = "",
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.room = room
        self.on_start_callback = on_start_callback
        self.extra_description = extra_description

    def build_embed(self) -> discord.Embed:
        status_label = {
            "waiting": "🟢 Waiting for players",
            "active": "🔥 Match in progress",
            "finished": "🏁 Match completed",
            "closed": "🔒 Room closed",
        }.get(self.room.status, self.room.status)

        desc = (
            f"**Game:** {self.room.game_title}\n"
            f"**Room ID:** `{self.room.room_id}`\n"
            f"**Host:** {self.room.host.mention}\n"
            f"**Players:** `{len(self.room.players)} / {self.room.max_players}` (Min: {self.room.min_players})\n"
            f"**Status:** {status_label}\n"
        )
        if self.extra_description:
            desc += f"\n{self.extra_description}\n"

        player_lines = "\n".join(
            f"`{i}.` {p.mention}{' 👑 *(Host)*' if p.id == self.room.host.id else ''}"
            for i, p in enumerate(self.room.players, 1)
        )
        embed = rof_embed(
            title=f"🏟️ {get_alliance_short()} GAME ROOM — {self.room.game_title.upper()}",
            description=desc,
            color=ROFColors.ARENA if self.room.status == "waiting" else ROFColors.PRIMARY,
            footer_extra=f"Room {self.room.room_id}",
        )
        embed.add_field(
            name=f"👥 Joined Players ({len(self.room.players)}/{self.room.max_players})",
            value=player_lines or "*No players in room.*",
            inline=False,
        )
        return embed

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.primary, emoji="➕", row=0)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self.room.lock:
            if self.room.status != "waiting":
                return await interaction.response.send_message(
                    "⚠️ Cannot join: this game has already started or closed.", ephemeral=True
                )
            if self.room.has_player(interaction.user.id):
                return await interaction.response.send_message(
                    "ℹ️ You have already joined this room!", ephemeral=True
                )
            if len(self.room.players) >= self.room.max_players:
                return await interaction.response.send_message(
                    f"⚠️ This room is full (`{self.room.max_players}/{self.room.max_players}` players).",
                    ephemeral=True,
                )
            existing = room_manager.get_player_active_room(interaction.user.id)
            if existing and existing.room_id != self.room.room_id:
                return await interaction.response.send_message(
                    f"⚠️ You are already in an active **{existing.game_title}** room (`{existing.room_id}`). Leave or finish that room first!",
                    ephemeral=True,
                )

            self.room.players.append(interaction.user)
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
            await interaction.followup.send(
                f"✅ You joined **{self.room.game_title}** (Room `{self.room.room_id}`)!",
                ephemeral=True,
            )

    @discord.ui.button(label="Leave Game", style=discord.ButtonStyle.secondary, emoji="🚪", row=0)
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self.room.lock:
            if self.room.status != "waiting":
                return await interaction.response.send_message(
                    "⚠️ The match has already started.", ephemeral=True
                )
            if not self.room.has_player(interaction.user.id):
                return await interaction.response.send_message(
                    "ℹ️ You are not in this room.", ephemeral=True
                )

            self.room.players = [p for p in self.room.players if p.id != interaction.user.id]

            # Handle host departure
            if not self.room.players:
                self.room.status = "closed"
                room_manager.close_room(self.room.room_id)
                self.stop()
                for child in self.children:
                    child.disabled = True
                embed = rof_embed(
                    title=f"🏟️ {get_alliance_short()} GAME ROOM — {self.room.game_title.upper()}",
                    description=f"🔒 Room `{self.room.room_id}` closed because all players left.",
                    color=ROFColors.ERROR,
                )
                return await interaction.response.edit_message(embed=embed, view=self)

            host_note = ""
            if interaction.user.id == self.room.host.id:
                self.room.host = self.room.players[0]
                host_note = f" 👑 {self.room.host.mention} is now the room host."

            await interaction.response.edit_message(embed=self.build_embed(), view=self)
            await interaction.followup.send(
                f"🚪 You left room `{self.room.room_id}`.{host_note}", ephemeral=True
            )

    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.success, emoji="▶️", row=0)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self.room.lock:
            if interaction.user.id != self.room.host.id:
                return await interaction.response.send_message(
                    f"🔒 Only the room host ({self.room.host.mention}) can start the game.",
                    ephemeral=True,
                )
            if self.room.status != "waiting":
                return await interaction.response.send_message(
                    "⚠️ This room has already started.", ephemeral=True
                )
            if len(self.room.players) < self.room.min_players:
                return await interaction.response.send_message(
                    f"⚠️ Need at least **{self.room.min_players} players** to start (currently `{len(self.room.players)}`).",
                    ephemeral=True,
                )

            self.room.status = "active"
            self.stop()
            for child in self.children:
                child.disabled = True

        try:
            await self.on_start_callback(interaction, self.room)
        except Exception:
            self.room.status = "closed"
            room_manager.close_room(self.room.room_id)
            raise

    @discord.ui.button(label="Close Room", style=discord.ButtonStyle.danger, emoji="✖️", row=0)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self.room.lock:
            if interaction.user.id != self.room.host.id:
                return await interaction.response.send_message(
                    f"🔒 Only the room host ({self.room.host.mention}) can close the room.",
                    ephemeral=True,
                )
            self.room.status = "closed"
            room_manager.close_room(self.room.room_id)
            self.stop()
            for child in self.children:
                child.disabled = True
            embed = rof_embed(
                title=f"🏟️ {get_alliance_short()} GAME ROOM — {self.room.game_title.upper()}",
                description=f"🔒 Room `{self.room.room_id}` was closed by the host.",
                color=ROFColors.ERROR,
            )
            await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        async with self.room.lock:
            if self.room.status != "waiting":
                return
            self.room.status = "closed"
            room_manager.close_room(self.room.room_id)
            for child in self.children:
                child.disabled = True
        if self.room.message:
            try:
                embed = rof_embed(
                    title=f"🏟️ {get_alliance_short()} GAME ROOM — {self.room.game_title.upper()}",
                    description=f"⌛ Room `{self.room.room_id}` expired due to inactivity.",
                    color=ROFColors.WARNING,
                )
                await self.room.message.edit(embed=embed, view=self)
            except Exception:
                pass
