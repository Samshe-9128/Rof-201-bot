# cogs/undercover.py
import random
import discord
from discord import app_commands
from discord.ext import commands

from core.config import ROFColors
from core.database import db
from core.rooms import MultiplayerRoom, RoomLobbyView, room_manager
from core.ui import rof_embed

WORDS = [
    ("Apple", "Pear"),
    ("Cat", "Dog"),
    ("Car", "Truck"),
    ("Coffee", "Tea"),
    ("Sun", "Moon"),
    ("Pizza", "Burger"),
    ("Guitar", "Violin"),
    ("Beach", "Desert"),
]


class UndercoverVote(discord.ui.View):
    def __init__(self, cog, players, spy, word_pair):
        super().__init__(timeout=180)
        self.cog = cog
        self.players = players
        self.spy = spy
        self.word_pair = word_pair
        self.votes = {}

        options = [discord.SelectOption(label=p.display_name, value=str(p.id)) for p in players]
        self.select = discord.ui.Select(placeholder="Who is the Spy?", options=options)
        self.select.callback = self.vote_callback
        self.add_item(self.select)

    async def vote_callback(self, interaction: discord.Interaction):
        if interaction.user.id not in [p.id for p in self.players]:
            return await interaction.response.send_message("You are not playing in this match!", ephemeral=True)

        self.votes[interaction.user.id] = int(self.select.values[0])
        await interaction.response.send_message("✅ Vote locked in!", ephemeral=True)

        if len(self.votes) == len(self.players):
            self.stop()
            await self.cog.tally_votes(interaction.channel, self.players, self.votes, self.spy, self.word_pair)


class StartVoteView(discord.ui.View):
    def __init__(self, cog, players, spy, word_pair):
        super().__init__(timeout=300)
        self.cog = cog
        self.players = players
        self.spy = spy
        self.word_pair = word_pair

    @discord.ui.button(label="Start Voting", style=discord.ButtonStyle.danger, emoji="🗳️")
    async def vote_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [p.id for p in self.players]:
            return await interaction.response.send_message("You are not playing!", ephemeral=True)

        self.stop()
        embed = rof_embed(
            title="🗳️ ROF Undercover — Voting Started",
            description="Select who you suspect is the Spy from the dropdown menu below!",
            color=ROFColors.ACCENT,
        )
        await interaction.response.edit_message(embed=embed, view=None)
        vote_view = UndercoverVote(self.cog, self.players, self.spy, self.word_pair)
        await interaction.channel.send("Cast your votes below:", view=vote_view)


class Undercover(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def open_undercover_room(self, interaction: discord.Interaction):
        existing = room_manager.get_player_active_room(interaction.user.id, "undercover")
        if existing:
            return await interaction.response.send_message(
                f"⚠️ You are already in an active Undercover room (`{existing.room_id}`).",
                ephemeral=True,
            )

        room = room_manager.create_room(
            game_key="undercover",
            game_title="Undercover (Who's the Spy)",
            host=interaction.user,
            min_players=3,
            max_players=6,
        )

        async def _on_start(start_inter: discord.Interaction, active_room: MultiplayerRoom):
            await start_inter.response.edit_message(embed=lobby.build_embed(), view=None)
            room_manager.close_room(active_room.room_id)
            await self.start_game(start_inter.channel, active_room.players)

        lobby = RoomLobbyView(
            room=room,
            on_start_callback=_on_start,
            extra_description="🕵️ **Players:** 3–6 players\n💬 Everyone gets a secret word via DM, except the Spy who gets a slightly different word!",
        )
        await interaction.response.send_message(embed=lobby.build_embed(), view=lobby)
        try:
            room.message = await interaction.original_response()
        except Exception:
            pass

    @app_commands.command(name="undercover", description="Start a game of Who's the Spy (3-6 players)")
    async def undercover(self, interaction: discord.Interaction):
        await self.open_undercover_room(interaction)

    async def start_game(self, channel, players):
        pair = random.choice(WORDS)
        civilian_word, spy_word = pair
        spy = random.choice(players)

        failed_dms = []
        for p in players:
            try:
                word = spy_word if p.id == spy.id else civilian_word
                role = "SPY 🤫" if p.id == spy.id else "CIVILIAN 👤"
                await p.send(
                    f"🕵️ **ROF Undercover Started!**\n"
                    f"Your secret word is: **{word}**\n"
                    f"Your role: **{role}**\n\n"
                    f"*Describe your word in the server channel without saying the word itself!*"
                )
            except Exception:
                failed_dms.append(p.mention)

        if failed_dms:
            return await channel.send(
                f"⚠️ Could not DM {', '.join(failed_dms)}. Please enable DMs from server members and try again."
            )

        embed = rof_embed(
            title="🕵️ ROF UNDERCOVER STARTED",
            description=(
                "Everyone has been DMed a secret word.\n"
                "One of you is the **Spy** and received a slightly different word!\n\n"
                "**Take turns describing your word in the chat.**\n"
                "When ready, click the button below to vote."
            ),
            color=ROFColors.WARNING,
        )
        view = StartVoteView(self, players, spy, pair)
        await channel.send(embed=embed, view=view)

    async def tally_votes(self, channel, players, votes, spy, word_pair):
        counts = {}
        for target_id in votes.values():
            counts[target_id] = counts.get(target_id, 0) + 1

        max_votes = max(counts.values())
        eliminated = [pid for pid, c in counts.items() if c == max_votes]
        eliminated_player = discord.utils.get(players, id=random.choice(eliminated))
        civilian_word, spy_word = word_pair
        arcade = self.bot.get_cog("ArcadeCore")

        if eliminated_player and eliminated_player.id == spy.id:
            embed = rof_embed(
                title="🔍 ROF Undercover — Voting Results",
                description=(
                    f"🎯 **Civilians Win!** {eliminated_player.mention} was caught as the Spy!\n"
                    f"**Words:** Civilian = `{civilian_word}` | Spy = `{spy_word}`"
                ),
                color=ROFColors.SUCCESS,
            )
            for p in players:
                won = p.id != spy.id
                db.record_game_result(
                    user_id=p.id,
                    game_name="Undercover",
                    result="win" if won else "loss",
                    score=30 if won else 0,
                    points_earned=30 if won else 5,
                    attempts=1,
                    mode="multi",
                    username=p.display_name,
                )
        else:
            elim_name = eliminated_player.mention if eliminated_player else "Nobody"
            embed = rof_embed(
                title="🔍 ROF Undercover — Voting Results",
                description=(
                    f"❌ **Spy Wins!** {elim_name} was innocent.\n"
                    f"The Spy was actually **{spy.mention}**!\n"
                    f"**Words:** Civilian = `{civilian_word}` | Spy = `{spy_word}`"
                ),
                color=ROFColors.ERROR,
            )
            for p in players:
                won = p.id == spy.id
                db.record_game_result(
                    user_id=p.id,
                    game_name="Undercover",
                    result="win" if won else "loss",
                    score=50 if won else 0,
                    points_earned=50 if won else 5,
                    attempts=1,
                    mode="multi",
                    username=p.display_name,
                )

        if arcade:
            arcade.reload_cache()
        await channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Undercover(bot))