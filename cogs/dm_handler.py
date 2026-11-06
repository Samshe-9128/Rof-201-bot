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

from core.config import DEFAULT_TZ_OFFSET, ROFColors, format_dual_timestamps
from core.database import db
from core.permissions import ensure_admin
from core.ui import PaginatedEmbedView, rof_embed


GAME_EXPLANATIONS = {
    "codebreaker": "Create or join a Codebreaker room via `/games` or `/codebreaker`, then submit four-digit guesses (unique digits, no leading zero). The bot gives private clues after each guess: 🟢 for correct digit and position, and 🟡 for correct digit in the wrong position. First player to crack the code wins!",
    "wordle": "Use `/wordle` (daily) or `/wordle_practice` (unlimited) to guess a hidden 5-letter word in 6 attempts. 🟩 means right letter & spot, 🟨 means right letter in the wrong spot, and ⬛ means not in the word.",
    "reaction": "In Reaction Race (`/quickdraw` or `/games`), wait until the screen switches from **WAIT...** to green **READY!**, then click as fast as possible. Clicking early is a False Start!",
    "quickdraw": "In Reaction Race (`/quickdraw` or `/games`), wait until the screen switches from **WAIT...** to green **READY!**, then click as fast as possible. Clicking early is a False Start!",
    "scramble": "In Word Scramble (`/games`), rearrange the mixed-up letters before the timer expires. You can also create a multiplayer Word Guessing Race room!",
    "memory": "Use `/memory` or `/games` to play **Memory Challenge** (memorize and reproduce a growing colour sequence `🔴 🔵 🟢 🟡`) or **Emoji Pair Match** (match 8 pairs on a 4x4 grid).",
    "math": "In Quick Math (`/games`), solve as many arithmetic questions as possible in 60 seconds, or play Quick Math Battle against other members for speed bonuses!",
    "trivia": "Play solo Trivia or multiplayer Trivia Battle via `/games`. Select answers across 8 categories (Science, History, Geography, Gaming, Movies, Sports, Tech, General Knowledge).",
    "rps": "Play Rock Paper Scissors against the bot or in a 2-player Best of 3 / Best of 5 room via `/games`.",
    "rock paper scissors": "Play Rock Paper Scissors against the bot or in a 2-player Best of 3 / Best of 5 room via `/games`.",
    "number": "In Number Guessing (`/games`), pick a difficulty range and use HIGHER ⬆️ and LOWER ⬇️ clues to find the secret number.",
    "emoji": "In Emoji Guessing (`/games`), identify the movie, game, animal, food, or phrase represented by the emoji combination.",
    "undercover": "Use `/undercover` with 3–6 players. Everyone receives the same secret word in DMs except the Spy, who gets a slightly different word!",
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
    q = (raw_query or "").strip()
    q_low = q.lower()
    tokens = set(re.findall(r"[a-z0-9]+", q_low))

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
    if any(w in tokens for w in ["event", "events", "schedule", "upcoming", "next", "surge", "brawl", "svs"]):
        if any(w in tokens for w in ["when", "next", "upcoming", "schedule", "events", "time"]):
            if not upcoming:
                return (
                    "📅 Upcoming ROF Events",
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
                    "📅 Upcoming ROF Events",
                    "There are currently no upcoming events scheduled in the database. Check `/events` later for updates!",
                )
            return ("📅 Upcoming ROF Events", "\n".join(lines))

    # 7. Game instructions
    for g_key, g_exp in GAME_EXPLANATIONS.items():
        if g_key in q_low:
            return (f"🎮 How to Play — {g_key.title()}", g_exp)

    if any(w in tokens for w in ["games", "game", "play", "arena"]):
        return (
            "🎮 ROF Gaming Arena",
            "Use `/games` to open the **ROF Gaming Arena**! You can play 10 Single-Player games "
            "(Wordle, Word Scramble, Memory Challenge, Quick Math, Reaction Speed Test, Trivia, RPS, Number Guessing, Emoji Guessing) "
            "or host Multiplayer rooms (Four-Digit Codebreaker, Reaction Race, Word Race, Quick Math Battle, Trivia Battle, RPS, Emoji Guessing, Undercover, Connect 4).",
        )

    # 8. Alliance rules — fix A
    if any(w in tokens for w in ["rule", "rules"]):
        try:
            rules_text = db.get_formatted_rules()
        except Exception as e:
            print(f"[ASSISTANT] get_formatted_rules failed: {e}")
            rules_text = "Alliance rules are currently unavailable. Please try again later."
        return ("📜 ROF Alliance Rules", rules_text)

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
            overlap = len(tokens & hay_tokens)
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

    # 10. Greetings
    if tokens & {"hi", "hello", "hey", "yo", "hola", "sup"}:
        return (
            "🛡️ ROF Alliance Assistant",
            "Hello warrior! Ask me about upcoming alliance events (e.g. *\"When is the next Surge?\"*), "
            "alliance rules, strategies, or how to play any ROF game — or use `/games`, `/events`, and `/help`.",
        )

    # 11. Help
    if tokens & {"help", "commands", "command"}:
        return (
            "🛡️ ROF Bot Commands",
            "• `/games` — Open the ROF Gaming Arena\n"
            "• `/events` — View upcoming events in Game Time (`UTC-2`) & India Time (`IST`)\n"
            "• `/rules` — View official alliance rules\n"
            "• `/profile` & `/leaderboard` — Check player stats and rankings\n"
            "• `/help` — Full command guide",
        )

    # 12. Honest fallback
    return (
        "🤖 ROF Alliance Assistant",
        "I don't have approved alliance information matching that specific question right now. "
        "You can ask me about:\n"
        "• **Upcoming Events** (*\"When is the next Surge?\"*)\n"
        "• **Alliance Rules & Guides** (*\"What are the alliance rules?\"*)\n"
        "• **How to Play Games** (*\"How do I play Codebreaker?\"*)\n"
        "Or type `/help`, `/events`, or `/games` to browse directly!",
    )


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
            self.keywords_input.default = existing.get("keywords", "")
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

            embed = rof_embed(
                title=f"✅ KNOWLEDGE SAVED — {saved['title']}",
                description=(
                    f"**Key:** `{saved['key']}` | **Category:** `{saved['category']}`\n"
                    f"**Keywords:** `{saved['keywords'] or 'None'}`\n\n"
                    f"{saved['content']}"
                ),
                color=ROFColors.SUCCESS,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"[ASSISTANT] KnowledgeModal.on_submit failed: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⚠️ Could not save the knowledge entry. Please try again.",
                        ephemeral=True,
                    )
            except Exception:
                pass


class DMHandler(commands.Cog):
    """Part 8: Alliance AI Assistant (DMs + Configured Alliance Channels) and /knowledge management."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_assistant_channel(self, channel_id: int) -> bool:
        # fix B: guard the DB read itself.
        try:
            raw = db.get_config("assistant_channels", "[]")
            chan_list = json.loads(raw)
            return int(channel_id) in [int(x) for x in chan_list]
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

        try:
            is_dm = message.guild is None
            is_mentioned = bool(self.bot.user and self.bot.user in message.mentions)
            is_configured_chan = (not is_dm) and self._is_assistant_channel(message.channel.id)
        except Exception as e:
            print(f"[ASSISTANT] channel check failed: {e}")
            return

        if not (is_dm or is_mentioned or is_configured_chan):
            return

        clean_text = message.content
        if self.bot.user:
            clean_text = (
                clean_text
                .replace(f"<@{self.bot.user.id}>", "")
                .replace(f"<@!{self.bot.user.id}>", "")
                .strip()
            )
        if not clean_text:
            clean_text = "help"

        # fix A: guard the whole query pipeline.
        try:
            title, answer = answer_alliance_query(clean_text)
        except Exception as e:
            print(f"[ASSISTANT] answer_alliance_query failed: {type(e).__name__}: {e}")
            traceback.print_exc()
            title = "⚠️ ROF Alliance Assistant"
            answer = "Sorry, something went wrong processing your question. Please try again in a moment."

        embed = rof_embed(
            title=title,
            description=answer,
            color=ROFColors.ARENA,
            footer_extra="ROF Alliance Assistant",
        )
        try:
            await message.channel.send(embed=embed)
        except Exception as e:
            print(f"[ASSISTANT] Failed to send reply: {e}")

    # ---------- /knowledge COMMAND GROUP ----------

    knowledge_group = app_commands.Group(
        name="knowledge",
        description="Manage the approved ROF Alliance Knowledge Base for the AI Assistant",
    )

    @knowledge_group.command(name="add", description="Add a new entry to the ROF Knowledge Base (Admin/Owner only)")
    async def knowledge_add_cmd(self, interaction: discord.Interaction):
        if not await ensure_admin(interaction):
            return
        await interaction.response.send_modal(KnowledgeModal())

    @knowledge_group.command(name="edit", description="Edit an existing Knowledge Base entry by key (Admin/Owner only)")
    @app_commands.describe(key="The unique key of the knowledge entry to edit (use /knowledge list to view keys)")
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
        await interaction.response.send_modal(KnowledgeModal(existing=existing))

    @knowledge_group.command(name="remove", description="Remove an entry from the Knowledge Base (Admin/Owner only)")
    @app_commands.describe(key="The unique key of the knowledge entry to remove")
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
            f"🗑️ Removed knowledge entry **`{key}`** from the ROF Knowledge Base.",
            ephemeral=True,
        )

    @knowledge_group.command(name="list", description="List all approved entries in the ROF Knowledge Base")
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
            embed = rof_embed(
                title="📘 ROF ALLIANCE KNOWLEDGE BASE",
                description="Approved topics used by the ROF Alliance Assistant:",
                color=ROFColors.ARENA,
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