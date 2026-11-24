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
from typing import List, Optional, Tuple

from core.config import DEFAULT_TZ_OFFSET, HAVColors, format_dual_timestamps, format_tz_label
from core.database import db
from core.loj_calculator import answer_loj_structured_query
from core.permissions import ensure_admin
from core.chat_input import chat_input_manager
from core.owner_stealth import owner_stealth
from core.ui import PaginatedEmbedView, get_alliance_short, hav_embed, safe_reply_error


GAME_EXPLANATIONS = {
    "codebreaker": "Create or join a Codebreaker room via `/games` or `/codebreaker`, then submit four-digit guesses (unique digits, no leading zero). The bot gives private clues after each guess: 🟢 for correct digit and position, and 🟡 for correct digit in the wrong position. First player to crack the code wins!",
    "wordle": "Use `/wordle` (choose Daily or Practice) in any server channel or DM, then simply type your 5-letter guesses directly in chat! 🟩 means right letter & spot, 🟨 means right letter in the wrong spot, and ⬛ means not in the word.",
    "reaction": "In Reaction Race (`/quickdraw` or `/games`), wait until the screen switches from **WAIT...** to green **READY!**, then click as fast as possible. Clicking early is a False Start!",
    "quickdraw": "In Reaction Race (`/quickdraw` or `/games`), wait until the screen switches from **WAIT...** to green **READY!**, then click as fast as possible. Clicking early is a False Start!",
    "scramble": "In Word Scramble (`/games`), rearrange the mixed-up letters before the timer expires. You can also create a multiplayer Word Guessing Race room!",
    "memory": "Use `/memory` or `/games` to play **Memory Challenge** (memorize and reproduce a growing colour sequence `🔴 🔵 🟢 🟡 🟣 🟠` up to 8 items).",
    "math": "In Quick Math (`/games`), solve as many arithmetic questions as possible in 60 seconds, or play Quick Math Battle against other members for speed bonuses!",
    "trivia": "Play solo Trivia or multiplayer Trivia Battle via `/games`. Select answers across 8 categories (Science, History, Geography, Gaming, Movies, Sports, Tech, General Knowledge).",
    "rps": "Play Rock Paper Scissors against the bot or in a 2-player Best of 3 / Best of 5 room via `/games`.",
    "rock paper scissors": "Play Rock Paper Scissors against the bot or in a 2-player Best of 3 / Best of 5 room via `/games`.",
    "number": "In Number Guessing (`/games`), pick a difficulty range and use HIGHER ⬆️ and LOWER ⬇️ clues to find the secret number.",
    "emoji": "In Emoji Guessing (`/games`), identify the movie, game, animal, food, or phrase represented by the emoji combination.",
    "higherlower": "Use `/higherlower` or `/games` to predict whether the next number (1–100) will be higher or lower. Cash out anytime to bank your streak!",
    "treasure": "Use `/treasure` or `/games` to uncover 7 hidden gems on a 3x3 grid while avoiding 2 bombs. Cash out anytime or go for a Full Clear bonus!",
    "tictactoe": "Use `/tictactoe` or `/games` to challenge another member to a fast 3x3 Tic-Tac-Toe duel.",
    "closest": "Join a Closest Wins room via `/games` (2–10 players) — submit a secret number from 1–100 in 20 seconds; closest to the target wins!",
    "connect4": "Use `/connect4` or `/games` to challenge another member to a 7x6 Connect 4 duel.",
}

# fix G: common English words that appear in event titles but shouldn't
# be used as stand-alone search keys.
_EVENT_NAME_STOPWORDS = {
    "the", "an", "a", "of", "and", "or", "for", "in", "on", "at", "to",
    "next", "upcoming", "new",
}

# fix J (informational): refined security triggers — "bypass" alone
# no longer trips the guardrail on innocuous game questions.
_SECURITY_TRIGGERS = [
    "make me admin",
    "give me admin",
    "grant me admin",
    "grant permission",
    "ignore previous",
    "ignore all previous",
    "ignore the above",
    "delete all events",
    "delete all data",
    "bypass permission",
    "bypass admin",
    "bypass security",
    "bypass authentication",
]


def _parse_iso_utc(raw_value: Optional[str]) -> Optional[datetime]:
    """
    fix I: robust ISO-8601 parser.
    Handles trailing `Z` (fails on Python ≤ 3.10 with fromisoformat) and
    naive timestamps (assumed UTC).
    """
    if not raw_value:
        return None
    s = str(raw_value).strip()
    if not s:
        return None
    # Replace trailing `Z` with explicit +00:00 (works on all Python 3.x)
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


