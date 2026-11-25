# HAV Discord Bot — Haven (Server 201) Gaming & Event Assistant

Official Discord bot for the **Haven (`HAV`)** alliance on **Server 201**, built by **Sam** — featuring **22 single-player & multiplayer Discord games**, **automated event scheduling with Game Time → India Time (`IST`) conversion**, **a clean human-style assistant for game rules & event timings**, **onboarding & alliance rules**, **profiles & leaderboards**, and **cloud persistence via MongoDB Atlas** *(with automatic local SQLite fallback)*.

## Quick Setup (FadeHost / Local)

1. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

   (Requires **Python 3.11+** — installs `discord.py>=2.7.1`, `python-dotenv>=1.2.4`, `pymongo[srv]>=4.20.1`)

2. **Enable Discord Privileged Gateway Intents:**
   In the Discord Developer Portal → your Bot → **Bot** tab → turn ON:
   * **Message Content Intent** *(required for chat-typing games, DM/mention assistant, and private Owner DM commands)*
   * **Server Members Intent** *(required for Welcome onboarding and member lookups)*

3. **Configure `.env` (or FadeHost environment variables):**
   Copy `.env.example` to `.env` and fill in your values:

   ```env
   DISCORD_TOKEN=your_bot_token_here
   GUILD_ID=your_server_id
   OWNER_ID=your_discord_user_id
   EVENT_CHANNEL_ID=0
   WELCOME_CHANNEL_ID=0
   RULES_CHANNEL_ID=0
   SERVER_TZ_OFFSET=-2
   MONGO_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
   MONGO_DB_NAME=haven_bot
   AUTO_SYNC_COMMANDS=true
   ```

   * **Cloud Persistence (`MONGO_URI`):** Stores all 9 collections (`players`, `game_stats`, `game_history`, `events`, `rules`, `knowledge_base`, `server_config`, `admins`, `audit_logs`) plus Wordle state (`wordle_stats`, `wordle_games`, `wordle_daily`) in **MongoDB Atlas** so uploading new code on FadeHost never wipes live data. Leave `MONGO_URI` blank to automatically use local SQLite (`haven_bot.db`).
   * **Slash Command Sync (`AUTO_SYNC_COMMANDS`):** Leave `true` on first boot; you can switch to `false` later and run `.sync` via Owner DM whenever slash commands change.

4. **Run the bot:**

   ```bash
   python bot.py
   ```

   On startup, the bot connects to MongoDB (or SQLite), loads all 14 cogs, sets presence to `Playing /games • Haven (HAV)`, and stays ready for both server channels and DMs.

## Haven Chat Assistant (Games, Event Timings & Rules)

Members can chat naturally with the bot in **DMs**, by **`@mentioning` the bot** anywhere in the server, or in any configured **Assistant Channel** (`/admin channels`). The assistant replies in plain Discord chat (staying automatically silent during active chat-input games) and focuses on:

* **Event Timings:** Ask *"When is the next event?"*, *"When is Surge?"*, or *"event timing"* to get exact **Game Time (`UTC-02:00`)**, **India Time (`IST`)**, and local Discord timestamps.
* **How to Play Any Haven Bot Game:** Ask *"how to play wordle"*, *"how to play c4"*, *"how to play 4 digit game"*, *"how does reaction race work?"*, or *"what games can I play?"* for quick, plain-English instructions.
* **Alliance Rules & Bot Info:** Ask *"what are the alliance rules?"*, *"who made you?"*, or *"help"*.
* **Custom Admin Entries (`/knowledge`):** Admins and Owner can still add, edit, list, or remove custom alliance notes anytime with `/knowledge add`, `/knowledge edit`, `/knowledge list`, and `/knowledge remove`.

## Gaming Arena (`/games`)

### Single-Player Games (Server Channels & DMs)

| Game | Command | How to Play | Highlights |
| ----- | ----- | ----- | ----- |
| **Wordle (Daily & Practice)** | `/wordle [mode]`, `/games` | Type 5-letter words in chat | Daily & Practice modes, live board + keyboard, streaks, Share Result, MongoDB/JSON persistence |
| **Word Scramble** | `/games` | Type unscrambled words in chat | 3 timed rounds, Easy/Medium/Hard, `hint` or `quit` anytime |
| **Quick Math** | `/games` | Type numeric answers in chat | 60-second sprint, streak multipliers, Easy/Medium/Hard |
| **Number Guessing** | `/games` | Type numbers in chat | Live `⬆️` / `⬇️` / `🎉` feedback; Easy (1–50), Medium (1–100), Hard (1–500) |
| **Emoji Guessing** | `/games` | Type answers in chat | Movies, Games, Animals, Food, Phrases, Objects; 3 attempts + `hint` |
| **Higher or Lower** | `/higherlower`, `/games` | 1-click buttons | Risk/reward streak scoring (`1–100`) with Cash Out |
| **Treasure Hunt (3×3)** | `/treasure`, `/games` | 1-click 3×3 tile grid | 7 hidden gems (`💎`) + 2 bombs (`💣`), Cash Out or Full Clear bonus |
| **Memory Challenge** | `/memory`, `/games` | 1-click color buttons | Progressive sequence reproduction up to 8 steps |
| **Reaction Speed Test** | `/quickdraw mode:solo`, `/games` | 1-click reaction button | Millisecond timing, false-start detection, personal best & average |
| **Trivia Challenge** | `/games` | 1-click A/B/C/D buttons | 5 questions across 8 categories with explanations |
| **Rock Paper Scissors** | `/games` | 1-click buttons | Single Round, Best of 3, or Best of 5 vs. HAV Bot |

