# ROF Discord Bot — Gaming & Alliance Management System

Official Discord bot for the **Rise of Farkers (ROF)** alliance — with **100% live alliance renaming & config sync** across every feature (welcomes, events, rules, games, profiles, leaderboards, and the AI assistant) with zero restarts, powered by **Python 3.11+**, **discord.py 2.4+**, and **SQLite (WAL mode)**.

---

## Quick Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   (`discord.py>=2.4.0` and `python-dotenv>=1.0.1`)
2. **Enable required Discord Intents:**
   In the Discord Developer Portal → your Bot application → **Bot** tab → **Privileged Gateway Intents**, turn ON:
   - **Message Content Intent** *(required for natural chat-typing games, DM assistant, and owner DM commands)*
   - **Server Members Intent** *(required for welcome onboarding and member lookups)*
3. **Configure `.env`:**
   Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN`, `GUILD_ID`, `OWNER_ID` (your Discord User ID), and optional channel IDs (`EVENT_CHANNEL_ID`, `WELCOME_CHANNEL_ID`, `RULES_CHANNEL_ID`, `SERVER_TZ_OFFSET=-2`).
4. **Run the bot:**
   ```bash
   python bot.py
   ```
   On startup, the bot automatically initializes and migrates `rof_bot.db` (SQLite with WAL mode), syncs global slash commands for server + DM play, and loads all 14 cogs.

---

## Gaming Arena (`/games`)

### Single-Player Games (Work Identically in Server Channels & DMs)

| Game | Command / Launcher | How to Play | Key Features |
| :--- | :--- | :--- | :--- |
| **Wordle (Daily & Practice)** | `/wordle [mode]`, `/games` | **Type any 5-letter word directly in chat or DM** | Choose `Daily` or `Practice` right in `/wordle`; live-updating board + keyboard, probe words allowed, daily streak & guess distribution, Share Result, `quit` to give up |
| **Word Scramble** | `/games` | **Type the unscrambled word directly in chat** | 3 timed rounds, Easy/Medium/Hard, type `hint` or `quit` anytime |
| **Quick Math** | `/games` | **Type numeric answers directly in chat** | 60-second sprint, streak bonus multipliers, Easy/Medium/Hard, type `quit` or click End Early |
| **Number Guessing** | `/games` | **Type numbers directly in chat** | Bot reacts `⬆️` / `⬇️` / `🎉` and updates guess history live; Easy (1–50), Medium (1–100), Hard (1–500) |
| **Emoji Guessing** | `/games` | **Type your answer directly in chat** | Movies, Games, Animals, Food, Phrases, Objects; 3 attempts, type `hint` or `quit` |
| **Higher or Lower** | `/higherlower`, `/games` | **1-click buttons** (Higher / Lower / Cash Out) | Risk/reward streak scoring (`1–100`) |
| **Treasure Hunt (Mining 3x3)** | `/treasure`, `/games` | **1-click 3x3 tile grid** | 7 hidden gems (`💎`) + 2 hidden bombs (`💣`), Cash Out anytime or go for Full Clear bonus |
| **Memory Challenge** | `/memory`, `/games` | **1-click color buttons** | Progressive sequence reproduction (`🔴 🔵 🟢 🟡 🟣 🟠`), up to 8 items |
| **Reaction Speed Test** | `/quickdraw mode:solo`, `/games` | **1-click reaction button** | Random delay (`2–5.5s`), millisecond timing, personal best & average tracking, false-start detection |
| **Trivia Challenge** | `/games` | **1-click A/B/C/D buttons** | 5 questions across 8 categories with instant explanations |
| **Rock Paper Scissors** | `/games` | **1-click buttons** | Single Round, Best of 3, or Best of 5 vs the Bot |

### Multiplayer Games (Server Channels Only — Public Room Lobbies)

| Game | Command / Launcher | Players | How to Play |
| :--- | :--- | :--- | :--- |
| **Word Guessing Race** | `/games` | 2–10 | **Race by typing answers directly in chat** across 3 rounds |
| **Quick Math Battle** | `/games` | 2–10 | **Type numbers directly in chat**; 10 pts + speed bonus per round |
| **Multiplayer Emoji Guessing** | `/games` | 2–10 | **Type answers directly in chat**; first correct wins the round |
| **Four-Digit Codebreaker** | `/codebreaker`, `/games` | 1–8 or 1v1 | Solo & 1v1 Duel accept **direct 4-digit chat typing**; multiplayer rooms use private popups so clues stay secret |
| **Closest Wins** | `/games` | 2–10 | 20-second simultaneous secret number guess (`1–100`) via private popup |
| **Trivia Battle** | `/games` | 2–10 | 5 rounds with private locked-in A/B/C/D answers & live scoreboard |
| **Reaction Race** | `/quickdraw`, `/games` | 2–10 | Compete for fastest valid click after green READY signal |
| **Multiplayer RPS** | `/games` | 2 (1v1) | Best of 3/5 with hidden moves revealed simultaneously |
| **Tic-Tac-Toe** | `/tictactoe`, `/games` | 2 (1v1) | Fast 3x3 grid duel |
| **Connect 4** | `/connect4`, `/games` | 2 (1v1) | Classic 7x6 strategy grid |

---

## Alliance Events & Scheduling (Streamlined)

All events automatically display **Game Time** (configured via `/admin settings`, default `UTC-02:00`), **India Time (`Asia/Kolkata` / IST)**, and each member's local Discord timestamp.

| Command | Access | What It Does |
| :--- | :--- | :--- |
| `/events` | Everyone (Server + DM) | Lists all upcoming scheduled events with countdowns, repeat schedule, and alert status |
| `/event add [repeat] [channel] [announce]` | Admin / Owner | Pick an optional repeat preset (`One-time`, `Every Day`, `Every 2 Days`, `Every 3 Days`, `Weekly`, `Every 14 Days`, or `Custom`) and optional silent creation (`announce: False`), then fill in the popup (Name, Date, Game Time, Reminder minutes, Repeat days) |
| `/event edit [event_id]` | Admin / Owner | Edit any scheduled event's name, date, time, reminder, or repeat interval |
| `/event view [event_id]` | Everyone | Shows full details and timezone conversions. Admins & Owner also get 1-click **✏️ Edit**, **🔕 Mute / Unmute Alerts**, and **🗑️ Delete** buttons right on the card |
| `/event delete [event_id]` | Admin / Owner | Permanently deletes an event (with confirmation) |

**How Recurring Events Work:** When a recurring event (`repeat_days > 0`) passes its start time, the background scheduler automatically advances `start_time_utc` forward by `repeat_days` (e.g., `+2 days`) and resets `reminder_sent = 0` so it runs continuously until you change repeat to `0` in `/event edit` or delete it.

---

## Alliance Management, Profiles, Rules & AI Assistant

- **Dynamic Alliance Branding (`.setalliance` — Private Owner DM Only):** Change your alliance's short tag (e.g. `ROF` → `KINGS`), full alliance name, and embed footer live at any time. Updates sync **immediately everywhere** — Welcome channel & DM embeds, Event announcements/reminders/lists, Rules, Admin panels, Profiles, Ranks (`<TAG> Legend`), Leaderboards, Game Room IDs, all 22 Games, and the AI Assistant — with zero restarts.
- **Admin Settings & Channels (`/admin settings`, `/admin channels`, `/admin welcome`, `/admin permissions`):** Configure Game Time UTC offset (syncs live across welcomes, events, help, and assistant), default reminder lead time, Wordle open-to-all toggle, wipe-on-leave toggle, announcement/welcome/rules/assistant channels, authorized admin roster, audit logs, and SQLite DB backups.
- **Profiles & Leaderboards (`/profile`, `/leaderboard`):** Unified SQLite tracking for total points, ranks (`Bronze` → `<TAG> Legend`), win rates, per-game best scores, reaction records, and a **1-click 📜 Match History** button directly on `/profile`.
- **Alliance Rules (`/rules view|add|edit|remove`):** Manage and post numbered alliance rules.
- **Alliance AI Assistant (`cogs/dm_handler.py` & `/knowledge add|edit|remove|list`):** Read-only assistant in DMs, `@mentions`, and configured channels that answers questions about upcoming events, rules, games, and approved alliance knowledge — and automatically stays silent while a user is playing an active chat-input game in DM.

---

## Private Owner-Only Controls (OWNER ONLY — DO NOT SHARE PUBLICLY)

These stealth commands **only work when sent by `OWNER_ID` in a Direct Message to the bot**. They have **no slash commands, no visible buttons, and no public `/help` entries**. If any other user types them, the bot ignores them completely.

| Owner DM Command | Function |
| :--- | :--- |
| `.ownerhelp` | Shows this private command list in your DM |
| `.peek` | Displays live secret info for **all currently active games** (yours and other players'): Mining 3x3 bomb/gem maps, Wordle secret words, Higher/Lower next numbers, Number Guessing targets, Scramble/Math/Emoji/Trivia answers, Memory sequences, Codebreaker secret codes, Closest Wins targets, and Tic-Tac-Toe / Connect 4 best moves |
| `.intel on` / `.intel off` *(or `.god`)* | Toggles automatic stealth DM intel whenever **you** start or advance a round in any game (default: **ON**). In Multiplayer RPS, automatically DMs you your opponent's locked move and the winning counter-pick |
| `.luck on` / `.luck off` | Toggles built-in gameplay advantages for the owner (default: **ON**): Mining silently swaps away bombs if safe tiles remain, Higher/Lower favors your pick, Solo RPS bot plays losing moves, and QuickDraw/Reaction Race gives a subtle millisecond edge |
| `.setalliance <TAG> \| <Full Name> [\| <Footer>]` | Renames your alliance tag, full name, and optional footer live from DM (Owner-only, no public slash command) |
| `.events` | Lists all scheduled events with IDs, repeat intervals, and muted status |
| `.eventmute <event_id>` | Toggles announcements ON/OFF for an event from DM |
| `.eventrepeat <event_id> <days>` | Sets repeat days (`2` = every 2 days, `0` = stop) from DM |
| `.eventdel <event_id>` | Permanently deletes an event from DM |
| `.announce <channel_id> <message>` | Sends a styled alliance announcement embed to any server channel |
| `.setpoints <user_id> <+N\|-N\|N>` | Silently adjusts or sets any player's arcade points (without polluting match history) |
| `.resetuser <user_id>` | Wipes a player's arcade stats and match history |
| `.config` / `.setconfig <key> <value>` | Views or updates any SQLite `server_config` key live |
| `.backup` | Creates a SQLite database backup privately from DM |
| `.status` | Shows current `.intel` / `.luck` toggles and active tracked game count |

---

## Changelog — v11 Audit, Full Live Sync, Command Consolidation & Bug Fixes

1. **100% Live Owner Config & Alliance Name Sync Across Every File:**
   - Replaced all remaining hardcoded `"ROF"`, `"Rise of Farkers"`, `"UTC-2"` / `"UTC-02:00"`, and `"10 minutes"` strings across `cogs/members.py`, `cogs/events.py`, `cogs/admin.py`, `cogs/arcade_core.py`, `cogs/dm_handler.py`, `cogs/launcher.py`, `core/config.py`, `core/permissions.py`, `core/rooms.py`, `bot.py`, and all 8 game cogs (`wordle`, `codebreaker`, `connect4`, `fast_games`, `memory`, `multiplayer_games`, `quickdraw`, `singleplayer_games`).
   - Renaming the alliance privately via Owner DM `.setalliance` now updates Welcome Channel & DM embeds, Event announcements/reminders/modals/lists, Rules, Ranks (`<TAG> Legend`), Game Room IDs (`<TAG>-XXXX`), Profiles, Leaderboards, Assistant replies, and every game screen live without a restart.
   - Changing Game Timezone (`game_tz_offset`) or Default Reminder (`default_reminder_minutes`) via `/admin settings` or `.setconfig` now updates Welcome DMs, Event creation modal labels, Event lists, `/help`, and Assistant replies automatically.
2. **Streamlined Commands & Easier Event Creation UX:**
   - Added `repeat` preset choices (`One-time`, `Every Day`, `Every 2 Days`, `Every 3 Days`, `Weekly`, `Every 14 Days`, `Custom`) and `announce` (`True`/`False`) directly to `/event add`, pre-filling the event modal automatically.
   - Upgraded `/event view` so Admins & Owner get 1-click **✏️ Edit**, **🔕 Mute / Unmute Alerts**, and **🗑️ Delete** buttons directly on the event card.
   - Removed redundant slash commands: `/event list` (use `/events`), `/event repeat` (use `/event add` or `/event edit`), `/event announce` (use `/event add` or 1-click Mute button), `/event cancel` (use `/event delete`), `/wordle_practice` (merged into `/wordle mode:Daily|Practice`), and `/game stats|history|help` (merged into `/profile` with a 1-click **📜 Match History** button and `/games` Game Help).
3. **Critical & Minor Bug Fixes:**
   - Fixed `db.reset_player_stats()` crash (`no such table: player_game_stats`) when running `.resetuser`.
   - Fixed unindented `safe_reply_error` in `cogs/members.py` (`/rules edit`) that triggered a false error message every time the Rules modal opened.
   - Fixed `.setpoints` in `core/owner_stealth.py` to update points directly via `db.adjust_player_points()` without adding fake `"Bonus"` games to player stats or match history.
   - Removed broken unused `load_arcade()` (`NameError: ARCADE_FILE`) in `cogs/arcade_core.py` and dead `db.update_event_reminder()` fallback in `cogs/events.py`.
   - Fixed stale game documentation in `cogs/dm_handler.py` & `cogs/launcher.py` (removed nonexistent `/undercover` and `Emoji Pair Match`, added missing guides for Higher or Lower, Treasure Hunt, Tic-Tac-Toe, and Closest Wins, fixed `/rules view` references).
4. **Discord API & Policy Compliance Verified:**
   - Enforced Discord's 45-character modal title/label cap, 1024-character embed field value cap (safe rules truncation in Welcome DM), 100-character slash command description cap, 5-field modal cap, and 100-command global limit (streamlined to **16** top-level slash commands/groups).
   - Kept slash command descriptions alliance-agnostic so runtime renames never require spamming global `tree.sync()`.

5. **Performance, Timeout Cleanup & Runtime Optimizations:**
   - Added an in-memory `server_config` cache in `core/database.py` (instant reads with zero SQLite open/close overhead per embed/click, updated immediately on `set_config`).
   - Moved `PRAGMA journal_mode=WAL` to run once on DB initialization instead of on every query.
   - Removed redundant per-write legacy JSON rewrites (`arcade_data.json`, `events.json`, `rules.json`) so SQLite is the single fast source of truth.
   - Removed `/admin alliance` (alliance renaming is now strictly private via Owner DM `.setalliance <TAG> | <Full Name> [| <Footer>]`), removed unused `EventSetupView`, streamlined startup to a single global `tree.sync()`, and added `.backup` to private Owner DM controls.
   - Patched `on_timeout` cleanup across all game views (`Connect 4`, `Higher or Lower`, `Treasure Hunt`, `Tic-Tac-Toe`, `Closest Wins`, `Memory`, `Trivia`, `Number Guessing`, `Emoji Guessing`, `Wordle`, `Codebreaker`) so abandoned games immediately unregister chat-input listeners and `.peek` trackers, with a **5-minute (300s)** stale-cleanup ceiling across `chat_input`, `owner_stealth`, and waiting lobbies.
6. **Real-Life 148-Scenario Stress Test & Final Bug Fixes:**
   - Fixed missing `get_alliance_short` import in `cogs/wordle.py` (which caused Wordle & Wordle Practice to crash when rendering the board) and fixed the `_register_chat_session` replacement order so switching from Daily to Practice Wordle keeps the new Practice board active.
   - Hardened Word Scramble (`cogs/singleplayer_games.py`) and Wordle (`cogs/wordle.py`) for 100% case-insensitive matching (including spaced letters like `a p p l e`) and DM `channel_id` fallback resolution across all 4 solo chat-input games.
   - Fixed `cogs/dm_handler.py` so typing `help` or `commands` in DM always returns the Bot Command Guide instead of matching `codebreaker_help` in the Knowledge Base.
   - Passed **148 / 148** real-life simulation scenarios across all **14 cogs** and **8 core modules** (Owner stealth invisibility, live alliance & timezone sync, 30-rule 1024-char Discord limit, 45-char modal cap, malformed/offline recurring events, messy word/text inputs, 20 simultaneous solo players in one channel, 10-player multiplayer lobby chaos, 40-player concurrent SQLite load, and 5-minute stale cleanup).