def _format_event(ev: dict, tz_off: float) -> Optional[str]:
    """
    fix C + H: safely render a single event line.
    Returns None if the event data is malformed.
    """
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
            f"The next **{name}** is scheduled for **{dual['game_time_short']} game time** "
            f"(**{dual['india_time_short']} India time**) on **{dual['short_date']}** "
            f"({dual['discord_relative']}).{desc_note}"
        )
    except Exception as e:
        print(f"[ASSISTANT] _format_event failed: {e}")
        return None


def answer_alliance_query(raw_query: str) -> Tuple[str, str]:
    """
    Read-only, deterministic alliance assistant.
    Never mutates state or grants permissions (Part 8.3).
    """
    short = get_alliance_short()
    q = (raw_query or "").strip()
    q_low = q.lower()
    _SYNONYMS = {
        "euipment": "equipment", "equip": "equipment", "eq": "equipment", "gear": "equipment",
        "lvl": "level", "lv": "level", "fc": "forticlad", "wo": "office",
        "cc": "crystal clash", "ut": "ultimate trial", "cage": "ultimate trial",
        "urself": "yourself", "ur": "your", "u": "you", "r": "are",
        "ref": "reformation", "reform": "reformation", "heros": "heroes",
        "troop": "troops", "brawl": "alliance brawl", "svs": "svs supreme honor", "riots": "riot", "shields": "shield", "join": "joiner joiners",
    }
    raw_tokens = re.findall(r"[a-z0-9]+", q_low)
    tokens = set(raw_tokens)
    for t in raw_tokens:
        if t in _SYNONYMS:
            tokens.update(_SYNONYMS[t].split())

    # 1. Security guardrail
    if any(p in q_low for p in _SECURITY_TRIGGERS):
        return (
            "🔒 Security Policy",
            "I am a read-only Alliance Assistant and cannot grant permissions or execute administrative actions. "
            "Administrative actions require authorized slash commands with backend role verification.",
        )

    # 2. Event scheduling permissions
    if ("event" in q_low or "schedule" in q_low) and any(
        w in q_low
        for w in ["can i", "how do i create", "who can", "schedule an", "make an", "create an", "modify"]
    ):
        return (
            "📅 Event Scheduling Permissions",
            "Only authorized administrators can schedule or modify events. You can view upcoming events at any time using `/events`.",
        )

    # 3. Timezone — fix A
    try:
        tz_off = float(db.get_config("game_tz_offset", str(DEFAULT_TZ_OFFSET)))
    except Exception as e:
        print(f"[ASSISTANT] tz config read failed: {e}")
        tz_off = float(DEFAULT_TZ_OFFSET)

    # 4. Upcoming events — fix A
    try:
        upcoming = db.get_upcoming_events(include_cancelled=False) or []
    except Exception as e:
        print(f"[ASSISTANT] get_upcoming_events failed: {e}")
        upcoming = []

    # 5. Check specific event by name — fix G + H
    for ev in upcoming:
        try:
            ev_name = (ev.get("name") or "").strip()
            if not ev_name:
                continue
            ev_name_low = ev_name.lower()
            ev_words = {
                w for w in re.findall(r"[a-z0-9]+", ev_name_low)
                if len(w) >= 3 and w not in _EVENT_NAME_STOPWORDS
            }
            name_in_query = ev_name_low in q_low
            words_in_query = bool(ev_words) and any(w in tokens for w in ev_words)
            if not (name_in_query or words_in_query):
                continue
            rendered = _format_event(ev, tz_off)
            if rendered:
                return (f"📅 Upcoming Event — {ev_name}", rendered)
        except Exception as e:
            print(f"[ASSISTANT] event name match failed: {e}")
            continue

    # 6. General "when / upcoming" listing
    if any(w in tokens for w in ["event", "events", "schedule", "upcoming", "next", "surge", "brawl", "svs"]) and not re.search(r"\b(?:day|d)\s*[1-5]\b", q_low) and "prep" not in tokens and "preparation" not in tokens:
        if any(w in tokens for w in ["when", "next", "upcoming", "schedule", "events", "time"]):
            if not upcoming:
                return (
                    f"📅 Upcoming {short} Events",
                    "There are currently no upcoming events scheduled in the database. Check `/events` later for updates!",
                )
            lines = []
            for ev in upcoming[:4]:
                try:
                    dt = _parse_iso_utc(ev.get("start_time_utc"))
                    if not dt:
                        continue
                    try:
                        dual = format_dual_timestamps(dt, tz_off)
                    except Exception as e:
                        print(f"[ASSISTANT] format_dual_timestamps failed: {e}")
                        continue
                    lines.append(
                        f"• **{ev.get('name', '?')}** — `{dual['short_date']}` at "
                        f"**`{dual['game_time_short']} game time`** "
                        f"(`{dual['india_time_short']} India time`) · {dual['discord_relative']}"
                    )
                except Exception as e:
                    print(f"[ASSISTANT] upcoming-list render failed: {e}")
                    continue
            if not lines:
                return (
                    f"📅 Upcoming {short} Events",
                    "There are currently no upcoming events scheduled in the database. Check `/events` later for updates!",
                )
            return (f"📅 Upcoming {short} Events", "\n".join(lines))

    # 7. Game instructions
    for g_key, g_exp in GAME_EXPLANATIONS.items():
        if g_key in q_low:
            return (f"🎮 How to Play — {g_key.title()}", g_exp)

    _LOJ_HINT_WORDS = {
        "jail", "loj", "hero", "heroes", "troop", "troops", "gorilla", "tyron", "tyronn",
        "wukong", "ada", "phoenix", "inata", "jasser", "barry", "patrick", "whisper",
        "lunarl", "veronica", "koschevoi", "sawyer", "ryuichi", "equipment", "gear",
        "firearms", "vest", "cuffs", "diamond", "diamonds", "code", "codes",
        "redeem", "warehouse", "inventory", "power", "camp", "training", "inmate", "inmates",
        "rally", "joiner", "joiners", "leader", "leaders", "garrison", "plunder", "shield",
        "city", "hall", "prison", "warden", "office", "lineup", "squad", "ratio", "ratios",
        "dice", "brawl", "gasoline", "cosmos", "cosmic", "satellite", "satellites",
        "overclock", "trial", "cage", "scarlet", "butcher", "crystal", "clash",
        "sandsea", "dreadwaker", "overlord", "forticlad", "barracks", "medical",
        "factory", "riot", "svs", "honor", "haven", "island",
    }
    if any(w in tokens for w in ["games", "game", "play", "arena"]) and not (tokens & _LOJ_HINT_WORDS):
        return (
            f"🎮 {short} Gaming Arena",
            f"Use `/games` to open the **{short} Gaming Arena**! You can play 12 Single-Player games "
            "(Higher or Lower, Treasure Hunt, Wordle Daily & Practice, Word Scramble, Memory Challenge, Quick Math, Reaction Speed Test, Trivia, RPS, Number Guessing, Emoji Guessing) "
            "or host Multiplayer rooms (Tic-Tac-Toe, Closest Wins, Four-Digit Codebreaker, Reaction Race, Word Race, Quick Math Battle, Trivia Battle, RPS, Emoji Guessing, Connect 4).",
        )

    # 8. Alliance rules — fix A
    if any(w in tokens for w in ["rule", "rules"]) and not (tokens & {"crystal", "clash", "svs", "supreme", "honor", "joiner", "joiners", "rally", "trial", "cage", "sandsea", "dreadwaker"}):
        try:
            rules_text = db.get_formatted_rules()
        except Exception as e:
            print(f"[ASSISTANT] get_formatted_rules failed: {e}")
            rules_text = "Alliance rules are currently unavailable. Please try again later."
        return (f"📜 {short} Alliance Rules", rules_text)

    # 11. Help
    if len(tokens) <= 4 and (tokens & {"help", "commands", "command"}):
        tz_label = format_tz_label(tz_off)
        return (
            f"🛡️ {short} Bot Commands",
            f"• `/games` — Open the {short} Gaming Arena\n"
            f"• `/events` — View upcoming events in Game Time (`{tz_label}`) & India Time (`IST`)\n"
            "• `/rules view` — View official alliance rules\n"
            "• `/profile` & `/leaderboard` — Check player stats, match history, and rankings\n"
            "• `/help` — Full command guide",
        )

    # 10a. Bot identity & creator (Sam — Server 201)
    _CREATOR_PHRASES = (
        "who made you", "who made u", "who built you", "who built u",
        "who created you", "who created u", "who is your owner", "who is ur owner",
        "who is your creator", "who is your dev", "who is your developer",
        "who owns you", "who owns u", "who coded you", "who coded u",
        "who programmed you", "who is sam",
    )
    _ABOUT_BOT_PHRASES = (
        "who are you", "who are u", "who r u", "who r you",
        "tell me about yourself", "tell me about ur self", "tell me about urself",
        "about yourself", "about urself", "about ur self", "about you", "about u",
        "introduce yourself", "introduce urself", "what are you", "what are u",
        "what r u", "what can you do", "what can u do", "what do you do",
    )
    if any(re.search(rf"\b{re.escape(p)}\b", q_low) for p in _CREATOR_PHRASES):
        return (
            f"👑 Creator — Sam (Server 201)",
            f"I was built by **Sam** from **Server 201** for the **Haven ({short})** alliance in **Lands of Jail**!\n"
            f"If you ever spot a bug or want a new feature, just ping **Sam** or use the **Report Bug** button.",
        )

    if any(re.search(rf"\b{re.escape(p)}\b", q_low) for p in _ABOUT_BOT_PHRASES):
        return (
            f"🛡️ I'm {short} Bot — Haven Alliance Assistant",
            f"Hey! I'm **{short} Bot**, the official Discord bot for the **Haven ({short})** alliance on **Server 201** in **Lands of Jail**, built by **Sam** (Server 201).\n\n"
            "Here's what I can help you with:\n"
            "• **Lands of Jail Guides** — Ask me about heroes, rally leaders/joiners, Trial Cage, SvS prep days, Crystal Clash, Cosmos Hub, buildings, or gift codes\n"
            "• **Alliance Events & Rules** — Check `/events` (Game Time + IST) or `/rules view`\n"
            "• **22 Alliance Games** — Play solo or multiplayer anytime with `/games`",
        )

    if any(p in q_low for p in ("which server", "what server", "our server", "server 201")) and "svs" not in tokens:
        return (
            f"🌐 Haven ({short}) — Server 201",
            f"We're the **Haven ({short})** alliance on **Server 201** in **Lands of Jail** (bot built by **Sam**).",
        )

    # 10. Greetings
    if len(raw_tokens) <= 2 and (set(raw_tokens) & {"hi", "hello", "hey", "yo", "hola", "sup"}):
        return (
            f"🛡️ {short} Alliance Assistant",
            f"Hey! I'm **{short} Bot** (built by **Sam** for **Haven** on **Server 201**). Ask me about **Lands of Jail** (heroes, Trial Cage, SvS, Crystal Clash, buildings), upcoming events, "
            f"alliance rules, strategies, or how to play any {short} game — or use `/games`, `/events`, and `/help`.",
        )

    # 8b. Lands of Jail exact upgrade calculators, hero directory, SvS days & buff pricing
    try:
        loj_ans = answer_loj_structured_query(q)
        if loj_ans is not None:
            return loj_ans
    except Exception as e:
        print(f"[ASSISTANT] loj_calculator failed: {e}")

    # 9. Knowledge Base search — fix A
    try:
        kb_items = db.list_knowledge() or []
    except Exception as e:
        print(f"[ASSISTANT] list_knowledge failed: {e}")
        kb_items = []

    best_item = None
    best_score = 0.0
    for item in kb_items:
        try:
            haystack = (
                f"{item.get('key', '')} {item.get('title', '')} "
                f"{item.get('category', '')} {item.get('keywords', '')}"
            ).lower()
            hay_tokens = set(re.findall(r"[a-z0-9]+", haystack))
            _KB_STOP = {
                "how", "to", "what", "who", "can", "is", "are", "the", "a", "an",
                "for", "in", "on", "of", "do", "i", "my", "me", "tell", "please",
                "about", "hey", "hi", "explain", "info", "guide", "should", "and",
                "or", "you", "your", "from", "with", "much", "many", "get", "lands", "jail",
            }
            q_meaningful = {t for t in tokens if t not in _KB_STOP} or tokens
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
        except Exception as e:
            print(f"[ASSISTANT] KB score failed: {e}")
            continue

    if best_item and best_score >= 1.6:
        return (
            f"📘 {best_item.get('title', '?')} ({best_item.get('category', '?')})",
            best_item.get("content", ""),
        )

    # 12. Honest fallback
    return (
        f"🤖 {short} Alliance Assistant",
        "I don't have approved alliance information matching that specific question right now. "
        "You can ask me about:\n"
        "• **Upcoming Events** (*\"When is the next Surge?\"*)\n"
        "• **Alliance Rules & Guides** (*\"What are the alliance rules?\"*)\n"
        "• **How to Play Games** (*\"How do I play Codebreaker?\"*)\n"
        "Or type `/help`, `/events`, or `/games` to browse directly!",
    )



