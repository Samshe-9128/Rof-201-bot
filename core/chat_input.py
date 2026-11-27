# core/chat_input.py
"""
Central chat-message input router for HAV Discord Bot games.

Lets players simply type their guesses/answers as normal Discord messages
(in both server channels and DMs) — just like popular Discord game bots —
instead of clicking buttons to open modal popups on every turn.
"""
import time
import traceback
from dataclasses import dataclass, field
from collections.abc import Awaitable, Callable

import discord

from core.logger import log

# Handler signature: async def handler(message: discord.Message) -> bool
# Return True if the message was consumed by the game session.
MessageHandler = Callable[[discord.Message], Awaitable[bool]]

@dataclass
class ChatInputSession:
    session_id: str
    channel_id: int
    game_name: str
    handler: MessageHandler
    allowed_user_ids: set[int] | None = None  # None = any non-bot user in channel
    expires_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    on_replace: Callable[[], None] | None = None

    def matches(self, message: discord.Message) -> bool:
        if message.channel.id != self.channel_id:
            return False
        if self.expires_at and time.time() > self.expires_at:
            return False
        if self.allowed_user_ids is not None and message.author.id not in self.allowed_user_ids:
            return False
        return True

class ChatInputManager:
    """
    Registry of active chat-based game input sessions.

    Supports both:
    - Solo sessions keyed per (channel_id, user_id) so multiple users can play
      in the same channel simultaneously without colliding.
    - Channel/multiplayer sessions keyed by room/session_id with a set of allowed players.
    """

    def __init__(self):
        self._sessions: dict[str, ChatInputSession] = {}
        self._consumed_messages: dict[int, float] = {}

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [
            sid for sid, sess in self._sessions.items()
            if sess.expires_at and now > sess.expires_at
        ]
        for sid in expired:
            self._sessions.pop(sid, None)

        if len(self._consumed_messages) > 200:
            cutoff = now - 60.0
            for mid, ts in list(self._consumed_messages.items()):
                if ts < cutoff:
                    self._consumed_messages.pop(mid, None)

    def register(
        self,
        session_id: str,
        channel_id: int,
        game_name: str,
        handler: MessageHandler,
        allowed_user_ids: set[int] | None = None,
        timeout_seconds: float = 300.0,
        on_replace: Callable[[], None] | None = None,
    ) -> ChatInputSession:
        """
        Register an active chat-input session.
        If this is a solo session (single user in a channel), any previous solo session
        for the same (channel_id, user_id) is cleanly replaced so inputs never collide.
        """
        self._purge_expired()

        # Replace any existing solo session for participating user(s) in the same channel
        # so solo games (e.g. Wordle) never collide with a newly started solo OR multiplayer chat game.
        if allowed_user_ids:
            for old_id, old_sess in list(self._sessions.items()):
                if (
                    old_id != session_id
                    and old_sess.channel_id == channel_id
                    and old_sess.allowed_user_ids is not None
                    and len(old_sess.allowed_user_ids) == 1
                    and next(iter(old_sess.allowed_user_ids)) in allowed_user_ids
                ):
                    self._sessions.pop(old_id, None)
                    if old_sess.on_replace:
                        try:
                            old_sess.on_replace()
                        except Exception:
                            pass

        old_same = self._sessions.pop(session_id, None)
        if old_same and old_same.on_replace:
            try:
                old_same.on_replace()
            except Exception:
                pass

        sess = ChatInputSession(
            session_id=session_id,
            channel_id=channel_id,
            game_name=game_name,
            handler=handler,
            allowed_user_ids=set(allowed_user_ids) if allowed_user_ids is not None else None,
            expires_at=(time.time() + timeout_seconds) if timeout_seconds else 0.0,
            on_replace=on_replace,
        )
        self._sessions[session_id] = sess
        return sess

    def unregister(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def mark_consumed(self, message_id: int) -> None:
        self._consumed_messages[message_id] = time.time()

    def was_consumed(self, message_id: int) -> bool:
        return message_id in self._consumed_messages

    def has_active_session(self, channel_id: int, user_id: int) -> bool:
        """Return True if the user currently has an active chat-input game in this channel."""
        self._purge_expired()
        for sess in self._sessions.values():
            if sess.channel_id != channel_id:
                continue
            if sess.allowed_user_ids is None or user_id in sess.allowed_user_ids:
                return True
        return False

    def get_active_sessions(self, channel_id: int, user_id: int):
        """Return matching sessions ordered newest-first."""
        self._purge_expired()
        matched = [
            sess for sess in self._sessions.values()
            if sess.channel_id == channel_id
            and (sess.allowed_user_ids is None or user_id in sess.allowed_user_ids)
        ]
        matched.sort(key=lambda s: s.created_at, reverse=True)
        return matched

    async def dispatch_message(self, message: discord.Message) -> bool:
        """
        Route an incoming Discord message to any matching active game session.
        Returns True if a game session consumed the message.
        """
        if message.author.bot:
            return False
        content = (message.content or "").strip()
        if not content or content.startswith(("/", "!")):
            return False

        sessions = self.get_active_sessions(message.channel.id, message.author.id)
        if not sessions:
            return False

        # In DMs, mark early so concurrent DMHandler listeners never hijack an active game input.
        if message.guild is None:
            self.mark_consumed(message.id)

        for sess in sessions:
            if not sess.matches(message):
                continue
            try:
                consumed = await sess.handler(message)
                if consumed:
                    self.mark_consumed(message.id)
                    return True
            except Exception as e:
                log.error(
                    "ChatInput session '%s' (%s) error: %s: %s",
                    sess.session_id,
                    sess.game_name,
                    type(e).__name__,
                    e,
                )
                traceback.print_exc()
        return False

chat_input_manager = ChatInputManager()

async def safe_add_reaction(message: discord.Message, emoji: str) -> None:
    """Best-effort reaction helper that never raises if permissions are missing."""
    try:
        await message.add_reaction(emoji)
    except Exception:
        pass

async def safe_delete_message(message: discord.Message) -> None:
    """Best-effort message delete (only in guild channels where bot has Manage Messages)."""
    if message.guild is None:
        return
    try:
        await message.delete()
    except Exception:
        pass
