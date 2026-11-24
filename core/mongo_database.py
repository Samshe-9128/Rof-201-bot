# core/mongo_database.py
import copy
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pymongo import ASCENDING, DESCENDING, MongoClient

from core.config import (
    DATA_DIR,
    DEFAULT_TZ_OFFSET,
    EVENT_CHANNEL_ID,
    RULES_CHANNEL_ID,
    WELCOME_CHANNEL_ID,
)

BACKUP_DIR = os.path.join(DATA_DIR, "backups")

DEFAULT_RULES_LIST = [
    "Respect all alliance members and keep chat welcoming.",
    "Participate actively in scheduled Alliance Brawls, Surge, and SVS events.",
    "No spamming, toxicity, or unnecessary drama in alliance channels.",
    "Follow event instructions from alliance leadership and have fun as a team!",
]

from core.knowledge_defaults import DEFAULT_KNOWLEDGE_ENTRIES


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _strip_id(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not doc:
        return None
    out = dict(doc)
    out.pop("_id", None)
    return out


class MongoDatabase:
    """Drop-in MongoDB backend matching the exact API of SQLite Database."""

    backend = "MongoDB"

    def __init__(self, mongo_uri: str, db_name: str = "haven_bot", client: Optional[Any] = None):
        self._lock = threading.RLock()
        self._db_name = db_name
        self.db_path = f"mongodb://{db_name}"
        self._client = client if client is not None else MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            retryWrites=True,
        )
        # Verify connectivity early on real MongoClient
        if client is None:
            self._client.admin.command("ping")
        self._db = self._client[db_name]

        self._players = self._db["players"]
        self._game_stats = self._db["game_stats"]
        self._game_history = self._db["game_history"]
        self._events = self._db["events"]
        self._rules = self._db["rules"]
        self._knowledge = self._db["knowledge_base"]
        self._config = self._db["server_config"]
        self._admins = self._db["admins"]
        self._audit = self._db["audit_logs"]
        self._kv = self._db["kv_store"]
        self._counters = self._db["_counters"]

        self._config_cache: Dict[str, str] = {}
        self._init_db()
        self._load_config_cache()

    def close(self):
        with self._lock:
            if self._client is not None:
                try:
                    self._client.close()
                finally:
                    self._client = None

    def _next_seq(self, name: str) -> int:
        doc = self._counters.find_one_and_update(
            {"_id": name},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=True,
        )
        return int(doc["seq"])

    def _init_db(self):
        with self._lock:
            # Indexes (idempotent in MongoDB)
            self._players.create_index([("user_id", ASCENDING)], unique=True)
            self._players.create_index([("points", DESCENDING)])
            self._game_stats.create_index([("user_id", ASCENDING), ("game_name", ASCENDING)], unique=True)
            self._game_history.create_index([("user_id", ASCENDING), ("played_at", DESCENDING)])
            self._game_history.create_index([("played_at", DESCENDING)])
            self._events.create_index([("id", ASCENDING)], unique=True)
            self._events.create_index([("status", ASCENDING), ("start_time_utc", ASCENDING)])
            self._rules.create_index([("rule_number", ASCENDING)])
            self._knowledge.create_index([("key", ASCENDING)], unique=True)
            self._config.create_index([("key", ASCENDING)], unique=True)
            self._admins.create_index([("target_id", ASCENDING), ("target_type", ASCENDING)], unique=True)
            self._audit.create_index([("id", DESCENDING)])

            # Seed default config keys without overwriting existing values
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
            now_s = _utc_now_str()
            for k, v in defaults.items():
                self._config.update_one(
                    {"key": k},
                    {"$setOnInsert": {"key": k, "value": v, "updated_at": now_s}},
                    upsert=True,
                )

            # Remove deprecated alliance-override keys so HAV / Haven is authoritative
            self._config.delete_many({"key": {"$in": ["alliance_short", "alliance_name", "alliance_footer"]}})

            # Auto-seed any missing default knowledge base entries (preserves custom edits)
            existing_keys = {d.get("key") for d in self._knowledge.find({}, {"key": 1})}
            for item in DEFAULT_KNOWLEDGE_ENTRIES:
                if item["key"] not in existing_keys:
                    self._knowledge.update_one(
                        {"key": item["key"]},
                        {
                            "$setOnInsert": {
                                "id": self._next_seq("knowledge_base"),
                                "key": item["key"],
                                "title": item["title"],
                                "category": item["category"],
                                "content": item["content"],
                                "keywords": item["keywords"],
                                "updated_by": 0,
                                "updated_at": now_s,
                            }
                        },
                        upsert=True,
                    )

            # Seed default rules if empty
            if self._rules.count_documents({}) == 0:
                for idx, content in enumerate(DEFAULT_RULES_LIST, 1):
                    self._rules.insert_one(
                        {
                            "id": self._next_seq("rules"),
                            "rule_number": idx,
                            "content": content,
                            "updated_by": 0,
                            "updated_at": now_s,
                        }
                    )

    def _load_config_cache(self):
        with self._lock:
            self._config_cache = {
                doc["key"]: doc["value"]
                for doc in self._config.find({}, {"key": 1, "value": 1})
            }

    # ---------- Config ----------

    def get_config(self, key: str, default: str = "") -> str:
        with self._lock:
            return self._config_cache.get(key, default)

    def set_config(self, key: str, value: str):
        k_str, v_str = str(key), str(value)
        with self._lock:
            self._config.update_one(
                {"key": k_str},
                {"$set": {"key": k_str, "value": v_str, "updated_at": _utc_now_str()}},
                upsert=True,
            )
            self._config_cache[k_str] = v_str

    def get_all_config(self) -> Dict[str, str]:
        with self._lock:
            return dict(sorted(self._config_cache.items()))

    # ---------- KV JSON Store (Wordle stats/games/daily) ----------

    def load_kv_json(self, doc_key: str, default: Any = None) -> Any:
        with self._lock:
            doc = self._kv.find_one({"_id": str(doc_key)})
            if doc and "data" in doc:
                return copy.deepcopy(doc["data"])
            return copy.deepcopy(default) if default is not None else {}

    def save_kv_json(self, doc_key: str, data: Any) -> None:
        with self._lock:
            self._kv.update_one(
                {"_id": str(doc_key)},
                {"$set": {"data": copy.deepcopy(data), "updated_at": _utc_now_str()}},
                upsert=True,
            )

    # ---------- Admins ----------

    def add_admin(self, target_id: int, target_type: str = "user", added_by: int = 0):
        with self._lock:
            self._admins.update_one(
                {"target_id": int(target_id), "target_type": target_type},
                {
                    "$set": {
                        "target_id": int(target_id),
                        "target_type": target_type,
                        "added_by": int(added_by),
                        "added_at": _utc_now_str(),
                    }
                },
                upsert=True,
            )

    def remove_admin(self, target_id: int, target_type: str = "user") -> bool:
        with self._lock:
            res = self._admins.delete_one({"target_id": int(target_id), "target_type": target_type})
            return res.deleted_count > 0

    def get_admins(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [_strip_id(d) for d in self._admins.find({})]

    def is_db_admin(self, user_id: int, role_ids: List[int] = None) -> bool:
        with self._lock:
            if self._admins.find_one({"target_id": int(user_id), "target_type": "user"}):
                return True
            if role_ids:
                r_ids = [int(r) for r in role_ids]
                if self._admins.find_one({"target_type": "role", "target_id": {"$in": r_ids}}):
                    return True
            return False

    # ---------- Audit Logs ----------

    def log_audit(self, actor_id: int, action: str, details: str = ""):
        with self._lock:
            self._audit.insert_one(
                {
                    "id": self._next_seq("audit_logs"),
                    "actor_id": int(actor_id),
                    "action": action,
                    "details": details,
                    "created_at": _utc_now_str(),
                }
            )

    def get_audit_logs(self, limit: int = 15) -> List[Dict[str, Any]]:
        with self._lock:
            docs = self._audit.find({}).sort("id", DESCENDING).limit(int(limit))
            return [_strip_id(d) for d in docs]

    # ---------- Players, Game Stats & History ----------

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
        now_s = _utc_now_str()

        with self._lock:
            # Ensure player doc exists
            existing = self._players.find_one({"user_id": uid})
            if not existing:
                player_doc = {
                    "user_id": uid,
                    "username": username or "",
                    "points": int(points_earned),
                    "games_played": 1,
                    "wins": is_win,
                    "losses": is_loss,
                    "draws": is_draw,
                    "best_score": int(score),
                    "best_reaction_ms": reaction_ms,
                    "total_reaction_ms": int(reaction_ms) if reaction_ms is not None else 0,
                    "reaction_count": 1 if reaction_ms is not None else 0,
                    "updated_at": now_s,
                }
                self._players.insert_one(player_doc)
                new_pts = player_doc["points"]
            else:
                new_pts = int(existing.get("points", 0)) + int(points_earned)
                new_best_score = max(int(existing.get("best_score", 0)), int(score))
                cur_best_react = existing.get("best_reaction_ms")
                if reaction_ms is not None and (cur_best_react is None or reaction_ms < cur_best_react):
                    new_best_react = reaction_ms
                else:
                    new_best_react = cur_best_react
                update_fields = {
                    "points": new_pts,
                    "games_played": int(existing.get("games_played", 0)) + 1,
                    "wins": int(existing.get("wins", 0)) + is_win,
                    "losses": int(existing.get("losses", 0)) + is_loss,
                    "draws": int(existing.get("draws", 0)) + is_draw,
                    "best_score": new_best_score,
                    "best_reaction_ms": new_best_react,
                    "total_reaction_ms": int(existing.get("total_reaction_ms", 0)) + (int(reaction_ms) if reaction_ms is not None else 0),
                    "reaction_count": int(existing.get("reaction_count", 0)) + (1 if reaction_ms is not None else 0),
                    "updated_at": now_s,
                }
                if username:
                    update_fields["username"] = username
                self._players.update_one({"user_id": uid}, {"$set": update_fields})

            # Upsert per-game stats
            gs = self._game_stats.find_one({"user_id": uid, "game_name": game_name})
            if not gs:
                self._game_stats.insert_one(
                    {
                        "user_id": uid,
                        "game_name": game_name,
                        "played": 1,
                        "wins": is_win,
                        "losses": is_loss,
                        "draws": is_draw,
                        "best_score": int(score),
                        "best_reaction_ms": reaction_ms,
                        "last_played_at": now_s,
                    }
                )
            else:
                gs_best_react = gs.get("best_reaction_ms")
                if reaction_ms is not None and (gs_best_react is None or reaction_ms < gs_best_react):
                    new_gs_react = reaction_ms
                else:
                    new_gs_react = gs_best_react
                self._game_stats.update_one(
                    {"user_id": uid, "game_name": game_name},
                    {
                        "$set": {
                            "played": int(gs.get("played", 0)) + 1,
                            "wins": int(gs.get("wins", 0)) + is_win,
                            "losses": int(gs.get("losses", 0)) + is_loss,
                            "draws": int(gs.get("draws", 0)) + is_draw,
                            "best_score": max(int(gs.get("best_score", 0)), int(score)),
                            "best_reaction_ms": new_gs_react,
                            "last_played_at": now_s,
                        }
                    },
                )

            # Append match history
            self._game_history.insert_one(
                {
                    "id": self._next_seq("game_history"),
                    "user_id": uid,
                    "game_name": game_name,
                    "mode": mode,
                    "result": result,
                    "score": int(score),
                    "points_earned": int(points_earned),
                    "attempts": int(attempts),
                    "duration_sec": float(duration_sec),
                    "reaction_ms": reaction_ms,
                    "played_at": now_ts,
                }
            )
            return int(new_pts)

    def get_player_profile(self, user_id: int) -> Dict[str, Any]:
        uid = int(user_id)
        with self._lock:
            p = self._players.find_one({"user_id": uid})
            g_docs = list(self._game_stats.find({"user_id": uid}).sort([("played", DESCENDING), ("wins", DESCENDING)]))
            g_rows = [_strip_id(d) for d in g_docs]
            games = {r["game_name"]: r for r in g_rows}

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

            gp = int(p.get("games_played", 0))
            wins = int(p.get("wins", 0))
            losses = int(p.get("losses", 0))
            draws = int(p.get("draws", 0))
            win_rate = round((wins / gp) * 100, 1) if gp > 0 else 0.0
            fav_game = g_rows[0]["game_name"] if g_rows else "None yet"
            rcount = int(p.get("reaction_count") or 0)
            avg_react = int(p.get("total_reaction_ms", 0) / rcount) if rcount > 0 else None

            return {
                "user_id": uid,
                "username": p.get("username") or "",
                "points": int(p.get("points", 0)),
                "games_played": gp,
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "win_rate": win_rate,
                "best_score": int(p.get("best_score", 0)),
                "best_reaction_ms": p.get("best_reaction_ms"),
                "avg_reaction_ms": avg_react,
                "favourite_game": fav_game,
                "game_stats": games,
            }

    def get_player_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            docs = self._game_history.find({"user_id": int(user_id)}).sort("played_at", DESCENDING).limit(int(limit))
            return [_strip_id(d) for d in docs]

    def get_leaderboard(
        self,
        scope: str = "overall",
        game_name: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            if scope == "weekly":
                cutoff = int(time.time()) - (7 * 86400)
                agg: Dict[int, Dict[str, Any]] = {}
                for h in self._game_history.find({"played_at": {"$gte": cutoff}}):
                    uid = int(h["user_id"])
                    entry = agg.setdefault(
                        uid,
                        {"user_id": uid, "username": "", "points": 0, "games_played": 0, "wins": 0, "best_score": 0},
                    )
                    entry["points"] += int(h.get("points_earned", 0))
                    entry["games_played"] += 1
                    if h.get("result") == "win":
                        entry["wins"] += 1
                    entry["best_score"] = max(entry["best_score"], int(h.get("score", 0)))
                if agg:
                    for p in self._players.find({"user_id": {"$in": list(agg.keys())}}, {"user_id": 1, "username": 1}):
                        agg[int(p["user_id"])]["username"] = p.get("username") or ""
                rows = sorted(agg.values(), key=lambda x: (-x["points"], -x["wins"]))
                return rows[: int(limit)]

            if scope == "game" and game_name:
                target = game_name.strip().lower()
                matched = [
                    _strip_id(d)
                    for d in self._game_stats.find({"played": {"$gt": 0}})
                    if str(d.get("game_name", "")).lower() == target
                ]
                uids = [int(m["user_id"]) for m in matched]
                pmap = {
                    int(p["user_id"]): p
                    for p in self._players.find({"user_id": {"$in": uids}}, {"user_id": 1, "username": 1, "points": 1})
                } if uids else {}
                out = []
                for gs in matched:
                    p = pmap.get(int(gs["user_id"]), {})
                    out.append(
                        {
                            "user_id": int(gs["user_id"]),
                            "username": p.get("username") or "",
                            "wins": int(gs.get("wins", 0)),
                            "games_played": int(gs.get("played", 0)),
                            "best_score": int(gs.get("best_score", 0)),
                            "best_reaction_ms": gs.get("best_reaction_ms"),
                            "points": int(p.get("points", 0)),
                        }
                    )
                out.sort(key=lambda x: (-x["wins"], -x["best_score"], x["games_played"]))
                return out[: int(limit)]

            docs = (
                self._players.find({"$or": [{"games_played": {"$gt": 0}}, {"points": {"$gt": 0}}]})
                .sort([("points", DESCENDING), ("wins", DESCENDING), ("best_score", DESCENDING)])
                .limit(int(limit))
            )
            return [
                {
                    "user_id": int(d["user_id"]),
                    "username": d.get("username") or "",
                    "points": int(d.get("points", 0)),
                    "games_played": int(d.get("games_played", 0)),
                    "wins": int(d.get("wins", 0)),
                    "losses": int(d.get("losses", 0)),
                    "draws": int(d.get("draws", 0)),
                    "best_score": int(d.get("best_score", 0)),
                    "best_reaction_ms": d.get("best_reaction_ms"),
                }
                for d in docs
            ]

    def wipe_player_stats(self, user_id: int):
        uid = int(user_id)
        with self._lock:
            self._players.delete_many({"user_id": uid})
            self._game_stats.delete_many({"user_id": uid})
            self._game_history.delete_many({"user_id": uid})

    def reset_player_stats(self, user_id: int) -> None:
        self.wipe_player_stats(user_id)

    def adjust_player_points(self, user_id: int, new_points: int, username: str = "") -> int:
        uid = int(user_id)
        pts = max(0, int(new_points))
        now_s = _utc_now_str()
        with self._lock:
            existing = self._players.find_one({"user_id": uid})
            if not existing:
                self._players.insert_one(
                    {
                        "user_id": uid,
                        "username": username or "",
                        "points": pts,
                        "games_played": 0,
                        "wins": 0,
                        "losses": 0,
                        "draws": 0,
                        "best_score": 0,
                        "best_reaction_ms": None,
                        "total_reaction_ms": 0,
                        "reaction_count": 0,
                        "updated_at": now_s,
                    }
                )
            else:
                self._players.update_one(
                    {"user_id": uid},
                    {"$set": {"points": pts, "updated_at": now_s}},
                )
            return pts

    # ---------- Events ----------

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
        repeat_days: int = 0,
        announce_enabled: int = 1,
    ) -> Dict[str, Any]:
        utc_iso = start_time_utc.astimezone(timezone.utc).isoformat()
        rep = max(0, min(365, int(repeat_days or 0)))
        ann = 1 if int(announce_enabled) else 0
        now_s = _utc_now_str()
        doc = {
            "id": event_id,
            "name": name.strip(),
            "description": description.strip(),
            "start_time_utc": utc_iso,
            "duration_minutes": int(duration_minutes),
            "channel_id": int(channel_id),
            "creator_id": int(creator_id),
            "reminder_minutes": int(reminder_minutes),
            "reminder_sent": 0,
            "repeat_days": rep,
            "announce_enabled": ann,
            "status": "scheduled",
            "created_at": now_s,
            "updated_at": now_s,
        }
        with self._lock:
            self._events.insert_one(doc)
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
        repeat_days: Optional[int] = None,
        announce_enabled: Optional[int] = None,
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
        new_rep = max(0, min(365, int(repeat_days))) if repeat_days is not None else int(ev.get("repeat_days", 0) or 0)
        new_ann = (
            (1 if int(announce_enabled) else 0)
            if announce_enabled is not None
            else int(ev.get("announce_enabled", 1) if ev.get("announce_enabled") is not None else 1)
        )

        reminder_sent = ev["reminder_sent"]
        if start_time_utc is not None or reminder_minutes is not None:
            dt_check = datetime.fromisoformat(new_utc)
            if dt_check > datetime.now(timezone.utc):
                reminder_sent = 0

        with self._lock:
            self._events.update_one(
                {"id": ev["id"]},
                {
                    "$set": {
                        "name": new_name,
                        "description": new_desc,
                        "start_time_utc": new_utc,
                        "duration_minutes": new_dur,
                        "channel_id": new_chan,
                        "reminder_minutes": new_rem,
                        "reminder_sent": reminder_sent,
                        "repeat_days": new_rep,
                        "announce_enabled": new_ann,
                        "updated_at": _utc_now_str(),
                    }
                },
            )
        return self.get_event(ev["id"])

    def cancel_or_delete_event(self, event_id: str, delete_permanently: bool = False) -> Optional[Dict[str, Any]]:
        ev = self.get_event(event_id)
        if not ev:
            return None
        with self._lock:
            if delete_permanently:
                self._events.delete_one({"id": ev["id"]})
            else:
                self._events.update_one(
                    {"id": ev["id"]},
                    {"$set": {"status": "cancelled", "reminder_sent": 1, "updated_at": _utc_now_str()}},
                )
        return ev

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        target = event_id.strip().lower()
        with self._lock:
            doc = self._events.find_one({"id": event_id.strip()})
            if doc:
                return _strip_id(doc)
            # Case-insensitive fallback
            for d in self._events.find({}):
                if str(d.get("id", "")).lower() == target:
                    return _strip_id(d)
            return None

    def get_upcoming_events(self, include_cancelled: bool = False) -> List[Dict[str, Any]]:
        now_iso = datetime.now(timezone.utc).isoformat()
        query: Dict[str, Any] = {"start_time_utc": {"$gte": now_iso}}
        if not include_cancelled:
            query["status"] = "scheduled"
        with self._lock:
            docs = self._events.find(query).sort("start_time_utc", ASCENDING)
            return [_strip_id(d) for d in docs]

    def get_due_reminders(self) -> List[Dict[str, Any]]:
        now_utc = datetime.now(timezone.utc)
        due = []
        with self._lock:
            for raw in self._events.find({"status": "scheduled"}):
                ev = _strip_id(raw)
                start_dt = datetime.fromisoformat(ev["start_time_utc"])
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                rep_days = int(ev.get("repeat_days") or 0)
                ann_on = int(ev.get("announce_enabled") if ev.get("announce_enabled") is not None else 1)
                rem_sent = int(ev.get("reminder_sent") or 0)
                rem_dt = start_dt - timedelta(minutes=int(ev.get("reminder_minutes", 10) or 0))

                if now_utc >= start_dt:
                    if rep_days > 0:
                        next_dt = start_dt
                        while next_dt <= now_utc:
                            next_dt = next_dt + timedelta(days=rep_days)
                        self._events.update_one(
                            {"id": ev["id"]},
                            {
                                "$set": {
                                    "start_time_utc": next_dt.astimezone(timezone.utc).isoformat(),
                                    "reminder_sent": 0,
                                    "updated_at": _utc_now_str(),
                                }
                            },
                        )
                    else:
                        self._events.update_one(
                            {"id": ev["id"]},
                            {"$set": {"reminder_sent": 1, "status": "completed", "updated_at": _utc_now_str()}},
                        )
                elif rem_sent == 0 and int(ev.get("reminder_minutes", 10) or 0) > 0 and now_utc >= rem_dt:
                    if ann_on == 1:
                        due.append(ev)
                    else:
                        self._events.update_one(
                            {"id": ev["id"]},
                            {"$set": {"reminder_sent": 1, "updated_at": _utc_now_str()}},
                        )
        return due

    def set_event_announce(self, event_id: str, enabled: bool) -> Optional[Dict[str, Any]]:
        return self.update_event(event_id, announce_enabled=(1 if enabled else 0))

    def set_event_repeat(self, event_id: str, repeat_days: int) -> Optional[Dict[str, Any]]:
        return self.update_event(event_id, repeat_days=max(0, min(365, int(repeat_days))))

    def mark_reminder_sent(self, event_id: str):
        with self._lock:
            self._events.update_one(
                {"id": event_id},
                {"$set": {"reminder_sent": 1, "updated_at": _utc_now_str()}},
            )

    # ---------- Rules ----------

    def get_rules_list(self) -> List[Dict[str, Any]]:
        with self._lock:
            docs = self._rules.find({}).sort([("rule_number", ASCENDING), ("id", ASCENDING)])
            return [_strip_id(d) for d in docs]

    def get_formatted_rules(self) -> str:
        rules = self.get_rules_list()
        if not rules:
            return "No rules have been configured yet."
        return "\n".join(f"**{r['rule_number']}.** {r['content']}" for r in rules)

    def add_rule(self, content: str, actor_id: int = 0) -> int:
        with self._lock:
            existing = self.get_rules_list()
            next_num = max((int(r["rule_number"]) for r in existing), default=0) + 1
            self._rules.insert_one(
                {
                    "id": self._next_seq("rules"),
                    "rule_number": next_num,
                    "content": content.strip(),
                    "updated_by": int(actor_id),
                    "updated_at": _utc_now_str(),
                }
            )
            return next_num

    def edit_rule(self, rule_number: int, content: str, actor_id: int = 0) -> bool:
        with self._lock:
            res = self._rules.update_one(
                {"rule_number": int(rule_number)},
                {"$set": {"content": content.strip(), "updated_by": int(actor_id), "updated_at": _utc_now_str()}},
            )
            return res.matched_count > 0

    def remove_rule(self, rule_number: int) -> bool:
        with self._lock:
            res = self._rules.delete_one({"rule_number": int(rule_number)})
            if res.deleted_count == 0:
                return False
            remaining = list(self._rules.find({}).sort([("rule_number", ASCENDING), ("id", ASCENDING)]))
            for idx, doc in enumerate(remaining, 1):
                self._rules.update_one({"_id": doc["_id"]}, {"$set": {"rule_number": idx}})
            return True

    def replace_all_rules(self, raw_text: str, actor_id: int = 0):
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        now_s = _utc_now_str()
        with self._lock:
            self._rules.delete_many({})
            for idx, line in enumerate(lines, 1):
                clean = line
                prefix = f"**{idx}.**"
                if clean.startswith(prefix):
                    clean = clean[len(prefix):].strip()
                elif clean.startswith(f"{idx}."):
                    clean = clean[len(f"{idx}."):].strip()
                self._rules.insert_one(
                    {
                        "id": self._next_seq("rules"),
                        "rule_number": idx,
                        "content": clean,
                        "updated_by": int(actor_id),
                        "updated_at": now_s,
                    }
                )

    # ---------- Knowledge Base ----------

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
        now_s = _utc_now_str()
        with self._lock:
            existing = self._knowledge.find_one({"key": clean_key})
            if not existing:
                doc = {
                    "id": self._next_seq("knowledge_base"),
                    "key": clean_key,
                    "title": title.strip(),
                    "category": category.strip(),
                    "content": content.strip(),
                    "keywords": keywords.strip(),
                    "updated_by": int(actor_id),
                    "updated_at": now_s,
                }
                self._knowledge.insert_one(doc)
                return _strip_id(doc)
            self._knowledge.update_one(
                {"key": clean_key},
                {
                    "$set": {
                        "title": title.strip(),
                        "category": category.strip(),
                        "content": content.strip(),
                        "keywords": keywords.strip(),
                        "updated_by": int(actor_id),
                        "updated_at": now_s,
                    }
                },
            )
            return _strip_id(self._knowledge.find_one({"key": clean_key}))

    def remove_knowledge(self, key: str) -> bool:
        clean_key = key.strip().lower().replace(" ", "_")
        with self._lock:
            res = self._knowledge.delete_one({"key": clean_key})
            return res.deleted_count > 0

    def list_knowledge(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            docs = [_strip_id(d) for d in self._knowledge.find({})]
            if category:
                target = category.strip().lower()
                docs = [d for d in docs if str(d.get("category", "")).lower() == target]
            docs.sort(key=lambda d: (str(d.get("category", "")), str(d.get("title", ""))))
            return docs

    def get_knowledge(self, key: str) -> Optional[Dict[str, Any]]:
        clean_key = key.strip().lower().replace(" ", "_")
        with self._lock:
            return _strip_id(self._knowledge.find_one({"key": clean_key}))

    # ---------- Backup ----------

    def create_backup(self) -> str:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(BACKUP_DIR, f"haven_mongo_backup_{stamp}.json")
        with self._lock:
            dump = {
                "exported_at_utc": datetime.now(timezone.utc).isoformat(),
                "database": self._db_name,
                "collections": {
                    "players": [_strip_id(d) for d in self._players.find({})],
                    "game_stats": [_strip_id(d) for d in self._game_stats.find({})],
                    "game_history": [_strip_id(d) for d in self._game_history.find({})],
                    "events": [_strip_id(d) for d in self._events.find({})],
                    "rules": [_strip_id(d) for d in self._rules.find({})],
                    "knowledge_base": [_strip_id(d) for d in self._knowledge.find({})],
                    "server_config": [_strip_id(d) for d in self._config.find({})],
                    "admins": [_strip_id(d) for d in self._admins.find({})],
                    "audit_logs": [_strip_id(d) for d in self._audit.find({})],
                    "kv_store": [
                        {"key": d.get("_id"), "data": d.get("data")}
                        for d in self._kv.find({})
                    ],
                },
            }
            tmp_path = f"{dest}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(dump, f, indent=2, ensure_ascii=False, default=str)
            os.replace(tmp_path, dest)
        return dest
