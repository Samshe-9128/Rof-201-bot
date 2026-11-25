# core/config.py
import os
from datetime import datetime, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = (os.getenv("DATA_DIR") or os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or BASE_DIR).strip() or BASE_DIR
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception:
    DATA_DIR = BASE_DIR


def _safe_int(env_key: str, default: int = 0) -> int:
    val = os.getenv(env_key, "")
    if val is None or str(val).strip() == "":
        return default
    try:
        return int(str(val).strip())
    except ValueError:
        return default


def _safe_float(env_key: str, default: float = 0.0) -> float:
    val = os.getenv(env_key, "")
    if val is None or str(val).strip() == "":
        return default
    try:
        return float(str(val).strip())
    except ValueError:
        return default


TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = _safe_int("GUILD_ID", 0)
OWNER_ID = _safe_int("OWNER_ID", 0)
EVENT_CHANNEL_ID = _safe_int("EVENT_CHANNEL_ID", 0)
WELCOME_CHANNEL_ID = _safe_int("WELCOME_CHANNEL_ID", 0)
RULES_CHANNEL_ID = _safe_int("RULES_CHANNEL_ID", 0)
DEFAULT_TZ_OFFSET = _safe_float("SERVER_TZ_OFFSET", -2.0)
MONGO_URI = os.getenv("MONGO_URI", "").strip()
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "haven_bot").strip() or "haven_bot"
AUTO_SYNC_COMMANDS = os.getenv("AUTO_SYNC_COMMANDS", "true").strip().lower() not in ("0", "false", "no")

# Timezones: Game Time (default UTC-02:00) and India Time (Asia/Kolkata, UTC+05:30)
GAME_TZ = timezone(timedelta(hours=DEFAULT_TZ_OFFSET))
if ZoneInfo is not None:
    try:
        INDIA_TZ = ZoneInfo("Asia/Kolkata")
    except Exception:
        INDIA_TZ = timezone(timedelta(hours=5, minutes=30), name="IST")
else:
    INDIA_TZ = timezone(timedelta(hours=5, minutes=30), name="IST")


def get_game_tz(offset_hours: float = None) -> timezone:
    if offset_hours is None:
        offset_hours = DEFAULT_TZ_OFFSET
    return timezone(timedelta(hours=float(offset_hours)))


def format_tz_label(offset_hours: float = None) -> str:
    """Format a UTC offset float cleanly, e.g. -2.0 -> 'UTC-02:00', 5.5 -> 'UTC+05:30'."""
    off_val = DEFAULT_TZ_OFFSET if offset_hours is None else float(offset_hours)
    sign = "+" if off_val >= 0 else "-"
    abs_val = abs(off_val)
    hrs = int(abs_val)
    mins = int(round((abs_val - hrs) * 60))
    return f"UTC{sign}{hrs:02d}:{mins:02d}"


def format_dual_timestamps(dt: datetime, offset_hours: float = None) -> dict:
    """Convert any timezone-aware datetime to Game Time (UTC-2), India Time (Asia/Kolkata), and Discord epoch."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_game_tz(offset_hours))
    game_tz = get_game_tz(offset_hours)
    dt_game = dt.astimezone(game_tz)
    dt_india = dt.astimezone(INDIA_TZ)
    epoch = int(dt.timestamp())

    sign = "+" if (offset_hours if offset_hours is not None else DEFAULT_TZ_OFFSET) >= 0 else ""
    off_val = offset_hours if offset_hours is not None else DEFAULT_TZ_OFFSET
    off_str = f"UTC{sign}{int(off_val)}" if float(off_val).is_integer() else f"UTC{sign}{off_val}"

    return {
        "date_str": dt_game.strftime("%d %B %Y"),
        "short_date": dt_game.strftime("%d %B"),
        "game_time": f"{dt_game.strftime('%H:%M')} ({off_str})",
        "game_time_short": dt_game.strftime("%H:%M"),
        "india_time": f"{dt_india.strftime('%H:%M')} IST ({dt_india.strftime('%I:%M %p')})",
        "india_time_short": dt_india.strftime("%H:%M"),
        "discord_full": f"<t:{epoch}:F>",
        "discord_short": f"<t:{epoch}:t>",
        "discord_relative": f"<t:{epoch}:R>",
        "epoch": epoch,
    }


# HAV (Haven) Branding & Dark Gaming Theme
BRAND_NAME = "Haven"
BRAND_SHORT = "HAV"
BRAND_FOOTER = "HAV Gaming & Alliance System"


class HAVColors:
    PRIMARY = 0x2B2D31      # Sleek dark gaming slate
    ARENA = 0x5865F2        # Vibrant cyber blurple
    ACCENT = 0xE63946       # HAV crimson
    SUCCESS = 0x2ECC71      # Emerald win
    WARNING = 0xF39C12      # Amber alert / wait
    ERROR = 0xED4245        # Clean danger red
    GOLD = 0xF1C40F         # Leaderboard / championship gold
    INFO = 0x3498DB         # Information blue


# Rank Ladder (HAV Theme)
RANK_LADDER = [
    (0, "Recruit", "🪨"),
    (100, "Scout", "🛡️"),
    (300, "Enforcer", "⚔️"),
    (600, "Vanguard", "🔥"),
    (1000, "Captain", "🎖️"),
    (1500, "Commander", "👑"),
    (2500, "HAV Legend", "🏆"),
]


def get_rank_info(points: int) -> tuple:
    current = RANK_LADDER[0]
    for threshold, name, icon in RANK_LADDER:
        if points >= threshold:
            current = (threshold, name, icon)
    return current
