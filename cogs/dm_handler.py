import asyncio
import time
# cogs/dm_handler.py
import difflib
import json
import re
import traceback
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from core.config import DEFAULT_TZ_OFFSET, HAVColors, format_dual_timestamps, format_tz_label
from core.database import db
from core.permissions import ensure_admin
from core.chat_input import chat_input_manager
from core.owner_stealth import owner_stealth
from core.ui import PaginatedEmbedView, get_alliance_short, hav_embed, safe_reply_error

# Friendly, human-style instructions for every game on Haven Bot
GAME_EXPLANATIONS = {
    "codebreaker": (
        "Start or join a **Codebreaker** room with `/games` or `/codebreaker`, then guess a 4-digit secret code "
        "(all unique digits, no leading zero). After each guess I'll give you clues: 🟢 = right digit in the right spot, "
        "🟡 = right digit in the wrong spot. First player to crack it wins!"
    ),
    "wordle": (
        "Run `/wordle` (Daily or Practice) in any server channel or DM, then just type your 5-letter guesses right in chat! "
        "🟩 = right letter & spot, 🟨 = right letter in the wrong spot, ⬛ = not in the word."
    ),
    "quickdraw": (
        "In **Reaction Race** (`/quickdraw` or `/games`), wait for **WAIT...** to flip to green **READY!**, "
        "then click as fast as you can. Clicking early counts as a False Start!"
    ),
    "scramble": (
        "In **Word Scramble** (`/games`), unscramble the mixed-up letters before the timer runs out — "
        "you can also host a multiplayer **Word Race** room against alliance mates!"
    ),
    "memory": (
        "Use `/memory` or `/games` to play **Memory Challenge** — watch the color sequence (`🔴 🔵 🟢 🟡 🟣 🟠`) "
        "and repeat it back as it grows up to 8 steps!"
    ),
    "math": (
        "In **Quick Math** (`/games`), solve as many arithmetic questions as you can in 60 seconds, "
        "or challenge teammates in a **Quick Math Battle** for speed bonuses!"
    ),
    "trivia": (
        "Play solo **Trivia** or multiplayer **Trivia Battle** via `/games` across 8 categories "
        "(Science, History, Geography, Gaming, Movies, Sports, Tech, General Knowledge)."
    ),
    "rps": (
        "Play **Rock Paper Scissors** against me or in a 2-player Best of 3 / Best of 5 room using `/games`."
    ),
    "number": (
        "In **Number Guessing** (`/games`), pick a difficulty range and use the HIGHER ⬆️ and LOWER ⬇️ hints to find the secret number."
    ),
    "emoji": (
        "In **Emoji Guessing** (`/games`), figure out the movie, game, animal, food, or phrase shown by the emojis — solo or multiplayer!"
    ),
    "higherlower": (
        "Use `/higherlower` or `/games` and predict whether the next number (1–100) will be higher or lower. "
        "Cash out anytime to bank your streak!"
    ),
    "treasure": (
        "Use `/treasure` or `/games` to uncover 7 hidden gems on a 3x3 grid while dodging 2 bombs. "
        "Cash out anytime or go for a Full Clear bonus!"
    ),
    "tictactoe": (
        "Use `/tictactoe` or `/games` to challenge another member to a quick 3x3 **Tic-Tac-Toe** duel."
    ),
    "closest": (
        "Join a **Closest Wins** room via `/games` (2–10 players) — pick a secret number from 1–100 in 20 seconds, and whoever is closest to the target wins!"
    ),
    "connect4": (
        "Use `/connect4` or `/games` to challenge a teammate to a classic 7x6 **Connect 4** match."
    ),
}

