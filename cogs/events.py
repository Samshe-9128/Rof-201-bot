# cogs/events.py
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import json
import os
import uuid
from dotenv import load_dotenv

load_dotenv()

OWNER_ID = int(os.getenv("OWNER_ID"))
GUILD_ID = int(os.getenv("GUILD_ID"))
EVENT_CHANNEL_ID = int(os.getenv("EVENT_CHANNEL_ID"))
TZ_OFFSET = float(os.getenv("SERVER_TZ_OFFSET", -2))

SERVER_TZ = timezone(timedelta(hours=TZ_OFFSET))
EVENTS_FILE = "events.json"

def load_events():
    try:
        with open(EVENTS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_events(events):
    with open(EVENTS_FILE, "w") as f:
        json.dump(events, f, indent=4)

def is_admin_or_owner(interaction: discord.Interaction):
    if interaction.user.id == OWNER_ID:
        return True
    # Handle DMs safely
    if not interaction.guild:
        return False
    if interaction.user.guild_permissions.administrator:
        return True
    return False


# ---------- EVENT SETUP MODAL ----------

class EventCreateModal(discord.ui.Modal, title="Schedule New Event"):
    event_name = discord.ui.TextInput(
        label="Event Name",
        placeholder="e.g., Alliance Brawl",
        max_length=50,
        required=True
    )
    event_date = discord.ui.TextInput(
        label="Date (YYYY-MM-DD)",
        placeholder="e.g., 2026-05-15",
        min_length=10,
        max_length=10,
        required=True
    )
    event_time = discord.ui.TextInput(
        label="Time (HH:MM) - Server Time",
        placeholder="e.g., 14:30",
        min_length=5,
        max_length=5,
        required=True
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        # Acknowledge the interaction immediately so it doesn't time out while we process
        await interaction.response.defer(ephemeral=True)

        try:
            # 1. Validate Date and Time Format
            date_str = self.event_date.value.strip()
            time_str = self.event_time.value.strip()
            
            try:
                event_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=SERVER_TZ)
            except ValueError:
                return await interaction.followup.send("❌ **Invalid Date/Time Format!** Please ensure you use `YYYY-MM-DD` for the date and `HH:MM` (24-hour format) for the time.", ephemeral=True)

            # 2. Validate Future Date
            if event_dt <= datetime.now(SERVER_TZ):
                return await interaction.followup.send("❌ **Time Travel Error!** You cannot schedule an event in the past. Please choose a future time.", ephemeral=True)

            # 3. Validate Channel Exists
            target_channel = self.cog.bot.get_channel(EVENT_CHANNEL_ID)
            if not target_channel:
                return await interaction.followup.send("❌ **Configuration Error:** I cannot find the announcement channel. Please check the `EVENT_CHANNEL_ID` in your `.env` file.", ephemeral=True)

            # 4. Send Announcement FIRST (If this fails, we don't save the event)
            try:
                await target_channel.send(
                    f"@everyone 📢 **ROF EVENT ANNOUNCEMENT**\n\n"
                    f"⚔️ **{self.event_name.value}**\n"
                    f"Event starts at **<t:{int(event_dt.timestamp())}:F>**\n"
                    f"*Automatically converts to your local time!*\n\n"
                    f"Get ready, ROF! 🔥",
                    allowed_mentions=discord.AllowedMentions(everyone=True)
                )
            except discord.Forbidden:
                return await interaction.followup.send(f"❌ **Permission Error:** I do not have permission to send messages in {target_channel.mention}. Please check my role permissions.", ephemeral=True)
            except Exception as e:
                return await interaction.followup.send(f"❌ **Discord Error:** Failed to send announcement. `{e}`", ephemeral=True)

            # 5. Save Event to Database
            event_id = str(uuid.uuid4())[:6]
            event_data = {
                "id": event_id,
                "name": self.event_name.value,
                "time": event_dt.isoformat(),
                "channel": EVENT_CHANNEL_ID,
                "reminder_sent": False,
                "creator": interaction.user.id
            }

            self.cog.events.append(event_data)
            save_events(self.cog.events)

            # 6. Success Message
            await interaction.followup.send(
                f"✅ **Success!** Event **{self.event_name.value}** has been scheduled (ID: `{event_id}`).\n"
                f"The announcement was sent to {target_channel.mention}.", 
                ephemeral=True
            )

        except Exception as e:
            # Ultimate safety net for any unexpected Python errors
            print(f"CRITICAL ERROR in EventCreateModal: {e}")
            await interaction.followup.send(f"❌ **Unexpected Error:** Something went wrong while scheduling the event.\n`{e}`", ephemeral=True)


# ---------- EVENT SETUP VIEW ----------

class EventSetupView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Create Event", style=discord.ButtonStyle.success, emoji="➕")
    async def create_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin_or_owner(interaction):
            return await interaction.response.send_message("❌ Only administrators can create events.", ephemeral=True)
        
        try:
            await interaction.response.send_modal(EventCreateModal(self.cog))
        except Exception as e:
            await interaction.response.send_message(f"❌ Could not open the setup menu: {e}", ephemeral=True)


# ---------- COG ----------

class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.events = load_events()
        self.reminder_task.start()

    def cog_unload(self):
        self.reminder_task.cancel()

    @tasks.loop(seconds=30)
    async def reminder_task(self):
        now = datetime.now(SERVER_TZ)
        changed = False

        for event in self.events:
            if event.get("reminder_sent"):
                continue

            try:
                event_dt = datetime.fromisoformat(event["time"])
                reminder_dt = event_dt - timedelta(minutes=30)

                # If event has passed, mark as sent so we stop checking it
                if now >= event_dt:
                    event["reminder_sent"] = True
                    changed = True
                    continue

                # If it's time to remind
                if now >= reminder_dt:
                    channel = self.bot.get_channel(event["channel"])
                    if not channel:
                        channel = await self.bot.fetch_channel(event["channel"])
                    
                    await channel.send(
                        f"@everyone 🔔 **ROF EVENT REMINDER!**\n\n"
                        f"⚔️ **{event['name']}**\n"
                        f"Starts in 30 minutes!\n"
                        f"🕒 Event time: <t:{int(event_dt.timestamp())}:t>\n\n"
                        f"Get your heroes ready! 🔥",
                        allowed_mentions=discord.AllowedMentions(everyone=True)
                    )
                    event["reminder_sent"] = True
                    changed = True
            except discord.NotFound:
                print(f"Warning: Could not find channel {event.get('channel')} for event {event.get('name')}.")
                event["reminder_sent"] = True
                changed = True
            except discord.Forbidden:
                print(f"Warning: Missing permissions to send reminder for event {event.get('name')}.")
                event["reminder_sent"] = True
                changed = True
            except Exception as e:
                print(f"Error processing reminder for {event.get('name')}: {e}")

        if changed:
            save_events(self.events)

    @reminder_task.before_loop
    async def before_reminder(self):
        await self.bot.wait_until_ready()

    # ---------- COMMANDS ----------

    @app_commands.command(name="event", description="Open the Event Setup Panel (Admin/Owner only)")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def event_panel(self, interaction: discord.Interaction):
        if not is_admin_or_owner(interaction):
            return await interaction.response.send_message("❌ Only Server Administrators or the Bot Owner can use this.", ephemeral=True)

        embed = discord.Embed(
            title="⚔️ ROF Event Manager",
            description="Click the button below to schedule a new alliance event.\n\nOnce created, the bot will announce it in the designated channel and remind everyone 30 minutes before it starts.",
            color=discord.Color.blue()
        )
        view = EventSetupView(self)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="events", description="View upcoming events")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def list_events(self, interaction: discord.Interaction):
        try:
            now = datetime.now(SERVER_TZ)
            upcoming = [e for e in self.events if datetime.fromisoformat(e["time"]) > now]

            if not upcoming:
                return await interaction.response.send_message("No upcoming events. ⚔️", ephemeral=True)

            upcoming.sort(key=lambda x: x["time"])
            desc = ""
            for e in upcoming:
                dt = datetime.fromisoformat(e["time"])
                desc += f"**{e['name']}** (ID: `{e.get('id', '???')}`)\n"
                desc += f"🕒 <t:{int(dt.timestamp())}:F> (<t:{int(dt.timestamp())}:R>)\n\n"

            embed = discord.Embed(title="⚔️ ROF UPCOMING EVENTS", description=desc, color=discord.Color.blue())
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error loading events: `{e}`", ephemeral=True)

    @app_commands.command(name="event_cancel", description="Cancel an event (Admin/Owner)")
    @app_commands.describe(event_id="The short ID of the event (e.g. a1b2c3)")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def cancel_event(self, interaction: discord.Interaction, event_id: str):
        if not is_admin_or_owner(interaction):
            return await interaction.response.send_message("❌ Only Administrators can cancel events.", ephemeral=True)

        event = next((e for e in self.events if e.get("id") == event_id), None)
        if not event:
            return await interaction.response.send_message("❌ Event ID not found.", ephemeral=True)

        try:
            self.events.remove(event)
            save_events(self.events)
            await interaction.response.send_message(f"🗑️ Event **{event['name']}** cancelled successfully.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to cancel event: `{e}`", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Events(bot))