### Multiplayer Games (Server Channels Only — Public Lobbies)

| Game | Command | Players | How to Play |
| ----- | ----- | ----- | ----- |
| **Word Guessing Race** | `/games` | 2–10 | Race by typing answers in chat across 3 rounds |
| **Quick Math Battle** | `/games` | 2–10 | Type answers in chat; points + speed bonus |
| **Multiplayer Emoji Guessing** | `/games` | 2–10 | First correct chat answer wins the round |
| **Four-Digit Codebreaker** | `/codebreaker`, `/games` | 1–8 or 1v1 | Direct 4-digit typing in Solo/1v1; private modal popups in multiplayer rooms |
| **Closest Wins** | `/games` | 2–10 | 20-second simultaneous secret guess (`1–100`) |
| **Trivia Battle** | `/games` | 2–10 | 5 rounds with private locked-in answers & live scoreboard |
| **Reaction Race** | `/quickdraw`, `/games` | 2–10 | Fastest valid click after the green READY signal |
| **Multiplayer RPS** | `/games` | 2 (1v1) | Best of 3 or 5 with simultaneous reveal |
| **Tic-Tac-Toe** | `/tictactoe`, `/games` | 2 (1v1) | 3×3 grid duel with `🏳 Forfeit` button |
| **Connect 4** | `/connect4`, `/games` | 2 (1v1) | 7×6 strategy grid with `🏳 Forfeit` button |

## Alliance Events, Profiles, Rules & Admin Tools

| Command | Access | Description |
| ----- | ----- | ----- |
| `/events` | Everyone (Server + DM) | Lists upcoming events in **Game Time (`UTC-02:00`)**, **India Time (`IST`)**, and local Discord timestamps |
| `/event add [repeat] [channel] [announce]` | Admin / Owner | Creates one-time or recurring events (`repeat_days` auto-advances after start) with optional silent mode |
| `/event edit [event_id]` | Admin / Owner | Edits name, date, time, reminder lead time, or repeat interval |
| `/event view [event_id]` | Everyone | Shows full event details; Admins/Owner get 1-click **Edit**, **Mute/Unmute**, and **Delete** buttons |
| `/event delete [event_id]` | Admin / Owner | Permanently deletes an event with confirmation |
| `/profile [member]` | Everyone (Server + DM) | Shows total points, rank (`Recruit` → **`HAV Legend`**), win rate, reaction record, and **Match History** |
| `/leaderboard` | Everyone (Server + DM) | Overall, Weekly, and Per-Game rankings |
| `/rules view\|add\|edit\|remove` | View: All / Edit: Admin | Manages numbered alliance rules |
| `/knowledge list\|add\|edit\|remove` | List: All / Edit: Admin | Manages custom alliance Q&A entries |
| `/admin settings\|channels\|welcome\|permissions` | Admin / Owner | Configures Game Time UTC offset, default reminder minutes, channels, welcome onboarding, admin roster, and audit logs |
| `/ping` | Everyone (Server + DM) | Displays WebSocket latency (`ms`), uptime, database backend (`MongoDB` / `SQLite`), and active rooms |
| `/help` | Everyone (Server + DM) | Full interactive command directory |

## Private Owner-Only DM Controls (OWNER ONLY)

These stealth commands work **only when sent by `OWNER_ID` in a Direct Message to the bot** and are invisible to everyone else:

| Owner DM Command | Function |
| ----- | ----- |
| `.ownerhelp` | Displays the private command reference |
| `.peek` | Shows live secret intel for active games |
| `.intel on\|off` *(or `.god`)* | Toggles automatic stealth DM intel whenever you play |
| `.luck on\|off` | Toggles built-in owner gameplay advantages |
| `.events` | Lists all scheduled events with IDs, repeat days, and mute status |
| `.eventmute <event_id>` | Toggles an event's announcements ON/OFF without deleting |
| `.eventrepeat <event_id> <days>` | Sets repeat interval (`0` to stop repeating) |
| `.eventdel <event_id>` | Permanently deletes an event |
| `.announce <channel_id> <message>` | Sends a styled `HAV` alliance announcement embed to any channel |
| `.setpoints <user_id> <+N\|-N\|N>` | Adjusts or sets any player's arcade points |
| `.resetuser <user_id>` | Wipes a player's arcade stats and match history |
| `.config` / `.setconfig <key> <value>` | Views or updates `server_config` keys live |
| `.backup` | Creates a backup (`.json` on MongoDB or `.db` on SQLite) and DMs it directly to you |
| `.reload <cog\|all>` | Hot-reloads a cog (or all cogs) without restarting the bot |
| `.sync` | Manually syncs global slash commands with Discord |
| `.status` | Shows `.intel`/`.luck` toggles, database backend, uptime, and active tracked games |

## Performance & Stability Highlights

* **Zero-Lag Event Loop:** Assistant queries run via `asyncio.to_thread` with pre-compiled regexes, zero-DB fast paths for greetings/games/identity, and a 15-second TTL cache for events and custom knowledge entries so MongoDB Atlas reads never stutter active games.
* **Dual-Backend Persistence:** Full **MongoDB Atlas** backend (`core/mongo_database.py`) with automatic **SQLite WAL** connection-pooled fallback (`core/database.py`), plus `.gitignore` keeping live data files out of Git.
* **Hardened Stability:** 2-second mention cooldown, 3-second cooldowns on high-traffic slash commands, cross-game multiplayer room locks, ghost-player eviction on `on_member_remove`, 5-minute stale session cleanup, and clean `db.close()` shutdown in `bot.close()`.