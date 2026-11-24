# HAV Discord Bot — Haven Gaming & Alliance Management System

Official Discord bot for the **Haven (HAV)** alliance — covering welcomes, scheduled events, alliance rules, 22 single-player & multiplayer games, player profiles, leaderboards, and the Alliance AI Assistant, powered by **Python 3.11+**, **discord.py 2.4+**, and **MongoDB Atlas** *(with automatic SQLite fallback locally)*.

---

## Quick Setup (FadeHost / Local)

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   (`discord.py>=2.4.0`, `python-dotenv>=1.0.1`, `pymongo[srv]>=4.6.0`)
2. **Enable required Discord Intents:**
   In the Discord Developer Portal → your Bot application → **Bot** tab → **Privileged Gateway Intents**, turn ON:
   - **Message Content Intent** *(required for natural chat-typing games, DM assistant, and owner DM commands)*
   - **Server Members Intent** *(required for welcome onboarding and member lookups)*
3. **Configure `.env` (or FadeHost Startup / Environment variables):**
   Copy `.env.example` to `.env` and fill in:
   - `DISCORD_TOKEN` — your Discord bot token
   - `GUILD_ID` — your server ID
   - `OWNER_ID` — your Discord User ID
   - `MONGO_URI` — your MongoDB Atlas `mongodb+srv://...` connection string *(stores all stats, events, rules, knowledge base, config, and Wordle data in the cloud so pushing new code on FadeHost never deletes your data; leave blank to use local `haven_bot.db` SQLite automatically)*
   - `MONGO_DB_NAME` — `haven_bot` *(optional)*
   - `AUTO_SYNC_COMMANDS` — `true` on first boot *(you can switch to `false` later and use Owner DM `.sync` whenever you change slash commands)*
   - Optional channel IDs: `EVENT_CHANNEL_ID`, `WELCOME_CHANNEL_ID`, `RULES_CHANNEL_ID`, `SERVER_TZ_OFFSET=-2`
4. **Run the bot:**
   ```bash
   python bot.py
   ```
   On startup, the bot connects to **MongoDB** (if `MONGO_URI` is set) or initializes local **SQLite (`haven_bot.db`)**, sets its status to `Playing /games • Haven (HAV)`, syncs global slash commands, and loads all 14 cogs.

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

## Alliance Events & Scheduling

All events automatically display **Game Time** (configured via `/admin settings`, default `UTC-02:00`), **India Time (`Asia/Kolkata` / IST)**, and each member's local Discord timestamp.

| Command | Access | What It Does |
| :--- | :--- | :--- |
| `/events` | Everyone (Server + DM) | Lists all upcoming scheduled events with countdowns, repeat schedule, and alert status |
| `/event add [repeat] [channel] [announce]` | Admin / Owner | Pick an optional repeat preset (`One-time`, `Every Day`, `Every 2 Days`, `Every 3 Days`, `Weekly`, `Every 14 Days`, or `Custom`) and optional silent creation (`announce: False`), then fill in the popup |
| `/event edit [event_id]` | Admin / Owner | Edit any scheduled event's name, date, time, reminder, or repeat interval |
| `/event view [event_id]` | Everyone | Shows full details and timezone conversions. Admins & Owner also get 1-click **✏️ Edit**, **🔕 Mute / Unmute Alerts**, and **🗑️ Delete** buttons |
| `/event delete [event_id]` | Admin / Owner | Permanently deletes an event (with confirmation) |
| `/ping` | Everyone (Server + DM) | Shows bot latency (`ms`), uptime, active database backend (`MongoDB` or `SQLite`), and active rooms |

---

## Private Owner-Only Controls (OWNER ONLY — DO NOT SHARE PUBLICLY)

These stealth commands **only work when sent by `OWNER_ID` in a Direct Message to the bot**. They have **no slash commands, no visible buttons, and no public `/help` entries**.

| Owner DM Command | Function |
| :--- | :--- |
| `.ownerhelp` | Shows this private command list in your DM |
| `.peek` | Displays live secret info for all currently active games |
| `.intel on` / `.intel off` *(or `.god`)* | Toggles automatic stealth DM intel whenever you play |
| `.luck on` / `.luck off` | Toggles built-in gameplay advantages for the owner |
| `.events` | Lists all scheduled events with IDs, repeat intervals, and muted status |
| `.eventmute <event_id>` | Toggles announcements ON/OFF for an event from DM |
| `.eventrepeat <event_id> <days>` | Sets repeat days (`2` = every 2 days, `0` = stop) from DM |
| `.eventdel <event_id>` | Permanently deletes an event from DM |
| `.announce <channel_id> <message>` | Sends a styled alliance announcement embed to any server channel |
| `.setpoints <user_id> <+N\|-N\|N>` | Silently adjusts or sets any player's arcade points |
| `.resetuser <user_id>` | Wipes a player's arcade stats and match history |
| `.config` / `.setconfig <key> <value>` | Views or updates any `server_config` key live |
| `.backup` | Creates a backup (`.json` on MongoDB or `.db` on SQLite) and DMs the file to you |
| `.reload <cog\|all>` | Hot-reloads a cog (or all cogs) without restarting the bot |
| `.sync` | Manually syncs global slash commands with Discord |
| `.status` | Shows stealth settings, database backend, uptime, and active tracked games |

---

## Changelog — v15 MongoDB Cloud Persistence & Minimal Dev Essentials

1. **Full MongoDB Atlas Support (`core/mongo_database.py`):**
   - Set `MONGO_URI` in `.env` (or FadeHost environment variables) to store all 9 collections (`players`, `game_stats`, `game_history`, `events`, `rules`, `knowledge_base`, `server_config`, `admins`, `audit_logs`) plus Wordle (`wordle_stats`, `wordle_games`, `wordle_daily`) in MongoDB so code updates never wipe live data.
   - Automatically falls back to local SQLite (`haven_bot.db`) when `MONGO_URI` is left blank.
   - Updated `.gitignore` to exclude `*.db` and runtime JSON files so Git pushes only carry code.
2. **Minimal Developer Essentials:**
   - Added default bot presence (`Playing /games • Haven (HAV)`), `/ping` with latency & uptime, Owner DM `.reload <cog|all>` hot-reloading, Owner DM `.sync` + `AUTO_SYNC_COMMANDS` toggle, `.backup` DM file attachment, 3-second cooldowns on high-traffic slash commands (`/games`, `/help`, `/ping`, `/profile`, `/leaderboard`, `/events`), and clean `db.close()` shutdown in `bot.close()`.
