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


# ROF Branding & Dark Gaming Theme
BRAND_NAME = "ROF — Rise of Farkers"
BRAND_SHORT = "ROF"
BRAND_FOOTER = "ROF Gaming & Alliance System"

class ROFColors:
    PRIMARY = 0x2B2D31      # Sleek dark gaming slate
    ARENA = 0x5865F2        # Vibrant cyber blurple
    ACCENT = 0xE63946       # ROF crimson
    SUCCESS = 0x2ECC71      # Emerald win
    WARNING = 0xF39C12      # Amber alert / wait
    ERROR = 0xED4245        # Clean danger red
    GOLD = 0xF1C40F         # Leaderboard / championship gold
    INFO = 0x3498DB         # Information blue

RANKS = [
    (0, "Bronze", "🥉"),
    (100, "Silver", "🥈"),
    (250, "Gold", "🥇"),
    (500, "Diamond", "💎"),
    (1000, "ROF Legend", "👑"),
]

def get_rank(points: int):
    current = (RANKS[0][1], RANKS[0][2])
    for threshold, name, emoji in RANKS:
        if points >= threshold:
            current = (name, emoji)
    return current
