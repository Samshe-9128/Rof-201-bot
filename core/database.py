# core/database.py
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from core.config import BASE_DIR, DEFAULT_TZ_OFFSET, EVENT_CHANNEL_ID, WELCOME_CHANNEL_ID, RULES_CHANNEL_ID

DB_PATH = os.path.join(BASE_DIR, "rof_bot.db")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

# Legacy JSON paths preserved for backwards compatibility & syncing
ARCADE_FILE = os.path.join(BASE_DIR, "arcade_data.json")
EVENTS_FILE = os.path.join(BASE_DIR, "events.json")
RULES_FILE = os.path.join(BASE_DIR, "rules.json")
APPROVED_FILE = os.path.join(BASE_DIR, "approved.json")
WORDLE_STATS_FILE = os.path.join(BASE_DIR, "wordle_stats.json")

DEFAULT_RULES_LIST = [
    "Respect all alliance members and keep chat welcoming.",
    "Participate actively in scheduled Alliance Brawls, Surge, and SVS events.",
    "No spamming, toxicity, or unnecessary drama in alliance channels.",
    "Follow event instructions from alliance leadership and have fun as a team!",
]

DEFAULT_KNOWLEDGE_ENTRIES = [
    {
        "key": "surge_guide",
        "title": "Surge Event Guide",
        "category": "Events",
        "content": "During Surge, rally with online alliance members at the scheduled Game Time (UTC-2). Check `/events` for the exact start time and join voice or event chat 10 minutes before launch.",
        "keywords": "surge event guide schedule rally how to play surge",
    },
    {
        "key": "svs_strategy",
        "title": "State vs State (SVS) & Alliance Brawl Strategy",
        "category": "Strategy",
        "content": "Save your speedups and stamina items for official SVS and Alliance Brawl windows. Shield up if you are offline during combat phases and coordinate rallies with R4/R5 leaders.",
        "keywords": "svs state brawl strategy shield rally r4 r5 combat",
    },
    {
        "key": "codebreaker_help",
        "title": "How to Play Four-Digit Codebreaker",
        "category": "Games",
        "content": "Create or join a Codebreaker room via `/games` or `/codebreaker`. The bot generates a 4-digit secret code with unique digits (no leading zero). Submit 4-digit guesses privately; 🟢 shows digits in the exact position and 🟡 shows correct digits in the wrong position.",
        "keywords": "codebreaker how to play 4 digit secret code clues mastermind",
    },
    {
        "key": "event_permissions",
        "title": "Who Can Schedule Alliance Events",
        "category": "FAQ",
        "content": "Only authorized administrators and the bot owner can create, edit, or cancel alliance events. All members can view upcoming events at any time using `/events`.",
        "keywords": "schedule create add modify cancel event permission admin who can",
    },
    {
        "key": "member_responsibilities",
        "title": "ROF Member Responsibilities",
        "category": "Guides",
        "content": "Stay active, contribute to alliance tech donations daily, check `/events` for upcoming battles, and treat fellow ROF members with respect.",
        "keywords": "member responsibilities duties donations active rules guide",
    },
]