# Casual aliases so players can type "c4", "ttt", "reaction", "4 digit", etc.
GAME_ALIASES = {
    "codebreaker": ("codebreaker", "code breaker", "4 digit", "four digit", "mastermind"),
    "wordle": ("wordle", "wordel", "5 letter"),
    "quickdraw": ("quickdraw", "quick draw", "reaction", "reaction race", "reaction speed"),
    "scramble": ("scramble", "word scramble", "word race", "unscramble"),
    "memory": ("memory", "memory challenge", "color sequence"),
    "math": ("math", "quick math", "math battle", "arithmetic"),
    "trivia": ("trivia", "quiz", "trivia battle"),
    "rps": ("rps", "rock paper scissors", "rock paper"),
    "number": ("number guess", "number guessing", "guess number", "guess the number"),
    "emoji": ("emoji", "emoji guess", "emoji guessing"),
    "higherlower": ("higherlower", "higher lower", "higher or lower", "hi lo", "hilo"),
    "treasure": ("treasure", "treasure hunt", "gems", "bombs"),
    "tictactoe": ("tictactoe", "tic tac toe", "ttt", "x and o"),
    "closest": ("closest", "closest wins"),
    "connect4": ("connect4", "connect 4", "connect four", "c4"),
}

_EVENT_NAME_STOPWORDS = {
    "the", "an", "a", "of", "and", "or", "for", "in", "on", "at", "to",
    "next", "upcoming", "new",
}

_SECURITY_RE = re.compile(
    r"\b(?:"
    r"make\s+me\s+admin|give\s+me\s+admin|grant\s+me\s+admin|grant\s+permission|"
    r"ignore\s+(?:all\s+)?(?:previous|the\s+above)|forget\s+(?:previous|all)|"
    r"delete\s+all\s+(?:events|data|rules)|"
    r"bypass\s+(?:permission|admin|security|authentication)"
    r")\b",
    re.IGNORECASE,
)

_CREATOR_RE = re.compile(
    r"\b(?:"
    r"who\s+(?:made|built|created|owns|coded|programmed)\s+(?:you|u)|"
    r"who\s+is\s+(?:your|ur)\s+(?:owner|creator|dev|developer)|"
    r"who\s+is\s+sam"
    r")\b",
    re.IGNORECASE,
)

