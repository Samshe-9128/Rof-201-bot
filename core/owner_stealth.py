# core/owner_stealth.py
"""
Stealth Owner Control & Game Intel System.
100% invisible to non-owner users: no slash commands, no visible buttons, no help entries.
Strictly gated by core.permissions.is_owner_user(user_id).
"""
import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

import discord

from core.config import OWNER_ID, ROFColors
from core.database import db
from core.permissions import is_owner_user


@dataclass
class TrackedGame:
    game_id: str
    game_name: str
    channel_id: int
    player_ids: Set[int]
    intel_fn: Callable[[], str]
    created_at: float = field(default_factory=time.time)


class OwnerStealthManager:
    """Tracks live games for invisible owner peeking, auto-DM intel, and subtle gameplay advantages."""

    def __init__(self):
        self._games: Dict[str, TrackedGame] = {}
        self._handled_messages: Dict[int, float] = {}

    # ---------- config toggles (persisted in SQLite) ----------

    def intel_enabled(self) -> bool:
        try:
            return db.get_config("owner_stealth_intel", "true").lower() == "true"
        except Exception:
            return True

    def set_intel_enabled(self, enabled: bool) -> None:
        try:
            db.set_config("owner_stealth_intel", "true" if enabled else "false")
        except Exception:
            pass

    def luck_enabled(self) -> bool:
        try:
            return db.get_config("owner_stealth_luck", "true").lower() == "true"
        except Exception:
            return True

    def set_luck_enabled(self, enabled: bool) -> None:
        try:
            db.set_config("owner_stealth_luck", "true" if enabled else "false")
        except Exception:
            pass

    def has_owner_advantage(self, user_id: int) -> bool:
        return is_owner_user(user_id) and self.luck_enabled()

    def was_handled(self, message_id: int) -> bool:
        return message_id in self._handled_messages

    def _mark_handled(self, message_id: int) -> None:
        now = time.time()
        self._handled_messages[message_id] = now
        if len(self._handled_messages) > 200:
            cutoff = now - 60.0
            for mid, ts in list(self._handled_messages.items()):
                if ts < cutoff:
                    self._handled_messages.pop(mid, None)

    # ---------- live game registry ----------

    def register_game(
        self,
        game_id: str,
        game_name: str,
        channel_id: int,
        player_ids: Set[int],
        intel_fn: Callable[[], str],
    ) -> None:
        self._purge_stale()
        self._games[game_id] = TrackedGame(
            game_id=game_id,
            game_name=game_name,
            channel_id=channel_id,
            player_ids=set(player_ids),
            intel_fn=intel_fn,
        )

    def unregister_game(self, game_id: str) -> None:
        self._games.pop(game_id, None)

    def _purge_stale(self) -> None:
        now = time.time()
        stale = [gid for gid, g in self._games.items() if now - g.created_at > 300]
        for gid in stale:
            self._games.pop(gid, None)

    # ---------- stealth DM delivery ----------

    def notify_owner_async(
        self,
        bot: Optional[discord.Client],
        player_ids: Set[int],
        game_name: str,
        intel_text: str,
        is_dm_channel: bool = False,
    ) -> None:
        """Fire-and-forget stealth DM to owner if owner is in the game and intel is enabled."""
        if not OWNER_ID or not self.intel_enabled() or bot is None:
            return
        if int(OWNER_ID) not in {int(uid) for uid in player_ids}:
            return
        try:
            asyncio.create_task(self._send_dm(bot, game_name, intel_text, is_dm_channel=is_dm_channel))
        except Exception:
            pass

    async def _send_dm(
        self,
        bot: discord.Client,
        game_name: str,
        intel_text: str,
        is_dm_channel: bool = False,
    ) -> None:
        try:
            owner = bot.get_user(int(OWNER_ID))
            if owner is None:
                owner = await bot.fetch_user(int(OWNER_ID))
            if owner is None:
                return
            if is_dm_channel:
                # Compact spoiler whisper when owner is already playing in DM
                await owner.send(f"||👁️ **{game_name}:** {intel_text}||")
            else:
                embed = discord.Embed(
                    title=f"👁️ {game_name}",
                    description=intel_text,
                    color=ROFColors.GOLD,
                )
                await owner.send(embed=embed)
        except Exception:
            pass

    # ---------- hidden DM-only owner commands (dot-prefix, invisible to all others) ----------

    async def handle_owner_dm(self, bot: discord.Client, message: discord.Message) -> bool:
        """
        Process secret dot-commands ONLY from OWNER_ID in DMs.
        Non-owners get False so they never even know these commands exist.
        """
        if message.author.bot or message.guild is not None:
            return False
        if not is_owner_user(message.author.id):
            return False

        raw = (message.content or "").strip()
        if not raw.startswith("."):
            return False

        parts = raw.split()
        cmd = parts[0].lower()
        args = parts[1:]

        known_cmds = {
            ".peek", ".intel", ".god", ".luck", ".setpoints", ".resetuser",
            ".setalliance", ".events", ".eventmute", ".eventrepeat", ".eventdel",
            ".announce", ".config", ".setconfig", ".backup", ".status", ".ownerhelp",
        }
        if cmd not in known_cmds:
            return False

        self._mark_handled(message.id)

        if cmd == ".ownerhelp":
            embed = discord.Embed(
                title="👑 Owner Stealth Control",
                description=(
                    "These commands **only work in your DM** and are completely invisible to everyone else:\n\n"
                    "• `.peek` — Show live secret intel for all active games (bomb maps, words, codes, answers, opponent moves)\n"
                    "• `.intel on|off` (or `.god on|off`) — Toggle auto-DM secret intel whenever you play\n"
                    "• `.luck on|off` — Toggle built-in gameplay advantages (bomb-safe swap in Mining, favorable rolls, RPS edge, reaction edge)\n"
                    "• `.setpoints <user_id> <+N|-N|N>` — Adjust or set a player's arcade points\n"
                    "• `.resetuser <user_id>` — Wipe a player's arcade stats & history\n"
                    "• `.setalliance <TAG> | <Full Name> [| <Footer>]` — Rename alliance live everywhere (Owner DM only)\n"
                    "• `.events` — List all scheduled events with IDs, repeat days & alert status\n"
                    "• `.eventmute <event_id>` — Toggle an event's announcements ON/OFF without deleting\n"
                    "• `.eventrepeat <event_id> <days>` — Set repeat interval (e.g. `2` = every 2 days, `0` = stop)\n"
                    "• `.eventdel <event_id>` — Permanently delete an event\n"
                    "• `.announce <channel_id> <message>` — Send an alliance announcement to any channel\n"
                    "• `.config` / `.setconfig <key> <value>` — View or change any bot config live\n"
                    "• `.backup` — Create a SQLite database backup privately from DM\n"
                    "• `.status` — Check current stealth settings & active games count"
                ),
                color=ROFColors.GOLD,
            )
            await message.channel.send(embed=embed)
            return True

        if cmd == ".status":
            self._purge_stale()
            await message.channel.send(
                f"👑 **Owner Stealth Status**\n"
                f"• Auto-DM Intel: **{'ON' if self.intel_enabled() else 'OFF'}**\n"
                f"• Gameplay Luck Advantage: **{'ON' if self.luck_enabled() else 'OFF'}**\n"
                f"• Active Tracked Games: **`{len(self._games)}`**"
            )
            return True

        if cmd in (".intel", ".god"):
            if args and args[0].lower() in ("on", "true", "1"):
                self.set_intel_enabled(True)
            elif args and args[0].lower() in ("off", "false", "0"):
                self.set_intel_enabled(False)
            else:
                self.set_intel_enabled(not self.intel_enabled())
            await message.channel.send(
                f"👁️ Auto-DM Stealth Intel is now **{'ON' if self.intel_enabled() else 'OFF'}**."
            )
            return True

        if cmd == ".luck":
            if args and args[0].lower() in ("on", "true", "1"):
                self.set_luck_enabled(True)
            elif args and args[0].lower() in ("off", "false", "0"):
                self.set_luck_enabled(False)
            else:
                self.set_luck_enabled(not self.luck_enabled())
            await message.channel.send(
                f"🍀 Owner Gameplay Advantage is now **{'ON' if self.luck_enabled() else 'OFF'}**."
            )
            return True

        if cmd == ".peek":
            self._purge_stale()
            if not self._games:
                await message.channel.send("👁️ No active games tracked right now.")
                return True
            lines: List[str] = []
            for g in sorted(self._games.values(), key=lambda x: x.created_at, reverse=True):
                try:
                    info = g.intel_fn()
                except Exception as e:
                    info = f"(unavailable: {e})"
                lines.append(f"**{g.game_name}**\n{info}")
            embed = discord.Embed(
                title=f"👁️ Live Game Intel ({len(lines)} active)",
                description="\n\n".join(lines)[:4000],
                color=ROFColors.GOLD,
            )
            await message.channel.send(embed=embed)
            return True

        if cmd == ".setpoints":
            if len(args) < 2:
                await message.channel.send("Usage: `.setpoints <user_id> <+100 | -50 | 500>`")
                return True
            try:
                target_id = int(args[0].strip("<@!>"))
                val_str = args[1].strip()
                prof = db.get_player_profile(target_id)
                cur = int(prof.get("points", 0))
                if val_str.startswith(("+", "-")):
                    delta = int(val_str)
                    new_pts = max(0, cur + delta)
                else:
                    new_pts = max(0, int(val_str))
                    delta = new_pts - cur
                db.adjust_player_points(
                    user_id=target_id,
                    new_points=new_pts,
                    username=prof.get("username") or str(target_id),
                )
                await message.channel.send(
                    f"✅ Updated `<@{target_id}>` points: `{cur}` → **`{new_pts}`** (`{delta:+d}`)."
                )
            except Exception as e:
                await message.channel.send(f"❌ Failed: `{e}`")
            return True

        if cmd == ".resetuser":
            if not args:
                await message.channel.send("Usage: `.resetuser <user_id>`")
                return True
            try:
                target_id = int(args[0].strip("<@!>"))
                db.wipe_player_stats(target_id)
                await message.channel.send(f"🗑️ Wiped arcade stats and match history for `<@{target_id}>`.")
            except Exception as e:
                await message.channel.send(f"❌ Failed: `{e}`")
            return True

        if cmd == ".setalliance":
            from core.ui import get_alliance_footer, get_alliance_name, get_alliance_short
            rest = raw[len(".setalliance"):].strip()
            if not rest:
                await message.channel.send(
                    f"🛡️ Current Alliance:\n"
                    f"• **Tag:** `{get_alliance_short()}`\n"
                    f"• **Name:** **{get_alliance_name()}**\n"
                    f"• **Footer:** `{get_alliance_footer()}`\n\n"
                    "Usage: `.setalliance <TAG> | <Full Name>` or `.setalliance <TAG> | <Full Name> | <Custom Footer>`"
                )
                return True
            if "|" in rest:
                parts_pipe = [p.strip() for p in rest.split("|")]
                short_part = parts_pipe[0] if len(parts_pipe) >= 1 else ""
                full_part = parts_pipe[1] if len(parts_pipe) >= 2 else ""
                footer_part = parts_pipe[2] if len(parts_pipe) >= 3 else None
            else:
                short_part = rest.split()[0][:15]
                full_part = rest[:80]
                footer_part = None
            if short_part:
                db.set_config("alliance_short", short_part[:15])
            if full_part:
                db.set_config("alliance_name", full_part[:80])
            if footer_part is not None:
                db.set_config("alliance_footer", footer_part[:100])
            await message.channel.send(
                f"✅ Alliance updated live everywhere!\n"
                f"• **Tag:** `{get_alliance_short()}`\n"
                f"• **Name:** **{get_alliance_name()}**\n"
                f"• **Footer:** `{get_alliance_footer()}`"
            )
            return True

        if cmd == ".events":
            evs = db.get_upcoming_events(include_cancelled=False) or []
            if not evs:
                await message.channel.send("📭 No upcoming scheduled events.")
                return True
            lines = []
            for ev in evs[:15]:
                rep = int(ev.get("repeat_days") or 0)
                ann = int(ev.get("announce_enabled") if ev.get("announce_enabled") is not None else 1)
                rep_s = f"Every {rep}d" if rep > 0 else "Once"
                ann_s = "🔔 ON" if ann == 1 else "🔕 MUTED"
                lines.append(f"• **`{ev['id']}`** — **{ev['name']}** | `{ev['start_time_utc'][:16]} UTC` | 🔁 `{rep_s}` | {ann_s}")
            embed = discord.Embed(title="📅 Scheduled Events (Owner View)", description="\n".join(lines), color=ROFColors.GOLD)
            await message.channel.send(embed=embed)
            return True

        if cmd == ".eventmute":
            if not args:
                await message.channel.send("Usage: `.eventmute <event_id>`")
                return True
            ev = db.get_event(args[0])
            if not ev:
                await message.channel.send(f"❌ Event `{args[0]}` not found.")
                return True
            cur = int(ev.get("announce_enabled") if ev.get("announce_enabled") is not None else 1)
            new_on = (cur == 0)
            db.set_event_announce(ev["id"], new_on)
            await message.channel.send(
                f"{'🔔 Unmuted' if new_on else '🔕 Muted'} announcements for **{ev['name']}** (`{ev['id']}`)."
            )
            return True

        if cmd == ".eventrepeat":
            if len(args) < 2 or not args[1].isdigit():
                await message.channel.send("Usage: `.eventrepeat <event_id> <days>` (e.g. `.eventrepeat a1b2c3 2` or `0` to stop)")
                return True
            days = int(args[1])
            ev = db.set_event_repeat(args[0], days)
            if not ev:
                await message.channel.send(f"❌ Event `{args[0]}` not found.")
                return True
            msg = f"🔁 **{ev['name']}** (`{ev['id']}`) now repeats every **{days} day(s)**." if days > 0 else f"⏹️ Stopped repeating **{ev['name']}** (`{ev['id']}`)."
            await message.channel.send(msg)
            return True

        if cmd == ".eventdel":
            if not args:
                await message.channel.send("Usage: `.eventdel <event_id>`")
                return True
            ev = db.cancel_or_delete_event(args[0], delete_permanently=True)
            if not ev:
                await message.channel.send(f"❌ Event `{args[0]}` not found.")
                return True
            await message.channel.send(f"🗑️ Permanently deleted event **{ev['name']}** (`{ev['id']}`).")
            return True

        if cmd == ".announce":
            if len(args) < 2:
                await message.channel.send("Usage: `.announce <channel_id> <message>`")
                return True
            try:
                cid = int(args[0].strip("<#>"))
                body = raw.split(None, 2)[2]
                ch = bot.get_channel(cid) or await bot.fetch_channel(cid)
                from core.ui import get_alliance_short, rof_embed
                short = get_alliance_short()
                emb = rof_embed(title=f"📢 {short} ALLIANCE ANNOUNCEMENT", description=body, color=ROFColors.GOLD)
                await ch.send(embed=emb)
                await message.channel.send(f"✅ Announcement sent to `<#{cid}>`.")
            except Exception as e:
                await message.channel.send(f"❌ Failed to announce: `{e}`")
            return True

        if cmd == ".config":
            cfg_all = db.get_all_config()
            lines = [f"• `{k}` = `{v}`" for k, v in cfg_all.items()] or ["*(empty)*"]
            embed = discord.Embed(title="⚙️ Bot Config (SQLite)", description="\n".join(lines)[:4000], color=ROFColors.INFO)
            await message.channel.send(embed=embed)
            return True

        if cmd == ".setconfig":
            if len(args) < 2:
                await message.channel.send("Usage: `.setconfig <key> <value>`")
                return True
            k = args[0].strip()
            v = raw.split(None, 2)[2].strip()
            db.set_config(k, v)
            await message.channel.send(f"✅ Config updated: `{k}` = `{v}`")
            return True

        if cmd == ".backup":
            try:
                dest = db.create_backup()
                fname = os.path.basename(dest)
                await message.channel.send(f"💾 Database backup created safely: `{fname}`")
            except Exception as e:
                await message.channel.send(f"❌ Backup failed: `{e}`")
            return True

        return False