class Database:
    """Thread-safe SQLite database with WAL mode, cloud/FUSE filesystem resilience, legacy JSON auto-migration, and backup support."""

    def __init__(self, db_path: str = DB_PATH):
        self.target_db_path = db_path
        self.db_path = self._resolve_working_db_path(db_path)
        self._lock = threading.RLock()
        self._init_db()
        self._migrate_legacy_json()

    def _resolve_working_db_path(self, requested_path: str) -> str:
        """Use requested_path directly when the filesystem supports SQLite locking; fallback to temp storage + file sync on FUSE mounts."""
        try:
            conn = sqlite3.connect(requested_path, timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("CREATE TABLE IF NOT EXISTS _fs_probe (id INTEGER);")
            conn.close()
            return requested_path
        except sqlite3.OperationalError:
            try:
                if os.path.exists(requested_path) and os.path.getsize(requested_path) == 0:
                    os.remove(requested_path)
            except Exception:
                pass
            fallback = os.path.join(tempfile.gettempdir(), "rof_bot_runtime.db")
            if os.path.exists(requested_path) and os.path.getsize(requested_path) > 0:
                try:
                    shutil.copy2(requested_path, fallback)
                except Exception:
                    pass
            return fallback

    def _mirror_if_needed(self):
        if self.db_path != self.target_db_path and os.path.exists(self.db_path):
            try:
                shutil.copy2(self.db_path, self.target_db_path)
            except Exception:
                pass

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.executescript(
                        """
                        CREATE TABLE IF NOT EXISTS players (
                            user_id INTEGER PRIMARY KEY,
                            username TEXT DEFAULT '',
                            points INTEGER DEFAULT 0,
                            games_played INTEGER DEFAULT 0,
                            wins INTEGER DEFAULT 0,
                            losses INTEGER DEFAULT 0,
                            draws INTEGER DEFAULT 0,
                            best_score INTEGER DEFAULT 0,
                            best_reaction_ms INTEGER DEFAULT NULL,
                            total_reaction_ms INTEGER DEFAULT 0,
                            reaction_count INTEGER DEFAULT 0,
                            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE IF NOT EXISTS game_stats (
                            user_id INTEGER NOT NULL,
                            game_name TEXT NOT NULL,
                            played INTEGER DEFAULT 0,
                            wins INTEGER DEFAULT 0,
                            losses INTEGER DEFAULT 0,
                            draws INTEGER DEFAULT 0,
                            best_score INTEGER DEFAULT 0,
                            best_reaction_ms INTEGER DEFAULT NULL,
                            last_played_at TEXT DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (user_id, game_name)
                        );

                        CREATE TABLE IF NOT EXISTS game_history (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            game_name TEXT NOT NULL,
                            mode TEXT DEFAULT 'single',
                            result TEXT NOT NULL,
                            score INTEGER DEFAULT 0,
                            points_earned INTEGER DEFAULT 0,
                            attempts INTEGER DEFAULT 0,
                            duration_sec REAL DEFAULT 0.0,
                            reaction_ms INTEGER DEFAULT NULL,
                            played_at INTEGER NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_history_user ON game_history(user_id, played_at DESC);
                        CREATE INDEX IF NOT EXISTS idx_history_time ON game_history(played_at DESC);
                        CREATE INDEX IF NOT EXISTS idx_history_game ON game_history(game_name, score DESC);

                        CREATE TABLE IF NOT EXISTS events (
                            id TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            description TEXT DEFAULT '',
                            start_time_utc TEXT NOT NULL,
                            duration_minutes INTEGER DEFAULT 60,
                            channel_id INTEGER DEFAULT 0,
                            creator_id INTEGER DEFAULT 0,
                            reminder_minutes INTEGER DEFAULT 10,
                            reminder_sent INTEGER DEFAULT 0,
                            status TEXT DEFAULT 'scheduled',
                            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                        );
                        CREATE INDEX IF NOT EXISTS idx_events_status_time ON events(status, start_time_utc);

                        CREATE TABLE IF NOT EXISTS rules (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            rule_number INTEGER NOT NULL,
                            content TEXT NOT NULL,
                            updated_by INTEGER DEFAULT 0,
                            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE IF NOT EXISTS knowledge_base (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            key TEXT UNIQUE NOT NULL,
                            title TEXT NOT NULL,
                            category TEXT DEFAULT 'General',
                            content TEXT NOT NULL,
                            keywords TEXT DEFAULT '',
                            updated_by INTEGER DEFAULT 0,
                            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE IF NOT EXISTS server_config (
                            key TEXT PRIMARY KEY,
                            value TEXT NOT NULL,
                            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE IF NOT EXISTS admins (
                            target_id INTEGER NOT NULL,
                            target_type TEXT NOT NULL DEFAULT 'user',
                            added_by INTEGER DEFAULT 0,
                            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (target_id, target_type)
                        );

                        CREATE TABLE IF NOT EXISTS audit_logs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            actor_id INTEGER NOT NULL,
                            action TEXT NOT NULL,
                            details TEXT DEFAULT '',
                            created_at TEXT DEFAULT CURRENT_TIMESTAMP
                        );
                        """
                    )

                    defaults = {
                        "game_tz_offset": str(DEFAULT_TZ_OFFSET),
                        "event_channel_id": str(EVENT_CHANNEL_ID),
                        "welcome_channel_id": str(WELCOME_CHANNEL_ID),
                        "rules_channel_id": str(RULES_CHANNEL_ID),
                        "assistant_channels": "[]",
                        "default_reminder_minutes": "10",
                        "wipe_stats_on_leave": "false",
                        "wordle_open_to_all": "true",
                    }
                    for k, v in defaults.items():
                        conn.execute(
                            "INSERT OR IGNORE INTO server_config (key, value) VALUES (?, ?)",
                            (k, v),
                        )

                    kb_count = conn.execute("SELECT COUNT(*) FROM knowledge_base").fetchone()[0]
                    if kb_count == 0:
                        for item in DEFAULT_KNOWLEDGE_ENTRIES:
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO knowledge_base (key, title, category, content, keywords)
                                VALUES (?, ?, ?, ?, ?)
                                """,
                                (item["key"], item["title"], item["category"], item["content"], item["keywords"]),
                            )
            finally:
                conn.close()
            self._mirror_if_needed()

    def _migrate_legacy_json(self):
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    migrated = conn.execute(
                        "SELECT value FROM server_config WHERE key = 'legacy_json_migrated'"
                    ).fetchone()
                    if migrated and migrated["value"] == "true":
                        return

                    if os.path.exists(ARCADE_FILE):
                        try:
                            with open(ARCADE_FILE, "r", encoding="utf-8") as f:
                                arcade = json.load(f)
                            for uid_str, pdata in arcade.items():
                                uid = int(uid_str)
                                pts = int(pdata.get("points", 0))
                                gp = int(pdata.get("games_played", 0))
                                wins = int(pdata.get("wins", 0))
                                losses = max(0, gp - wins)
                                conn.execute(
                                    """
                                    INSERT INTO players (user_id, points, games_played, wins, losses)
                                    VALUES (?, ?, ?, ?, ?)
                                    ON CONFLICT(user_id) DO UPDATE SET
                                        points = MAX(players.points, excluded.points),
                                        games_played = MAX(players.games_played, excluded.games_played),
                                        wins = MAX(players.wins, excluded.wins)
                                    """,
                                    (uid, pts, gp, wins, losses),
                                )
                                for gname, gstat in pdata.get("game_stats", {}).items():
                                    g_played = int(gstat.get("played", 0))
                                    g_won = int(gstat.get("won", 0))
                                    g_loss = max(0, g_played - g_won)
                                    conn.execute(
                                        """
                                        INSERT INTO game_stats (user_id, game_name, played, wins, losses, best_score)
                                        VALUES (?, ?, ?, ?, ?, ?)
                                        ON CONFLICT(user_id, game_name) DO UPDATE SET
                                            played = MAX(game_stats.played, excluded.played),
                                            wins = MAX(game_stats.wins, excluded.wins)
                                        """,
                                        (uid, gname, g_played, g_won, g_loss, g_won * 25),
                                    )
                        except Exception as e:
                            print(f"[DB] Notice during arcade_data.json migration: {e}")

                    if os.path.exists(WORDLE_STATS_FILE):
                        try:
                            with open(WORDLE_STATS_FILE, "r", encoding="utf-8") as f:
                                wstats = json.load(f)
                            for uid_str, s in wstats.items():
                                uid = int(uid_str)
                                gp = int(s.get("games_played", 0))
                                wins = int(s.get("wins", 0))
                                losses = max(0, gp - wins)
                                conn.execute(
                                    "INSERT OR IGNORE INTO players (user_id, points, games_played, wins, losses) VALUES (?, 0, 0, 0, 0)",
                                    (uid,),
                                )
                                conn.execute(
                                    """
                                    INSERT INTO game_stats (user_id, game_name, played, wins, losses, best_score)
                                    VALUES (?, 'Wordle', ?, ?, ?, ?)
                                    ON CONFLICT(user_id, game_name) DO UPDATE SET
                                        played = MAX(game_stats.played, excluded.played),
                                        wins = MAX(game_stats.wins, excluded.wins),
                                        losses = MAX(game_stats.losses, excluded.losses)
                                    """,
                                    (uid, gp, wins, losses, int(s.get("max_streak", 0)) * 20),
                                )
                        except Exception as e:
                            print(f"[DB] Notice during wordle_stats.json migration: {e}")

                    if os.path.exists(EVENTS_FILE):
                        try:
                            with open(EVENTS_FILE, "r", encoding="utf-8") as f:
                                events_list = json.load(f)
                            if isinstance(events_list, list):
                                for ev in events_list:
                                    ev_id = str(ev.get("id") or "")
                                    if not ev_id:
                                        continue
                                    dt = datetime.fromisoformat(ev["time"])
                                    if dt.tzinfo is None:
                                        dt = dt.replace(tzinfo=timezone(timedelta(hours=DEFAULT_TZ_OFFSET)))
                                    utc_iso = dt.astimezone(timezone.utc).isoformat()
                                    conn.execute(
                                        """
                                        INSERT OR IGNORE INTO events
                                        (id, name, description, start_time_utc, duration_minutes, channel_id, creator_id, reminder_minutes, reminder_sent, status)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled')
                                        """,
                                        (
                                            ev_id,
                                            ev.get("name", "Alliance Event"),
                                            ev.get("description", ""),
                                            utc_iso,
                                            int(ev.get("duration_minutes", 60)),
                                            int(ev.get("channel", EVENT_CHANNEL_ID or 0)),
                                            int(ev.get("creator", 0)),
                                            int(ev.get("reminder_minutes", 10)),
                                            1 if ev.get("reminder_sent") else 0,
                                        ),
                                    )
                        except Exception as e:
                            print(f"[DB] Notice during events.json migration: {e}")

                    rules_count = conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
                    if rules_count == 0:
                        migrated_rules = []
                        if os.path.exists(RULES_FILE):
                            try:
                                with open(RULES_FILE, "r", encoding="utf-8") as f:
                                    raw_rules = json.load(f).get("rules", "")
                                for line in raw_rules.splitlines():
                                    clean = line.strip()
                                    if not clean or clean.startswith("*Use"):
                                        continue
                                    for prefix in ["**1.**", "**2.**", "**3.**", "**4.**", "**5.**", "1.", "2.", "3.", "4.", "5."]:
                                        if clean.startswith(prefix):
                                            clean = clean[len(prefix):].strip()
                                    if clean:
                                        migrated_rules.append(clean)
                            except Exception:
                                pass
                        if not migrated_rules:
                            migrated_rules = DEFAULT_RULES_LIST
                        for idx, rtext in enumerate(migrated_rules, 1):
                            conn.execute(
                                "INSERT INTO rules (rule_number, content) VALUES (?, ?)",
                                (idx, rtext),
                            )

                    conn.execute(
                        "INSERT OR REPLACE INTO server_config (key, value) VALUES ('legacy_json_migrated', 'true')"
                    )
            finally:
                conn.close()
        self._sync_rules_json()
        self._sync_events_json()
        self._mirror_if_needed()

    def get_config(self, key: str, default: str = "") -> str:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT value FROM server_config WHERE key = ?", (key,)).fetchone()
                return row["value"] if row else default
            finally:
                conn.close()

    def set_config(self, key: str, value: str):
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO server_config (key, value, updated_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                        """,
                        (str(key), str(value)),
                    )
            finally:
                conn.close()
            self._mirror_if_needed()

    def add_admin(self, target_id: int, target_type: str = "user", added_by: int = 0):
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO admins (target_id, target_type, added_by) VALUES (?, ?, ?)",
                        (int(target_id), target_type, int(added_by)),
                    )
            finally:
                conn.close()
            self._mirror_if_needed()

    def remove_admin(self, target_id: int, target_type: str = "user") -> bool:
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    cur = conn.execute(
                        "DELETE FROM admins WHERE target_id = ? AND target_type = ?",
                        (int(target_id), target_type),
                    )
                    res = cur.rowcount > 0
            finally:
                conn.close()
            self._mirror_if_needed()
            return res

    def get_admins(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute("SELECT target_id, target_type, added_by, added_at FROM admins").fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def is_db_admin(self, user_id: int, role_ids: List[int] = None) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT 1 FROM admins WHERE target_id = ? AND target_type = 'user'",
                    (int(user_id),),
                ).fetchone()
                if row:
                    return True
                if role_ids:
                    placeholders = ",".join("?" for _ in role_ids)
                    r_row = conn.execute(
                        f"SELECT 1 FROM admins WHERE target_type = 'role' AND target_id IN ({placeholders})",
                        [int(r) for r in role_ids],
                    ).fetchone()
                    if r_row:
                        return True
                return False
            finally:
                conn.close()

    def log_audit(self, actor_id: int, action: str, details: str = ""):
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO audit_logs (actor_id, action, details) VALUES (?, ?, ?)",
                        (int(actor_id), action, details),
                    )
            finally:
                conn.close()

    def get_audit_logs(self, limit: int = 15) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT id, actor_id, action, details, created_at FROM audit_logs ORDER BY id DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def record_game_result(
        self,
        user_id: int,
        game_name: str,
        result: str = "win",
        score: int = 0,
        points_earned: int = 0,
        attempts: int = 0,
        duration_sec: float = 0.0,
        reaction_ms: Optional[int] = None,
        mode: str = "single",
        username: str = "",
    ) -> int:
        uid = int(user_id)
        is_win = 1 if result == "win" else 0
        is_loss = 1 if result == "loss" else 0
        is_draw = 1 if result == "draw" else 0
        now_ts = int(time.time())

        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO players (user_id, username, points, games_played, wins, losses, draws, best_score)
                        VALUES (?, ?, 0, 0, 0, 0, 0, 0)
                        ON CONFLICT(user_id) DO NOTHING
                        """,
                        (uid, username or ""),
                    )
                    if username:
                        conn.execute("UPDATE players SET username = ? WHERE user_id = ?", (username, uid))

                    conn.execute(
                        """
                        UPDATE players SET
                            points = points + ?,
                            games_played = games_played + 1,
                            wins = wins + ?,
                            losses = losses + ?,
                            draws = draws + ?,
                            best_score = MAX(best_score, ?),
                            best_reaction_ms = CASE
                                WHEN ? IS NOT NULL AND (best_reaction_ms IS NULL OR ? < best_reaction_ms) THEN ?
                                ELSE best_reaction_ms
                            END,
                            total_reaction_ms = total_reaction_ms + COALESCE(?, 0),
                            reaction_count = reaction_count + CASE WHEN ? IS NOT NULL THEN 1 ELSE 0 END,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                        """,
                        (
                            int(points_earned),
                            is_win,
                            is_loss,
                            is_draw,
                            int(score),
                            reaction_ms,
                            reaction_ms,
                            reaction_ms,
                            reaction_ms,
                            reaction_ms,
                            uid,
                        ),
                    )

                    conn.execute(
                        """
                        INSERT INTO game_stats (user_id, game_name, played, wins, losses, draws, best_score, best_reaction_ms)
                        VALUES (?, ?, 1, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id, game_name) DO UPDATE SET
                            played = game_stats.played + 1,
                            wins = game_stats.wins + excluded.wins,
                            losses = game_stats.losses + excluded.losses,
                            draws = game_stats.draws + excluded.draws,
                            best_score = MAX(game_stats.best_score, excluded.best_score),
                            best_reaction_ms = CASE
                                WHEN excluded.best_reaction_ms IS NOT NULL AND (game_stats.best_reaction_ms IS NULL OR excluded.best_reaction_ms < game_stats.best_reaction_ms)
                                THEN excluded.best_reaction_ms
                                ELSE game_stats.best_reaction_ms
                            END,
                            last_played_at = CURRENT_TIMESTAMP
                        """,
                        (uid, game_name, is_win, is_loss, is_draw, int(score), reaction_ms),
                    )

                    conn.execute(
                        """
                        INSERT INTO game_history
                        (user_id, game_name, mode, result, score, points_earned, attempts, duration_sec, reaction_ms, played_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            uid,
                            game_name,
                            mode,
                            result,
                            int(score),
                            int(points_earned),
                            int(attempts),
                            float(duration_sec),
                            reaction_ms,
                            now_ts,
                        ),
                    )

                    new_pts = conn.execute("SELECT points FROM players WHERE user_id = ?", (uid,)).fetchone()["points"]
            finally:
                conn.close()

        self._sync_arcade_json()
        self._mirror_if_needed()
        return int(new_pts)

    def get_player_profile(self, user_id: int) -> Dict[str, Any]:
        uid = int(user_id)
        with self._lock:
            conn = self._connect()
            try:
                p = conn.execute("SELECT * FROM players WHERE user_id = ?", (uid,)).fetchone()
                g_rows = conn.execute(
                    "SELECT * FROM game_stats WHERE user_id = ? ORDER BY played DESC, wins DESC",
                    (uid,),
                ).fetchall()
                games = {r["game_name"]: dict(r) for r in g_rows}

                if not p:
                    return {
                        "user_id": uid,
                        "username": "",
                        "points": 0,
                        "games_played": 0,
                        "wins": 0,
                        "losses": 0,
                        "draws": 0,
                        "win_rate": 0.0,
                        "best_score": 0,
                        "best_reaction_ms": None,
                        "avg_reaction_ms": None,
                        "favourite_game": "None yet",
                        "game_stats": {},
                    }

                gp = int(p["games_played"])
                wins = int(p["wins"])
                losses = int(p["losses"])
                draws = int(p["draws"])
                win_rate = round((wins / gp) * 100, 1) if gp > 0 else 0.0
                fav_game = g_rows[0]["game_name"] if g_rows else "None yet"
                rcount = int(p["reaction_count"] or 0)
                avg_react = int(p["total_reaction_ms"] / rcount) if rcount > 0 else None

                return {
                    "user_id": uid,
                    "username": p["username"] or "",
                    "points": int(p["points"]),
                    "games_played": gp,
                    "wins": wins,
                    "losses": losses,
                    "draws": draws,
                    "win_rate": win_rate,
                    "best_score": int(p["best_score"]),
                    "best_reaction_ms": p["best_reaction_ms"],
                    "avg_reaction_ms": avg_react,
                    "favourite_game": fav_game,
                    "game_stats": games,
                }
            finally:
                conn.close()

    def get_player_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM game_history WHERE user_id = ? ORDER BY played_at DESC LIMIT ?",
                    (int(user_id), int(limit)),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_leaderboard(
        self,
        scope: str = "overall",
        game_name: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                if scope == "weekly":
                    cutoff = int(time.time()) - (7 * 86400)
                    rows = conn.execute(
                        """
                        SELECT h.user_id, COALESCE(p.username, '') AS username,
                               SUM(h.points_earned) AS points,
                               COUNT(*) AS games_played,
                               SUM(CASE WHEN h.result = 'win' THEN 1 ELSE 0 END) AS wins,
                               MAX(h.score) AS best_score
                        FROM game_history h
                        LEFT JOIN players p ON p.user_id = h.user_id
                        WHERE h.played_at >= ?
                        GROUP BY h.user_id
                        ORDER BY points DESC, wins DESC
                        LIMIT ?
                        """,
                        (cutoff, int(limit)),
                    ).fetchall()
                    return [dict(r) for r in rows]

                if scope == "game" and game_name:
                    rows = conn.execute(
                        """
                        SELECT gs.user_id, COALESCE(p.username, '') AS username,
                               gs.wins, gs.played AS games_played, gs.best_score,
                               gs.best_reaction_ms, COALESCE(p.points, 0) AS points
                        FROM game_stats gs
                        LEFT JOIN players p ON p.user_id = gs.user_id
                        WHERE LOWER(gs.game_name) = LOWER(?) AND gs.played > 0
                        ORDER BY gs.wins DESC, gs.best_score DESC, gs.played ASC
                        LIMIT ?
                        """,
                        (game_name, int(limit)),
                    ).fetchall()
                    return [dict(r) for r in rows]

                rows = conn.execute(
                    """
                    SELECT user_id, username, points, games_played, wins, losses, draws, best_score, best_reaction_ms
                    FROM players
                    WHERE games_played > 0 OR points > 0
                    ORDER BY points DESC, wins DESC, best_score DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def wipe_player_stats(self, user_id: int):
        uid = int(user_id)
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute("DELETE FROM players WHERE user_id = ?", (uid,))
                    conn.execute("DELETE FROM game_stats WHERE user_id = ?", (uid,))
                    conn.execute("DELETE FROM game_history WHERE user_id = ?", (uid,))
            finally:
                conn.close()
        self._sync_arcade_json()
        self._mirror_if_needed()

    def _sync_arcade_json(self):
        try:
            with self._lock:
                conn = self._connect()
                try:
                    p_rows = conn.execute("SELECT * FROM players").fetchall()
                    g_rows = conn.execute("SELECT * FROM game_stats").fetchall()
                finally:
                    conn.close()
            out = {}
            for p in p_rows:
                uid = str(p["user_id"])
                out[uid] = {
                    "points": p["points"],
                    "games_played": p["games_played"],
                    "wins": p["wins"],
                    "losses": p["losses"],
                    "draws": p["draws"],
                    "game_stats": {},
                }
            for g in g_rows:
                uid = str(g["user_id"])
                if uid in out:
                    out[uid]["game_stats"][g["game_name"]] = {
                        "played": g["played"],
                        "won": g["wins"],
                    }
            with open(ARCADE_FILE, "w", encoding="utf-8") as f:
                json.dump(out, f, indent=4)
        except Exception:
            pass

    def create_event(
        self,
        event_id: str,
        name: str,
        description: str,
        start_time_utc: datetime,
        duration_minutes: int,
        channel_id: int,
        creator_id: int,
        reminder_minutes: int = 10,
    ) -> Dict[str, Any]:
        utc_iso = start_time_utc.astimezone(timezone.utc).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO events
                        (id, name, description, start_time_utc, duration_minutes, channel_id, creator_id, reminder_minutes, reminder_sent, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'scheduled')
                        """,
                        (
                            event_id,
                            name.strip(),
                            description.strip(),
                            utc_iso,
                            int(duration_minutes),
                            int(channel_id),
                            int(creator_id),
                            int(reminder_minutes),
                        ),
                    )
            finally:
                conn.close()
        self._sync_events_json()
        self._mirror_if_needed()
        return self.get_event(event_id)

    def update_event(
        self,
        event_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        start_time_utc: Optional[datetime] = None,
        duration_minutes: Optional[int] = None,
        channel_id: Optional[int] = None,
        reminder_minutes: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        ev = self.get_event(event_id)
        if not ev:
            return None
        new_name = name.strip() if name is not None else ev["name"]
        new_desc = description.strip() if description is not None else ev["description"]
        new_utc = start_time_utc.astimezone(timezone.utc).isoformat() if start_time_utc else ev["start_time_utc"]
        new_dur = int(duration_minutes) if duration_minutes is not None else ev["duration_minutes"]
        new_chan = int(channel_id) if channel_id is not None else ev["channel_id"]
        new_rem = int(reminder_minutes) if reminder_minutes is not None else ev["reminder_minutes"]

        reminder_sent = ev["reminder_sent"]
        if start_time_utc is not None or reminder_minutes is not None:
            dt_check = datetime.fromisoformat(new_utc)
            if dt_check > datetime.now(timezone.utc):
                reminder_sent = 0

        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        """
                        UPDATE events SET
                            name = ?,
                            description = ?,
                            start_time_utc = ?,
                            duration_minutes = ?,
                            channel_id = ?,
                            reminder_minutes = ?,
                            reminder_sent = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (new_name, new_desc, new_utc, new_dur, new_chan, new_rem, reminder_sent, event_id),
                    )
            finally:
                conn.close()
        self._sync_events_json()
        self._mirror_if_needed()
        return self.get_event(event_id)

    def cancel_or_delete_event(self, event_id: str, delete_permanently: bool = False) -> Optional[Dict[str, Any]]:
        ev = self.get_event(event_id)
        if not ev:
            return None
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    if delete_permanently:
                        conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
                    else:
                        conn.execute(
                            "UPDATE events SET status = 'cancelled', reminder_sent = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (event_id,),
                        )
            finally:
                conn.close()
        self._sync_events_json()
        self._mirror_if_needed()
        return ev

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT * FROM events WHERE LOWER(id) = LOWER(?)", (event_id.strip(),)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def get_upcoming_events(self, include_cancelled: bool = False) -> List[Dict[str, Any]]:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                if include_cancelled:
                    rows = conn.execute(
                        "SELECT * FROM events WHERE start_time_utc >= ? ORDER BY start_time_utc ASC",
                        (now_iso,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM events WHERE status = 'scheduled' AND start_time_utc >= ? ORDER BY start_time_utc ASC",
                        (now_iso,),
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_due_reminders(self) -> List[Dict[str, Any]]:
        now_utc = datetime.now(timezone.utc)
        due = []
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM events WHERE status = 'scheduled' AND reminder_sent = 0"
                ).fetchall()
                for r in rows:
                    ev = dict(r)
                    start_dt = datetime.fromisoformat(ev["start_time_utc"])
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=timezone.utc)
                    rem_dt = start_dt - timedelta(minutes=int(ev.get("reminder_minutes", 10)))
                    if now_utc >= start_dt:
                        conn.execute(
                            "UPDATE events SET reminder_sent = 1, status = 'completed' WHERE id = ?",
                            (ev["id"],),
                        )
                        conn.commit()
                    elif now_utc >= rem_dt:
                        due.append(ev)
            finally:
                conn.close()
        return due

    def mark_reminder_sent(self, event_id: str):
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        "UPDATE events SET reminder_sent = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (event_id,),
                    )
            finally:
                conn.close()
        self._sync_events_json()
        self._mirror_if_needed()

    def _sync_events_json(self):
        try:
            with self._lock:
                conn = self._connect()
                try:
                    rows = conn.execute("SELECT * FROM events WHERE status = 'scheduled'").fetchall()
                finally:
                    conn.close()
            legacy = []
            for r in rows:
                legacy.append(
                    {
                        "id": r["id"],
                        "name": r["name"],
                        "description": r["description"],
                        "time": r["start_time_utc"],
                        "duration_minutes": r["duration_minutes"],
                        "channel": r["channel_id"],
                        "reminder_sent": bool(r["reminder_sent"]),
                        "creator": r["creator_id"],
                    }
                )
            with open(EVENTS_FILE, "w", encoding="utf-8") as f:
                json.dump(legacy, f, indent=4)
        except Exception:
            pass

    def get_rules_list(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute("SELECT * FROM rules ORDER BY rule_number ASC, id ASC").fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_formatted_rules(self) -> str:
        rules = self.get_rules_list()
        if not rules:
            return "No rules have been configured yet."
        return "\n".join(f"**{r['rule_number']}.** {r['content']}" for r in rules)

    def add_rule(self, content: str, actor_id: int = 0) -> int:
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    max_num = conn.execute("SELECT COALESCE(MAX(rule_number), 0) FROM rules").fetchone()[0]
                    next_num = int(max_num) + 1
                    conn.execute(
                        "INSERT INTO rules (rule_number, content, updated_by) VALUES (?, ?, ?)",
                        (next_num, content.strip(), int(actor_id)),
                    )
            finally:
                conn.close()
        self._sync_rules_json()
        self._mirror_if_needed()
        return next_num

    def edit_rule(self, rule_number: int, content: str, actor_id: int = 0) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    cur = conn.execute(
                        "UPDATE rules SET content = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP WHERE rule_number = ?",
                        (content.strip(), int(actor_id), int(rule_number)),
                    )
                    updated = cur.rowcount > 0
            finally:
                conn.close()
        if updated:
            self._sync_rules_json()
            self._mirror_if_needed()
        return updated

    def remove_rule(self, rule_number: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    cur = conn.execute("DELETE FROM rules WHERE rule_number = ?", (int(rule_number),))
                    if cur.rowcount == 0:
                        return False
                    remaining = conn.execute("SELECT id FROM rules ORDER BY rule_number ASC, id ASC").fetchall()
                    for idx, row in enumerate(remaining, 1):
                        conn.execute("UPDATE rules SET rule_number = ? WHERE id = ?", (idx, row["id"]))
            finally:
                conn.close()
        self._sync_rules_json()
        self._mirror_if_needed()
        return True

    def replace_all_rules(self, raw_text: str, actor_id: int = 0):
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute("DELETE FROM rules")
                    for idx, line in enumerate(lines, 1):
                        clean = line
                        prefix = f"**{idx}.**"
                        if clean.startswith(prefix):
                            clean = clean[len(prefix):].strip()
                        elif clean.startswith(f"{idx}."):
                            clean = clean[len(f"{idx}."):].strip()
                        conn.execute(
                            "INSERT INTO rules (rule_number, content, updated_by) VALUES (?, ?, ?)",
                            (idx, clean, int(actor_id)),
                        )
            finally:
                conn.close()
        self._sync_rules_json()
        self._mirror_if_needed()

    def _sync_rules_json(self):
        try:
            text = self.get_formatted_rules()
            with open(RULES_FILE, "w", encoding="utf-8") as f:
                json.dump({"rules": text}, f, indent=4)
        except Exception:
            pass

    def upsert_knowledge(
        self,
        key: str,
        title: str,
        category: str,
        content: str,
        keywords: str = "",
        actor_id: int = 0,
    ) -> Dict[str, Any]:
        clean_key = key.strip().lower().replace(" ", "_")
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO knowledge_base (key, title, category, content, keywords, updated_by, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(key) DO UPDATE SET
                            title = excluded.title,
                            category = excluded.category,
                            content = excluded.content,
                            keywords = excluded.keywords,
                            updated_by = excluded.updated_by,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (clean_key, title.strip(), category.strip(), content.strip(), keywords.strip(), int(actor_id)),
                    )
                    row = conn.execute("SELECT * FROM knowledge_base WHERE key = ?", (clean_key,)).fetchone()
                    res = dict(row)
            finally:
                conn.close()
            self._mirror_if_needed()
            return res

    def remove_knowledge(self, key: str) -> bool:
        clean_key = key.strip().lower().replace(" ", "_")
        with self._lock:
            conn = self._connect()
            try:
                with conn:
                    cur = conn.execute("DELETE FROM knowledge_base WHERE LOWER(key) = ?", (clean_key,))
                    res = cur.rowcount > 0
            finally:
                conn.close()
            self._mirror_if_needed()
            return res

    def list_knowledge(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                if category:
                    rows = conn.execute(
                        "SELECT * FROM knowledge_base WHERE LOWER(category) = LOWER(?) ORDER BY category, title",
                        (category.strip(),),
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM knowledge_base ORDER BY category, title").fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_knowledge(self, key: str) -> Optional[Dict[str, Any]]:
        clean_key = key.strip().lower().replace(" ", "_")
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT * FROM knowledge_base WHERE LOWER(key) = ?", (clean_key,)).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def create_backup(self) -> str:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(BACKUP_DIR, f"rof_bot_backup_{stamp}.db")
        with self._lock:
            shutil.copy2(self.db_path, dest)
            self._mirror_if_needed()
        return dest


db = Database()