async def knowledge_key_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    try:
        items = db.list_knowledge()
    except Exception:
        return []
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
    key_input = discord.ui.TextInput(
        label="Unique Topic Key",
        placeholder="e.g., surge_strategy",
        max_length=40,
        required=True,
    )
    title_input = discord.ui.TextInput(
        label="Title",
        placeholder="e.g., Surge Rally Strategy",
        max_length=80,
        required=True,
    )
    category_input = discord.ui.TextInput(
        label="Category (FAQ, Guides, Events, Strategy)",
        placeholder="Strategy",
        max_length=30,
        required=True,
    )
    keywords_input = discord.ui.TextInput(
        label="Search Keywords (space-separated)",
        placeholder="surge rally troop formation leader",
        max_length=120,
        required=False,
    )
    content_input = discord.ui.TextInput(
        label="Approved Knowledge Content",
        style=discord.TextStyle.paragraph,
        placeholder="Enter the approved alliance information...",
        max_length=1500,
        required=True,
    )

    def __init__(self, existing: Optional[dict] = None):
        super().__init__(title="Edit Knowledge Entry" if existing else "Add Alliance Knowledge")
        if existing:
            self.key_input.default = existing["key"]
            self.title_input.default = existing["title"]
            self.category_input.default = existing["category"]
            self.keywords_input.default = existing.get("keywords") or ""
            self.content_input.default = existing["content"]

    async def on_submit(self, interaction: discord.Interaction):
        # fix D: guard the whole flow so the user always gets a response.
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

            # fix F: audit log is fire-and-forget.
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
    """Part 8: Alliance AI Assistant (DMs + Configured Alliance Channels) and /knowledge management."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._assistant_raw_cache: Optional[str] = None
        self._assistant_chan_set: set = set()
        self._mention_cooldowns: dict = {}

    def _is_assistant_channel(self, channel_id: int) -> bool:
        # O(1) cached lookup; only re-parses JSON when server_config changes.
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
        # fix K: also bail on whitespace-only.
        if not message.content or not message.content.strip():
            return
        if message.content.startswith(("/", "!")):
            return
        # Never interrupt active chat-input games (Wordle, Scramble, Quick Math, etc.) in DMs or channels.
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
            # Also catch when a member @mentions the bot's auto-created managed role in a server channel
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

        # fix A: guard the whole query pipeline.
        try:
            title, answer = answer_alliance_query(clean_text)
        except Exception as e:
            print(f"[ASSISTANT] answer_alliance_query failed: {type(e).__name__}: {e}")
            traceback.print_exc()
            title = f"⚠️ {get_alliance_short()} Alliance Assistant"
            answer = "Sorry, something went wrong processing your question. Please try again in a moment."

        embed = hav_embed(
            title=title,
            description=answer,
            color=HAVColors.ARENA,
            footer_extra=f"{get_alliance_short()} Alliance Assistant",
        )
        try:
            if not is_dm:
                await message.reply(embed=embed, mention_author=False)
            else:
                await message.channel.send(embed=embed)
        except Exception:
            try:
                await message.channel.send(embed=embed)
            except Exception as e:
                print(f"[ASSISTANT] Failed to send reply: {e}")

    # ---------- /knowledge COMMAND GROUP ----------

    knowledge_group = app_commands.Group(
        name="knowledge",
        description="Manage the approved Alliance Knowledge Base for the AI Assistant",
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
        # fix E: DB call guarded.
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
        # fix E: DB call guarded.
        try:
            ok = db.remove_knowledge(key)
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
        # fix F: audit log is fire-and-forget.
        try:
            db.log_audit(interaction.user.id, "knowledge_remove", f"Removed knowledge key '{key}'")
        except Exception as e:
            print(f"[ASSISTANT] log_audit failed (remove): {e}")
        await interaction.response.send_message(
            f"🗑️ Removed knowledge entry **`{key}`** from the {get_alliance_short()} Knowledge Base.",
            ephemeral=True,
        )

    @knowledge_group.command(name="list", description="List all approved entries in the Alliance Knowledge Base")
    @app_commands.describe(category="Optional category filter (e.g., Events, Strategy, Guides, FAQ)")
    async def knowledge_list_cmd(self, interaction: discord.Interaction, category: Optional[str] = None):
        # fix E: DB call guarded.
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
        pages: List[discord.Embed] = []
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