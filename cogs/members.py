# cogs/members.py
import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from datetime import datetime, timezone, timedelta

load_dotenv_env = os.getenv("SERVER_TZ_OFFSET", "-2")
SERVER_TZ = timezone(timedelta(hours=float(load_dotenv_env)))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCADE_FILE = os.path.join(BASE_DIR, 'arcade_data.json')
WORDLE_STATS_FILE = os.path.join(BASE_DIR, 'wordle_stats.json')
WORDLE_GAMES_FILE = os.path.join(BASE_DIR, 'wordle_games.json')
EVENTS_FILE = os.path.join(BASE_DIR, 'events.json')
RULES_FILE = os.path.join(BASE_DIR, 'rules.json')
GUILD_ID = int(os.getenv("GUILD_ID"))

DEFAULT_RULES = (
    "**1.** Respect all alliance members.\n"
    "**2.** Participate in Alliance Brawls and SVS.\n"
    "**3.** No spamming or drama in the chats.\n"
    "**4.** Have fun and play as a team! 🔥\n\n"
    "*Use `/rof setrules` to update these rules.*"
)

def load_rules():
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f).get("rules", DEFAULT_RULES)
        except:
            return DEFAULT_RULES
    return DEFAULT_RULES

def save_rules(text):
    with open(RULES_FILE, 'w', encoding='utf-8') as f:
        json.dump({"rules": text}, f, indent=4)


class RulesModal(discord.ui.Modal, title="Set ROF Alliance Rules"):
    rules_input = discord.ui.TextInput(
        label="Enter the new rules below:",
        style=discord.TextStyle.paragraph,
        placeholder="Type your rules here. You can use **bold**, *italics*, and new lines.",
        min_length=5,
        max_length=4000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        save_rules(self.rules_input.value)
        await interaction.response.send_message("✅ **Rules updated successfully!** All new members will receive these in their welcome DM.", ephemeral=True)


class Members(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Sends a Welcome DM with Rules and Upcoming Events."""
        if member.guild.id != GUILD_ID:
            return

        print(f"👋 {member.name} joined. Sending Welcome DM...")

        # 1. Load upcoming events
        events_text = "No upcoming events scheduled right now."
        if os.path.exists(EVENTS_FILE):
            try:
                with open(EVENTS_FILE, 'r') as f:
                    events = json.load(f)
                
                now = datetime.now(SERVER_TZ)
                upcoming = [e for e in events if datetime.fromisoformat(e["time"]) > now]
                upcoming.sort(key=lambda x: x["time"])

                if upcoming:
                    events_text = ""
                    for e in upcoming[:4]: # Show max 4 events
                        dt = datetime.fromisoformat(e["time"])
                        events_text += f"⚔️ **{e['name']}**\n🕒 <t:{int(dt.timestamp())}:F> (<t:{int(dt.timestamp())}:R>)\n\n"
            except Exception as err:
                print(f"Error reading events for welcome DM: {err}")

        # 2. Build the Welcome Embed
        embed = discord.Embed(
            title=f"🛡️ Welcome to ROF, {member.display_name}!",
            description=(
                f"We are glad to have you in the **Rise of Farkers** alliance.\n"
                f"Here is everything you need to know to get started."
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        # 3. Load rules dynamically
        current_rules = load_rules()
        embed.add_field(name="📜 Guild Rules", value=current_rules, inline=False)
        embed.add_field(name="📅 Upcoming Events", value=events_text, inline=False)
        
        embed.add_field(
            name="🎮 ROF Arcade", 
            value="We have custom mini-games! Type `/wordle`, `/quickdraw`, or `/connect4` in the server to play and earn Arcade Points.", 
            inline=False
        )
        
        embed.set_footer(text=f"Your member ID: {member.id} | Rise of Farkers")

        # 4. Send the DM
        try:
            await member.send(embed=embed)
            print(f"✅ Welcome DM successfully sent to {member.name}")
        except discord.Forbidden:
            print(f"❌ Failed to DM {member.name}. They have DMs from server members turned off.")
        except Exception as e:
            print(f"❌ Error sending DM to {member.name}: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Wipes stats when a member leaves the server."""
        if member.guild.id != GUILD_ID:
            return

        print(f"🚪 {member.name} left the server. Wiping their data...")
        uid = str(member.id)
        
        files_to_clean = [ARCADE_FILE, WORDLE_STATS_FILE, WORDLE_GAMES_FILE]
        
        for filepath in files_to_clean:
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    if uid in data:
                        del data[uid]
                        with open(filepath, 'w') as f:
                            json.dump(data, f, indent=4)
                except Exception as e:
                    print(f"Error wiping data in {filepath}: {e}")


# --- Command Group ---
# Notice we put guild_ids here at the parent level!
rof_group = app_commands.Group(name="rof", description="ROF Alliance Commands", guild_ids=[GUILD_ID])

@rof_group.command(name="rules", description="View the ROF Alliance rules")
async def view_rules(interaction: discord.Interaction):
    current_rules = load_rules()
    embed = discord.Embed(title="📜 ROF Alliance Rules", description=current_rules, color=discord.Color.blue())
    embed.set_footer(text="Rise of Farkers")
    await interaction.response.send_message(embed=embed)

@rof_group.command(name="setrules", description="Set the ROF Alliance rules (Admin only)")
@app_commands.default_permissions(administrator=True) 
async def set_rules(interaction: discord.Interaction):
    if interaction.user.id != int(os.getenv("OWNER_ID")) and not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only the owner or an admin can change the rules.", ephemeral=True)
    
    await interaction.response.send_modal(RulesModal())


async def setup(bot):
    bot.tree.add_command(rof_group)
    await bot.add_cog(Members(bot))