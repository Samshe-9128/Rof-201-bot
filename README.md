# 🛡️ ROF Discord Bot — Gaming & Alliance Management System

Official Discord bot for the **Rise of Farkers (ROF)** alliance, powered by **Python 3.11+** and **discord.py 2.4+** (slash commands, interactive Views, Buttons, Select Menus, and Modals).

## Quick Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in your `DISCORD_TOKEN`, `GUILD_ID`, `OWNER_ID`, and channel IDs.
3. Run the bot:
   ```bash
   python bot.py
   ```
   On first startup, the bot automatically initializes `rof_bot.db` (SQLite with WAL mode) and migrates any legacy `.json` data.

## Key Commands

- **Fast & Interactive Games (Single-player games also work in DMs!):** `/games`, `/higherlower`, `/treasure`, `/tictactoe`, `/codebreaker`, `/quickdraw`, `/wordle`, `/wordle_practice`, `/memory`, `/connect4`, `/game stats`, `/game history`, `/game help`
- **Profiles & Leaderboards:** `/profile`, `/leaderboard`
- **Events (`UTC-2` & `Asia/Kolkata`):** `/events`, `/event add`, `/event edit`, `/event cancel`, `/event delete`, `/event view`, `/event list`
- **Rules & Onboarding:** `/rules view`, `/rules add`, `/rules edit`, `/rules remove`
- **Alliance AI Assistant:** `/knowledge add`, `/knowledge edit`, `/knowledge remove`, `/knowledge list` (plus natural language in DMs & configured channels)
- **Administration & Security:** `/admin settings`, `/admin channels`, `/admin welcome`, `/admin permissions`