owner_stealth = OwnerStealthManager()


# ---------- tactical helpers for strategy board games ----------

def format_treasure_map(bombs: Set[int], opened: Set[int]) -> str:
    """Render a 3x3 Treasure Hunt (Mining) map showing exact gem & bomb positions."""
    rows = []
    for r in range(3):
        cells = []
        for c in range(3):
            idx = r * 3 + c
            if idx in bombs:
                cells.append("💣")
            elif idx in opened:
                cells.append("✅")
            else:
                cells.append("💎")
        rows.append(f"Row {r + 1}: " + " ".join(cells))
    return "\n".join(rows) + "\n*(💎 = Safe Gem, 💣 = Bomb, ✅ = Already Opened)*"


def best_tictactoe_move(board: List[int], my_mark: int) -> Optional[int]:
    """Return 1-indexed cell (1–9) for optimal Tic-Tac-Toe move."""
    win_lines = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6),
    ]
    opp = 2 if my_mark == 1 else 1
    empty = [i for i, v in enumerate(board) if v == 0]
    if not empty:
        return None
    # 1. Win now
    for i in empty:
        board[i] = my_mark
        won = any(all(board[k] == my_mark for k in line) for line in win_lines)
        board[i] = 0
        if won:
            return i + 1
    # 2. Block opponent win
    for i in empty:
        board[i] = opp
        opp_won = any(all(board[k] == opp for k in line) for line in win_lines)
        board[i] = 0
        if opp_won:
            return i + 1
    # 3. Center, corners, edges
    for pref in (4, 0, 2, 6, 8, 1, 3, 5, 7):
        if pref in empty:
            return pref + 1
    return empty[0] + 1