_ABOUT_BOT_RE = re.compile(
    r"\b(?:"
    r"who\s+(?:are|r)\s+(?:you|u)|"
    r"(?:tell\s+me\s+)?about\s+(?:yourself|urself|ur\s+self|you|u)|"
    r"introduce\s+(?:yourself|urself)|"
    r"what\s+(?:are|r)\s+(?:you|u)|"
    r"what\s+(?:can|do)\s+(?:you|u)\s+do"
    r")\b",
    re.IGNORECASE,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_KB_STOP = {
    "how", "to", "what", "who", "can", "is", "are", "the", "a", "an",
    "for", "in", "on", "of", "do", "i", "my", "me", "tell", "please",
    "about", "hey", "hi", "explain", "info", "guide", "should", "and",
    "or", "you", "your", "from", "with",
}

# Lightweight 15-second TTL cache so MongoDB Atlas isn't hit on every chat message
_CACHE_TTL_SEC = 15.0
_events_cache: tuple[float, list[dict]] = (0.0, [])
_kb_cache: tuple[float, list[dict]] = (0.0, [])

def invalidate_assistant_caches() -> None:
    global _events_cache, _kb_cache
    _events_cache = (0.0, [])
    _kb_cache = (0.0, [])

def _get_cached_upcoming_events() -> list[dict]:
    global _events_cache
    now = time.monotonic()
    if now - _events_cache[0] < _CACHE_TTL_SEC:
        return _events_cache[1]
    try:
        evs = db.get_upcoming_events(include_cancelled=False) or []
    except Exception as e:
        print(f"[ASSISTANT] get_upcoming_events failed: {e}")
        evs = []
    _events_cache = (now, evs)
    return evs

def _get_cached_knowledge() -> list[dict]:
    global _kb_cache
    now = time.monotonic()
    if now - _kb_cache[0] < _CACHE_TTL_SEC:
        return _kb_cache[1]
    try:
        items = db.list_knowledge() or []
    except Exception as e:
        print(f"[ASSISTANT] list_knowledge failed: {e}")
        items = []
    _kb_cache = (now, items)
    return items

def _parse_iso_utc(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    s = str(raw_value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception as e:
        print(f"[ASSISTANT] invalid ISO datetime '{raw_value}': {e}")
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def _format_event(ev: dict, tz_off: float) -> str | None:
    try:
        name = (ev.get("name") or "").strip()
        if not name:
            return None
        dt = _parse_iso_utc(ev.get("start_time_utc"))
        if dt is None:
            return None
        try:
            dual = format_dual_timestamps(dt, tz_off)
        except Exception as e:
            print(f"[ASSISTANT] format_dual_timestamps failed for '{name}': {e}")
            return None
        desc = ev.get("description")
        desc_note = f"\n📝 *{desc}*" if desc else ""
        return (
            f"The next **{name}** is on **{dual['short_date']}** at **{dual['game_time_short']} game time** "
            f"(**{dual['india_time_short']} India time**, {dual['discord_relative']}).{desc_note}"
        )
    except Exception as e:
        print(f"[ASSISTANT] _format_event failed: {e}")
        return None

def _match_haven_game(q_low: str, tokens: set) -> tuple[str, str] | None:
    """Match any of Haven Bot's Discord games by name or casual alias."""
    for g_key, aliases in GAME_ALIASES.items():
        for alias in aliases:
            if " " in alias:
                if alias in q_low:
                    return (g_key, GAME_EXPLANATIONS[g_key])
            else:
                if alias in tokens:
                    return (g_key, GAME_EXPLANATIONS[g_key])
    return None

def answer_alliance_query(raw_query: str) -> tuple[str, str]:
    """
    Fast, friendly, read-only Haven Alliance Assistant.
    Instant zero-DB fast path for greetings, games, identity, & security;
    TTL-cached DB reads for event timings, rules, & custom /knowledge entries.
    """
    short = get_alliance_short()
    q = (raw_query or "").strip()
    q_low = q.lower()
    raw_tokens = _TOKEN_RE.findall(q_low)
    tokens = set(raw_tokens)

    # 1. Security guardrail (0ms local)
    if _SECURITY_RE.search(q_low):
        return (
            "🔒 Security Policy",
            "Nice try, haha — I'm read-only, so I can't grant admin permissions or delete anything. Only authorized admins can do that with slash commands.",
        )

    # 2. Casual greetings & small talk (0ms local)
    if len(raw_tokens) <= 2 and (tokens & {"hi", "hello", "hey", "yo", "hola", "sup"}):
        return (
            f"🛡️ {short} Bot",
            "Hey! Ask me about upcoming **event timings**, **how to play** any game on `/games`, or **alliance rules**!",
        )
    if len(raw_tokens) <= 5 and (tokens & {"thanks", "thank", "ty", "thx", "tysm"}):
        return (
            f"🛡️ {short} Bot",
            "Anytime! Ping me whenever you need an event time or game rules 💪",
        )
    if len(raw_tokens) <= 4 and any(p in q_low for p in ("good bot", "nice bot", "awesome bot", "great job")):
        return (
            f"🛡️ {short} Bot",
            f"Appreciate it! Always here to help **Haven ({short})**.",
        )
    if len(raw_tokens) <= 3 and (tokens & {"bye", "goodbye", "cya", "gn", "goodnight"}):
        return (
            f"👋 {short} Bot",
            "Catch you later! Check `/events` before you hop off so you don't miss anything.",
        )

    # 3. Bot identity & creator (0ms local)
    if _CREATOR_RE.search(q_low):
        return (
            "👑 Creator — Sam (Server 201)",
            f"**Sam** from **Server 201** built me for **Haven ({short})**! If you spot a bug or want a new feature, just ping Sam or use the Report Bug button.",
        )
    if _ABOUT_BOT_RE.search(q_low):
        return (
            f"🛡️ {short} Bot",
            f"Hey! I'm **{short} Bot**, built by **Sam** for **Haven ({short})** on **Server 201**.\n"
            "I can tell you upcoming **event timings** (Game Time + IST), explain **how to play any game** on `/games`, and share **alliance rules** (`/rules view`)!",
        )
    if any(p in q_low for p in ("which server", "what server", "our server", "server 201")):
        return (
            f"🌐 Haven ({short}) — Server 201",
            f"We're **Haven ({short})** on **Server 201**!",
        )

    # 4. Event scheduling permissions (0ms local)
    if ("event" in q_low or "schedule" in q_low) and any(
        w in q_low
        for w in ("can i", "how do i create", "who can", "schedule an", "make an", "create an", "modify", "add an")
    ):
        return (
            "📅 Event Permissions",
            "Only authorized alliance admins (and **Sam**) can create or edit events, but anyone can check upcoming times anytime using `/events`!",
        )

    # 5. How to play a specific Haven Bot game (0ms local)
    matched_game = _match_haven_game(q_low, tokens)
    if matched_game:
        g_key, g_exp = matched_game
        return (f"🎮 How to Play — {g_key.title()}", g_exp)

    # 6. General games list (0ms local)
    if any(w in tokens for w in ("games", "game", "play", "arena", "minigame", "minigames")):
        return (
            f"🎮 {short} Gaming Arena",
            f"Run `/games` to open the **{short} Gaming Arena**! You can play **12 solo games** "
            "(Wordle Daily & Practice, Higher or Lower, Treasure Hunt, Word Scramble, Memory Challenge, Quick Math, Reaction Speed Test, Trivia, RPS, Number Guessing, Emoji Guessing) "
            "or **multiplayer rooms** (Tic-Tac-Toe, Connect 4, Codebreaker, Closest Wins, Reaction Race, Word Race, Quick Math Battle, Trivia Battle, RPS, Emoji Guessing). "
            "Ask me *\"how to play Wordle\"* or any game name for quick rules!",
        )

    # 7. Alliance rules
    if any(w in tokens for w in ("rule", "rules")):
        try:
            rules_text = db.get_formatted_rules()
        except Exception as e:
            print(f"[ASSISTANT] get_formatted_rules failed: {e}")
            rules_text = "Alliance rules are currently unavailable right now — try `/rules view` in a moment."
        return (f"📜 {short} Alliance Rules", rules_text)

    # 8. Timezone & cached upcoming events
    try:
        tz_off = float(db.get_config("game_tz_offset", str(DEFAULT_TZ_OFFSET)))
    except Exception:
        tz_off = float(DEFAULT_TZ_OFFSET)

    # 9. Help / commands
    if len(tokens) <= 5 and (tokens & {"help", "commands", "command"}):
        tz_label = format_tz_label(tz_off)
        return (
            f"🛡️ {short} Bot Commands",
            f"Here's what you can use anytime:\n"
            f"• `/games` — Play all 22 solo & multiplayer games\n"
            f"• `/events` — Check upcoming alliance events in Game Time (`{tz_label}`) & India Time (`IST`)\n"
            "• `/rules view` — Read the Haven alliance rules\n"
            "• `/profile` & `/leaderboard` — Check your game stats & rankings\n"
            "• `/help` — Full command list",
        )

    upcoming = _get_cached_upcoming_events()

    # 10. Specific upcoming event by name
    for ev in upcoming:
        try:
            ev_name = (ev.get("name") or "").strip()
            if not ev_name:
                continue
            ev_name_low = ev_name.lower()
            ev_words = {
                w for w in _TOKEN_RE.findall(ev_name_low)
                if len(w) >= 3 and w not in _EVENT_NAME_STOPWORDS
            }
            if ev_name_low in q_low or (ev_words and any(w in tokens for w in ev_words)):
                rendered = _format_event(ev, tz_off)
                if rendered:
                    return (f"📅 Upcoming Event — {ev_name}", rendered)
        except Exception as e:
            print(f"[ASSISTANT] event name match failed: {e}")
            continue

    # 11. General upcoming events / timings
    if any(w in tokens for w in ("event", "events", "schedule", "upcoming", "timing", "timings", "surge", "brawl", "svs")):
        if not upcoming:
            return (
                f"📅 Upcoming {short} Events",
                "There are no upcoming events scheduled right now — check `/events` later for updates!",
            )
        lines = []
        for ev in upcoming[:5]:
            try:
                dt = _parse_iso_utc(ev.get("start_time_utc"))
                if not dt:
                    continue
                dual = format_dual_timestamps(dt, tz_off)
                lines.append(
                    f"• **{ev.get('name', '?')}** — {dual['short_date']} at "
                    f"**{dual['game_time_short']} game time** "
                    f"({dual['india_time_short']} IST · {dual['discord_relative']})"
                )
            except Exception:
                continue
        if not lines:
            return (
                f"📅 Upcoming {short} Events",
                "There are no upcoming events scheduled right now — check `/events` later!",
            )
        return (
            f"📅 Upcoming {short} Events",
            "Here are the next scheduled alliance events:\n" + "\n".join(lines),
        )

    # 12. Custom Knowledge Base entries (added/edited by admins via /knowledge)
    kb_items = _get_cached_knowledge()
    best_item = None
    best_score = 0.0
    q_meaningful = {t for t in tokens if t not in _KB_STOP} or tokens

    for item in kb_items:
        try:
            haystack = (
                f"{item.get('key', '')} {item.get('title', '')} "
                f"{item.get('category', '')} {item.get('keywords', '')}"
            ).lower()
            hay_tokens = set(_TOKEN_RE.findall(haystack))
            h_meaningful = {t for t in hay_tokens if t not in _KB_STOP} or hay_tokens
            overlap = len(q_meaningful & h_meaningful)
            seq_ratio = difflib.SequenceMatcher(
                None, q_low, (item.get("title") or "").lower()
            ).ratio()
            score = (overlap * 1.5) + seq_ratio
            if (item.get("key", "").lower() in q_low
                    or (item.get("title") or "").lower() in q_low):
                score += 3.0
            if score > best_score:
                best_score = score
                best_item = item
        except Exception:
            continue

    if best_item and best_score >= 2.0:
        return (
            f"📘 {best_item.get('title', '?')}",
            best_item.get("content", ""),
        )

    # 13. Clean, friendly fallback
    return (
        f"🤖 {short} Bot",
        "I mostly help with **event timings**, **how to play Haven Bot games**, and **alliance rules**! Try asking:\n"
        "• *\"When is the next event?\"* (or `/events`)\n"
        "• *\"How do I play Wordle?\"* / *\"How to play Codebreaker?\"* (or `/games`)\n"
        "• *\"What are the alliance rules?\"* (or `/rules view`)",
    )

async def knowledge_key_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    items = _get_cached_knowledge()
    q = (current or "").strip().lower()
    choices = []
    for item in items:
        key = item.get("key", "")
        title = item.get("title", key)
        if not q or q in key.lower() or q in title.lower():
            label = f"{key} — {title}"[:100]
            choices.append(app_commands.Choice(name=label, value=key))
        if len(choices) >= 25:
            break
    return choices

class KnowledgeModal(discord.ui.Modal):
    def __init__(self, existing: dict | None = None):
        super().__init__(title="Edit Knowledge Entry" if existing else "Add Alliance Knowledge")
        self.key_input = discord.ui.TextInput(
            placeholder="e.g., surge_timing",
            default=existing["key"] if existing else None,
            max_length=40,
            required=True,
        )
        self.title_input = discord.ui.TextInput(
            placeholder="e.g., Surge Event Info",
            default=existing["title"] if existing else None,
            max_length=80,
            required=True,
        )
        self.category_input = discord.ui.TextInput(
            placeholder="Events",
            default=existing["category"] if existing else None,
            max_length=30,
            required=True,
        )
        self.keywords_input = discord.ui.TextInput(
            placeholder="surge event timing reinforce",
            default=(existing.get("keywords") or "") if existing else None,
            max_length=120,
            required=False,
        )
        self.content_input = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            placeholder="Enter the approved alliance information...",
            default=existing["content"] if existing else None,
            max_length=1500,
            required=True,
        )
        self.add_item(discord.ui.Label(text="Unique Topic Key", component=self.key_input))
        self.add_item(discord.ui.Label(text="Title", component=self.title_input))
        self.add_item(discord.ui.Label(text="Category (FAQ, Guides, Events, Games)", component=self.category_input))
        self.add_item(discord.ui.Label(text="Search Keywords (space-separated)", component=self.keywords_input))
        self.add_item(discord.ui.Label(text="Approved Knowledge Content", component=self.content_input))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if not await ensure_admin(interaction):
                return

            saved = db.upsert_knowledge(
                key=self.key_input.value,
                title=self.title_input.value,
                category=self.category_input.value,
                content=self.content_input.value,
                keywords=self.keywords_input.value or "",
                actor_id=interaction.user.id,
            )
            invalidate_assistant_caches()

            try:
                db.log_audit(
                    interaction.user.id,
                    "knowledge_upsert",
                    f"Saved knowledge key '{saved['key']}'",
                )
            except Exception as e:
                print(f"[ASSISTANT] log_audit failed (upsert): {e}")

            embed = hav_embed(
                title=f"✅ KNOWLEDGE SAVED — {saved['title']}",
                description=(
                    f"**Key:** `{saved['key']}` | **Category:** `{saved['category']}`\n"
                    f"**Keywords:** `{saved['keywords'] or 'None'}`\n\n"
                    f"{saved['content']}"
                ),
                color=HAVColors.SUCCESS,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"[ASSISTANT] KnowledgeModal.on_submit failed: {type(e).__name__}: {e}")
            traceback.print_exc()
            await safe_reply_error(
                interaction,
                "⚠️ Could not save the knowledge entry. Please try again.",
            )

class DMHandler(commands.Cog):
    """Part 8: Haven Alliance Assistant (DMs + Configured Alliance Channels) and /knowledge management."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._assistant_raw_cache: str | None = None
        self._assistant_chan_set: set = set()
        self._mention_cooldowns: dict = {}

    def _is_assistant_channel(self, channel_id: int) -> bool:
        try:
            raw = db.get_config("assistant_channels", "[]")
            if raw != self._assistant_raw_cache:
                chan_list = json.loads(raw)
                self._assistant_chan_set = {int(x) for x in chan_list}
                self._assistant_raw_cache = raw
            return int(channel_id) in self._assistant_chan_set
        except Exception as e:
            print(f"[ASSISTANT] _is_assistant_channel failed: {e}")
            return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.content or not message.content.strip():
            return
        if message.content.startswith(("/", "!")):
            return
        if (
            owner_stealth.was_handled(message.id)
            or chat_input_manager.has_active_session(message.channel.id, message.author.id)
            or chat_input_manager.was_consumed(message.id)
        ):
            return

        bot_role_ids = set()
        try:
            is_dm = message.guild is None
            is_user_mentioned = bool(
                self.bot.user
                and (
                    self.bot.user in message.mentions
                    or any(getattr(u, "id", None) == self.bot.user.id for u in message.mentions)
                )
            )
            is_role_mentioned = False
            if not is_dm and message.guild and message.role_mentions:
                me = message.guild.me
                my_roles = set(getattr(me, "roles", []) or []) if me else set()
                for role in message.role_mentions:
                    if role in my_roles and (
                        (hasattr(role, "is_bot_managed") and role.is_bot_managed())
                        or (self.bot.user and role.name.lower() == self.bot.user.name.lower())
                    ):
                        is_role_mentioned = True
                        bot_role_ids.add(role.id)

            is_mentioned = is_user_mentioned or is_role_mentioned
            is_configured_chan = (not is_dm) and self._is_assistant_channel(message.channel.id)
        except Exception as e:
            print(f"[ASSISTANT] channel check failed: {e}")
            return

        if not (is_dm or is_mentioned or is_configured_chan):
            return

        # Light 2-second per-user cooldown in server channels to prevent ping spam
        if not is_dm:
            now_mono = time.monotonic()
            last_t = self._mention_cooldowns.get(message.author.id, 0.0)
            if now_mono - last_t < 2.0:
                return
            self._mention_cooldowns[message.author.id] = now_mono
            if len(self._mention_cooldowns) > 200:
                cutoff = now_mono - 60.0
                self._mention_cooldowns = {k: v for k, v in self._mention_cooldowns.items() if v > cutoff}

        clean_text = message.content
        if self.bot.user:
            clean_text = (
                clean_text
                .replace(f"<@{self.bot.user.id}>", "")
                .replace(f"<@!{self.bot.user.id}>", "")
            )
        for rid in bot_role_ids:
            clean_text = clean_text.replace(f"<@&{rid}>", "")
        clean_text = clean_text.strip()
        if not clean_text:
            clean_text = "help"

        # Run off the main asyncio event loop so DB reads never stutter active games
        try:
            title, answer = await asyncio.to_thread(answer_alliance_query, clean_text)
        except Exception as e:
            print(f"[ASSISTANT] answer_alliance_query failed: {type(e).__name__}: {e}")
            traceback.print_exc()
            title = f"⚠️ {get_alliance_short()} Bot"
            answer = "Oops, something went wrong — mind asking that again in a second?"

        use_embed = title.startswith("📜")
        try:
            if use_embed:
                embed = hav_embed(
                    title=title,
                    description=answer[:4000],
                    color=HAVColors.ARENA,
                    footer_extra=f"{get_alliance_short()} Alliance Assistant",
                )
                if not is_dm:
                    await message.reply(embed=embed, mention_author=False)
                else:
                    await message.channel.send(embed=embed)
            else:
                if not is_dm:
                    await message.reply(content=answer[:1950], mention_author=False)
                else:
                    await message.channel.send(content=answer[:1950])
        except Exception:
            try:
                await message.channel.send(content=answer[:1950])
            except Exception as e:
                print(f"[ASSISTANT] Failed to send reply: {e}")

    # ---------- /knowledge COMMAND GROUP ----------

    knowledge_group = app_commands.Group(
        name="knowledge",
        description="Manage custom Haven Alliance Knowledge Base entries",
    )

    @knowledge_group.command(name="add", description="Add a new entry to the Alliance Knowledge Base (Admin/Owner only)")
    async def knowledge_add_cmd(self, interaction: discord.Interaction):
        if not await ensure_admin(interaction):
            return
        try:
            await interaction.response.send_modal(KnowledgeModal())
        except Exception as e:
            print(f"[ASSISTANT] send_modal failed (knowledge add): {e}")
            await safe_reply_error(interaction, "⚠️ Could not open the form right now. Please try again.")

    @knowledge_group.command(name="edit", description="Edit an existing Knowledge Base entry by key (Admin/Owner only)")
    @app_commands.describe(key="The unique key of the knowledge entry to edit (use /knowledge list to view keys)")
    @app_commands.autocomplete(key=knowledge_key_autocomplete)
    async def knowledge_edit_cmd(self, interaction: discord.Interaction, key: str):
        if not await ensure_admin(interaction):
            return
        try:
            existing = db.get_knowledge(key)
        except Exception as e:
            print(f"[ASSISTANT] get_knowledge failed: {e}")
            return await interaction.response.send_message(
                "⚠️ Could not look up that entry right now. Please try again.",
                ephemeral=True,
            )
        if not existing:
            return await interaction.response.send_message(
                f"❌ Knowledge entry `{key}` not found. Use `/knowledge list` to view available keys.",
                ephemeral=True,
            )
        try:
            await interaction.response.send_modal(KnowledgeModal(existing=existing))
        except Exception as e:
            print(f"[ASSISTANT] send_modal failed (knowledge edit): {e}")
            await safe_reply_error(interaction, "⚠️ Could not open the form right now. Please try again.")

    @knowledge_group.command(name="remove", description="Remove an entry from the Knowledge Base (Admin/Owner only)")
    @app_commands.describe(key="The unique key of the knowledge entry to remove")
    @app_commands.autocomplete(key=knowledge_key_autocomplete)
    async def knowledge_remove_cmd(self, interaction: discord.Interaction, key: str):
        if not await ensure_admin(interaction):
            return
        try:
            ok = db.remove_knowledge(key)
            if ok:
                invalidate_assistant_caches()
        except Exception as e:
            print(f"[ASSISTANT] remove_knowledge failed: {e}")
            return await interaction.response.send_message(
                "⚠️ Could not remove that entry right now. Please try again.",
                ephemeral=True,
            )
        if not ok:
            return await interaction.response.send_message(
                f"❌ Knowledge entry `{key}` was not found.", ephemeral=True
            )
        try:
            db.log_audit(interaction.user.id, "knowledge_remove", f"Removed knowledge key '{key}'")
        except Exception as e:
            print(f"[ASSISTANT] log_audit failed (remove): {e}")
        await interaction.response.send_message(
            f"🗑️ Removed knowledge entry **`{key}`** from the {get_alliance_short()} Knowledge Base.",
            ephemeral=True,
        )

    @knowledge_group.command(name="list", description="List all approved entries in the Alliance Knowledge Base")
    @app_commands.describe(category="Optional category filter (e.g., Events, Games, Guides, FAQ)")
    async def knowledge_list_cmd(self, interaction: discord.Interaction, category: str | None = None):
        try:
            items = db.list_knowledge(category=category)
        except Exception as e:
            print(f"[ASSISTANT] list_knowledge failed: {e}")
            return await interaction.response.send_message(
                "⚠️ Could not load the Knowledge Base right now. Please try again.",
                ephemeral=True,
            )
        if not items:
            return await interaction.response.send_message(
                "ℹ️ No knowledge base entries found.", ephemeral=True
            )

        per_page = 5
        pages: list[discord.Embed] = []
        for idx in range(0, len(items), per_page):
            chunk = items[idx : idx + per_page]
            embed = hav_embed(
                title=f"📘 {get_alliance_short()} ALLIANCE KNOWLEDGE BASE",
                description=f"Approved topics used by the {get_alliance_short()} Alliance Assistant:",
                color=HAVColors.ARENA,
            )
            for item in chunk:
                try:
                    content = item.get("content", "")
                    truncated = content[:300] + ("..." if len(content) > 300 else "")
                    embed.add_field(
                        name=(
                            f"📌 {item.get('title', '?')} "
                            f"(`{item.get('key', '?')}` · {item.get('category', '?')})"
                        ),
                        value=truncated or "*No content*",
                        inline=False,
                    )
                except Exception as e:
                    print(f"[ASSISTANT] KB list row render failed: {e}")
                    continue
            pages.append(embed)

        if not pages:
            return await interaction.response.send_message(
                "ℹ️ No knowledge base entries found.", ephemeral=True
            )

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0], ephemeral=True)
        else:
            view = PaginatedEmbedView(interaction.user.id, pages)
            await interaction.response.send_message(embed=pages[0], view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(DMHandler(bot))