# HAV Discord Bot — Haven (Server 201) Gaming & Lands of Jail Assistant

Official Discord bot for the **Haven (`HAV`)** alliance on **Server 201** in **Lands of Jail**, built by **Sam** — combining a **Lands of Jail strategy assistant & upgrade cost calculator**, **22 single-player & multiplayer games**, **automated event scheduling with Game Time → IST conversion**, **onboarding & alliance rules**, **profiles & leaderboards**, and **cloud persistence via MongoDB Atlas** *(with automatic local SQLite fallback)*.

## Quick Setup (FadeHost / Local)

1. **Install dependencies:**

   ```
   pip install -r requirements.txt
   
   ```

   (`discord.py>=2.4.0`, `python-dotenv>=1.0.1`, `pymongo[srv]>=4.6.0`)

2. **Enable Discord Privileged Gateway Intents:**
   In the Discord Developer Portal → your Bot → **Bot** tab → turn ON:

   * **Message Content Intent** *(required for chat-typing games, DM assistant, and private Owner DM commands)*

   * **Server Members Intent** *(required for Welcome onboarding and member lookups)*

3. **Configure `.env` (or FadeHost environment variables):**
   Copy `.env.example` to `.env` and set:

   ```
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

   * **Cloud Persistence (`MONGO_URI`):** When set, all 9 collections (`players`, `game_stats`, `game_history`, `events`, `rules`, `knowledge_base`, `server_config`, `admins`, `audit_logs`) plus Wordle (`wordle_stats`, `wordle_games`, `wordle_daily`) are stored in **MongoDB Atlas** so uploading new code on FadeHost never deletes live data. Leave `MONGO_URI` blank to automatically use local SQLite (`haven_bot.db`).

   * **Slash Command Sync (`AUTO_SYNC_COMMANDS`):** Leave `true` on first boot; you can switch to `false` later and use Owner DM `.sync` whenever you add or change slash commands.

4. **Run the bot:**

   ```
   python bot.py
   
   ```

   On startup, the bot connects to MongoDB (or SQLite), auto-seeds any missing Knowledge Base guides without overwriting custom edits, sets its presence to `Playing /games • Haven (HAV)`, and loads all 14 cogs.

## Lands of Jail AI Assistant & Upgrade Calculators

Members can ask questions in **DMs**, by **`@mentioning` the bot**, or in any configured **Assistant Channel** (`/admin channels`). The assistant stays automatically silent while a player is in an active chat-input game.

### Built-In Upgrade Calculators & Live Lookups

Data is sourced from the [Lands of Jail Unofficial Wiki](https://landsofjail.miraheze.org/wiki/Main_Page) and [LOJ XLab](https://lojxlab.com/upgrades/).

| Feature | Example Member Questions | What the Bot Calculates / Returns | 
| ----- | ----- | ----- | 
| **Exclusive Equipment (Lv. 0–10)** | *"hero equipment lvl 5 to lvl 6"*, *"exclusive gear 0 to 10"* | Exact **Parts** needed (`550` total to max), **SvS Day 4/5 points** (`12,000`/part), running total, and Arrest/War skill rhythm | 
| **Equipment Reformation (Lv. 1–20)** | *"reformation lvl 5 to lvl 10"*, *"ref lvl 16"* | Exact **Precision Gears** (`4,260` total) + **Magnets** (`11,220` from Lv.10+), step breakdown, and SvS points (`6,000`/gear) | 
| **Warden's Office (Lv. 2–30)** | *"warden office lvl 24"*, *"wo 25 to 30"* | Required buildings, Food/Wood/Steel/Gasoline costs, base build time, unlocks, offline cap (12h max at Lv.27), and Power | 
| **Forticlad (FC 1–10)** | *"fc 5 to fc 8"*, *"how many cores for fc 3"* | Office-only & all-buildings **Forticlad Cores** + **Advanced Cores**, prerequisites, and SvS Day 1/2/5 points (`3,000`/core) | 
| **Tome Upgrades (Lv. 0–18)** | *"tome lvl 5 to lvl 12"*, *"tome 0 to 18"* | Exact **Seal of Wisdom**, **Seal of Knowledge**, **Seal of Mystery Tome** (Lv.12+), 6-tome troop set totals, and bonus stat % | 
| **40+ Hero Directory & Gen 1–7** | *"tell me about tyronn"*, *"is whisper good"*, *"gen 5 heroes"* | Troop class, generation/rarity, best role (Rally Leader/Joiner/Garrison/Solo/Utility), and exclusive equipment notes | 
| **SvS Prep Day 1–5 Lookup** | *"svs day 4"*, *"svs prep day 2"* | Exact point values for every task on that specific Preparation Phase day | 
| **Shields, Buffs & Materials** | *"how much is 24h shield"*, *"where to get magnets"* | Diamond prices for Shields, Anti-Scout, Combat/Training/Gathering buffs, and drop sources for Bolts, Magnets, Coils, Gears, and Cores | 
| **Bot Identity & Creator** | *"who are u"*, *"who made u"*, *"tell me about ur self"*, *"which server"* | Introduces itself as **HAV Bot** for **Haven (`HAV`)** on **Server 201**, built by **Sam** | 

### Pre-Loaded Knowledge Base (24 Auto-Seeded Guides)

Admins and Owner can manage topics anytime with `/knowledge add`, `/knowledge edit`, `/knowledge remove`, and `/knowledge list`:

* **Heroes (4):** Rally Leaders (S1–S7), Rally Joiners & 1st-skill/top-4 rules, Best Season Lineups (Rally/Garrison/Solo), Utility & Gathering Heroes

* **Buildings & Systems (4):** Exterior Building Upgrade Order, Interior Prison Rooms & Riot Prevention, Cosmos Hub / Satellites / Overclock, Tome Upgrade Guide

* **Events (5):** Ultimate Trial (Scarlet Butcher / Trial Cage), Supreme Honor (SvS), Crystal Clash Rules & Buildings, Alliance Brawl / Sandsea Conquest / Dreadwaker Overlord / Treasure Barrage, Turmoil Surge

* **Equipment & Strategy (5):** Exclusive Equipment Costs (0–10), Equipment Reformation Costs (1–20), Troop Ratios (Trial Cage / War / Plunder / Garrison), Hero Equipment Priority, Diamonds & Gold Cuffs Spending

* **Alliance, FAQ & About (6):** About HAV Bot (Sam — Server 201), Gift Code Redemption, Shields/Buffs & Upgrade Materials, Event Permissions, HAV Member Responsibilities, Codebreaker Help

## Gaming Arena (`/games`)

### Single-Player Games (Work in Both Server Channels & DMs)

| Game | Command | How to Play | Highlights | 
| ----- | ----- | ----- | ----- | 
| **Wordle (Daily & Practice)** | `/wordle [mode]`, `/games` | Type 5-letter words directly in chat | Daily & unlimited Practice modes, live board + keyboard, streak & guess distribution, Share Result, MongoDB/JSON persistence | 
| **Word Scramble** | `/games` | Type unscrambled words in chat | 3 timed rounds, Easy/Medium/Hard, `hint` or `quit` anytime | 
| **Quick Math** | `/games` | Type numeric answers in chat | 60-second sprint, streak multipliers, Easy/Medium/Hard | 
| **Number Guessing** | `/games` | Type numbers in chat | Live `⬆️` / `⬇️` / `🎉` feedback; Easy (1–50), Medium (1–100), Hard (1–500) | 
| **Emoji Guessing** | `/games` | Type answers in chat | Movies, Games, Animals, Food, Phrases, Objects; 3 attempts + `hint` | 
| **Higher or Lower** | `/higherlower`, `/games` | 1-click buttons | Risk/reward streak scoring (`1–100`) with Cash Out | 
| **Treasure Hunt (Mining 3×3)** | `/treasure`, `/games` | 1-click 3×3 tile grid | 7 hidden gems (`💎`) + 2 bombs (`💣`), Cash Out or Full Clear bonus | 
| **Memory Challenge** | `/memory`, `/games` | 1-click color buttons | Progressive sequence reproduction up to 8 items | 
| **Reaction Speed Test** | `/quickdraw mode:solo`, `/games` | 1-click reaction button | Millisecond timing, false-start detection, personal best & average tracking | 
| **Trivia Challenge** | `/games` | 1-click A/B/C/D buttons | 5 questions across 8 categories with explanations | 
| **Rock Paper Scissors** | `/games` | 1-click buttons | Single Round, Best of 3, or Best of 5 vs. HAV Bot | 

### Multiplayer Games (Server Channels Only — Public Lobbies)

| Game | Command | Players | How to Play | 
| ----- | ----- | ----- | ----- | 
| **Word Guessing Race** | `/games` | 2–10 | Race by typing answers directly in chat across 3 rounds | 
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
| `/profile [member]` | Everyone (Server + DM) | Shows total points, rank (`Bronze` → **`HAV Legend`**), win rate, reaction record, and 1-click **Match History** | 
| `/leaderboard` | Everyone (Server + DM) | Overall, Weekly, and Per-Game rankings | 
| `/rules view|add|edit|remove` | View: All / Edit: Admin | Manages numbered alliance rules | 
| `/admin settings|channels|welcome|permissions` | Admin / Owner | Configures Game Time UTC offset, default reminder minutes, channels, welcome onboarding, admin roster, and audit logs | 
| `/ping` | Everyone (Server + DM) | Displays WebSocket latency (`ms`), bot uptime, active database backend (`MongoDB` / `SQLite`), and active rooms | 
| `/help` | Everyone (Server + DM) | Full interactive command directory | 

* **Automated Welcome Onboarding:** Greets new members in the Welcome channel and sends a structured DM with Haven rules, upcoming events, and a quick-start guide.

* **Private Bug Reports:** Ephemeral post-game prompts and `🐛 Report Bug` modals privately DM `OWNER_ID`, and error messages tag `<@OWNER_ID>`.

## Private Owner-Only DM Controls (OWNER ONLY)

These stealth commands work **only when sent by `OWNER_ID` in a Direct Message to the bot** and are completely invisible to everyone else:

| Owner DM Command | Function | 
| ----- | ----- | 
| `.ownerhelp` | Displays this private command reference | 
| `.peek` | Shows live secret intel for all active games (bomb maps, Wordle words, codes, answers, best board moves) | 
| `.intel on|off` *(or `.god`)* | Toggles automatic stealth DM intel whenever you play | 
| `.luck on|off` | Toggles built-in owner gameplay advantages | 
| `.events` | Lists all scheduled events with IDs, repeat days, and mute status | 
| `.eventmute <event_id>` | Toggles an event's announcements ON/OFF without deleting | 
| `.eventrepeat <event_id> <days>` | Sets repeat interval (`0` to stop repeating) | 
| `.eventdel <event_id>` | Permanently deletes an event | 
| `.announce <channel_id> <message>` | Sends a styled `HAV` alliance announcement embed to any channel | 
| `.setpoints <user_id> <+N|-N|N>` | Adjusts or sets any player's arcade points cleanly | 
| `.resetuser <user_id>` | Wipes a player's arcade stats and match history | 
| `.config` / `.setconfig <key> <value>` | Views or updates `server_config` keys live | 
| `.backup` | Creates a backup (`.json` on MongoDB or `.db` on SQLite) and DMs the file directly to you | 
| `.reload <cog|all>` | Hot-reloads a cog (or all cogs) without restarting the bot | 
| `.sync` | Manually syncs global slash commands with Discord | 
| `.status` | Shows `.intel`/`.luck` toggles, database backend, uptime, and active tracked games | 

## Reliability & Performance Highlights

* **Dual-Backend Persistence:** Full **MongoDB Atlas** backend (`core/mongo_database.py`) with automatic **SQLite WAL** connection-pooled fallback (`core/database.py`), plus `.gitignore` rules keeping live data files out of Git.

* **Fast Hot Paths:** In-memory `server_config` cache, O(1) cached `assistant_channels` set, zero-lock `HAV` branding helpers, indexed leaderboard & reminder queries, and atomic Wordle JSON writes.

* **Hardened Stability:** 3-second cooldowns on high-traffic slash commands, cross-game multiplayer room locks, ghost-player eviction on `on_member_remove`, 5-minute stale session cleanup, clean `db.close()` shutdown in `bot.close()`, and **1,070/1,070** verified Lands of Jail assistant test coverage.