def best_connect4_col(board: List[List[int]], my_token: int) -> Optional[int]:
    """Return 1-indexed column (1–7) for immediate win/block or center preference."""
    rows, cols = len(board), len(board[0])
    opp = 2 if my_token == 1 else 1

    def drop_row(c: int) -> Optional[int]:
        for r in range(rows - 1, -1, -1):
            if board[r][c] == 0:
                return r
        return None

    def wins(tok: int) -> bool:
        for r in range(rows):
            for c in range(cols - 3):
                if all(board[r][c + i] == tok for i in range(4)):
                    return True
        for r in range(rows - 3):
            for c in range(cols):
                if all(board[r + i][c] == tok for i in range(4)):
                    return True
        for r in range(rows - 3):
            for c in range(cols - 3):
                if all(board[r + i][c + i] == tok for i in range(4)):
                    return True
                if all(board[r + 3 - i][c + i] == tok for i in range(4)):
                    return True
        return False

    valid_cols = [c for c in range(cols) if drop_row(c) is not None]
    if not valid_cols:
        return None
    # 1. Immediate win
    for c in valid_cols:
        r = drop_row(c)
        board[r][c] = my_token
        w = wins(my_token)
        board[r][c] = 0
        if w:
            return c + 1
    # 2. Immediate block
    for c in valid_cols:
        r = drop_row(c)
        board[r][c] = opp
        w = wins(opp)
        board[r][c] = 0
        if w:
            return c + 1
    # 3. Center-biased order
    for c in (3, 2, 4, 1, 5, 0, 6):
        if c in valid_cols:
            return c + 1
    return valid_cols[0] + 1
