# core/knowledge_defaults.py
"""Shared default Knowledge Base entries for Haven (HAV) — Server 201."""

DEFAULT_KNOWLEDGE_ENTRIES = [
    {
        "key": "bot_about",
        "title": "About HAV Bot & Creator (Sam — Server 201)",
        "category": "About",
        "content": (
            "I'm **HAV Bot**, the official Discord bot for **Haven (`HAV`)** on **Server 201**, built by **Sam**.\n"
            "I track alliance event timings in Game Time & India Time (`/events`), share alliance rules (`/rules view`), "
            "help you learn how to play all 22 solo & multiplayer Discord games (`/games`), and answer any custom alliance guides added by admins."
        ),
        "keywords": "who are you who made you who built you who created you about yourself bot owner developer sam server 201 haven hav",
    },
    {
        "key": "surge_guide",
        "title": "Turmoil Surge Event Reminder",
        "category": "Events",
        "content": (
            "Check `/events` for the exact **Turmoil Surge** Game Time & India Time schedule, and try to be online about 10 minutes before start so everyone can reinforce each other."
        ),
        "keywords": "surge turmoil surge event schedule timing reinforce",
    },
    {
        "key": "codebreaker_help",
        "title": "How to Play Four-Digit Codebreaker",
        "category": "Games",
        "content": (
            "Start or join a room with `/games` or `/codebreaker`. The bot picks a secret 4-digit code (all unique digits, no leading zero). "
            "Submit guesses and use the clues: 🟢 = right digit & right spot, 🟡 = right digit in the wrong spot."
        ),
        "keywords": "codebreaker how to play 4 digit secret code clues mastermind",
    },
    {
        "key": "event_permissions",
        "title": "Who Can Schedule Alliance Events",
        "category": "FAQ",
        "content": (
            "Only authorized alliance admins and **Sam** can create, edit, or cancel events. "
            "Everyone in Haven can check upcoming event times anytime with `/events`."
        ),
        "keywords": "schedule create add modify cancel event permission admin who can",
    },
    {
        "key": "member_responsibilities",
        "title": "HAV Member Responsibilities",
        "category": "Guides",
        "content": (
            "Stay active on **Server 201**, check `/events` for upcoming alliance times, help teammates out, "
            "and keep chat friendly and respectful for everyone in **Haven (HAV)**."
        ),
        "keywords": "member responsibilities duties active rules guide haven hav server 201",
    },
]
