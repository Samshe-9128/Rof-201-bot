# cogs/undercover.py
import random
import traceback
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


# ---------- vote view ----------

class UndercoverVote(discord.ui.View):
    def __init__(self, cog, players, spy, word_pair):
        super().__init__(timeout=180)
        self.cog = cog
        self.players = list(players)              # fix E
        self.player_ids = {p.id for p in self.players}
        self.spy = spy
        self.word_pair = word_pair
        self.votes = {}
        self.tallied = False
        self.message = None

        options = [
            discord.SelectOption(label=p.display_name, value=str(p.id))
            for p in self.players
        ]
        self.select = discord.ui.Select(placeholder="Who is the Spy?", options=options)
        self.select.callback = self.vote_callback
        self.add_item(self.select)

    async def vote_callback(self, interaction: discord.Interaction):
        # Already tallied — stop processing.
        if self.tallied:
            return await interaction.response.send_message(
                "Voting has already ended.", ephemeral=True
            )
        if interaction.user.id not in self.player_ids:
            return await interaction.response.send_message(
                "You are not playing in this match!", ephemeral=True
            )

        # fix F: validate target
        try:
            target_id = int(self.select.values[0])
        except (ValueError, IndexError):
            return await interaction.response.send_message(
                "Invalid vote target.", ephemeral=True
            )
        if target_id not in self.player_ids:
            return await interaction.response.send_message(
                "Invalid vote target.", ephemeral=True
            )

        self.votes[interaction.user.id] = target_id

        remaining = len(self.players) - len(self.votes)
        suffix = (
            f" ({remaining} vote{'s' if remaining != 1 else ''} remaining)"
            if remaining else ""
        )
        try:
            await interaction.response.send_message(
                f"✅ Vote locked in!{suffix}", ephemeral=True
            )
        except Exception as e:
            print(f"[UNDERCOVER] vote ack failed: {e}")

        # fix A: double-guard on `not self.tallied` so simultaneous
        # last-two-voter callbacks can't both trigger a tally.
        if len(self.votes) == len(self.players) and not self.tallied:
            self.tallied = True
            self.stop()

            # Cleanup the original vote message (if we can).
            if self.message:
                try:
                    await self.message.edit(
                        content="🗳️ *Voting closed — tallying results...*",
                        view=None,
                    )
                except Exception as e:
                    print(f"[UNDERCOVER] vote-message cleanup failed: {e}")

            # fix B: don't let a tally failure leave the game dead-silent.
            try:
                await self.cog.tally_votes(
                    interaction.channel,
                    self.players,
                    self.votes,
                    self.spy,
                    self.word_pair,
                )
            except Exception as e:
                print(f"[UNDERCOVER] tally failed: {type(e).__name__}: {e}")
                traceback.print_exc()
                try:
                    await interaction.channel.send(
                        "⚠️ Something went wrong while tallying votes. "
                        "Please start a new game with `/undercover`."
                    )
                except Exception:
                    pass

    async def on_timeout(self):
        if self.tallied:
            return
        self.tallied = True
        if self.message:
            try:
                embed = rof_embed(
                    title="⏰ Voting Timed Out",
                    description=(
                        "Not everyone cast their vote in time. "
                        "The round has been cancelled — start a new game with `/undercover`."
                    ),
                    color=ROFColors.ERROR,
                )
                await self.message.edit(content="", embed=embed, view=None)
            except Exception as e:
                print(f"[UNDERCOVER] timeout cleanup failed: {e}")


# ---------- start-vote view ----------

class StartVoteView(discord.ui.View):
    def __init__(self, cog, players, spy, word_pair, channel=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.players = list(players)              # fix E
        self.player_ids = {p.id for p in self.players}
        self.spy = spy
        self.word_pair = word_pair
        self.channel = channel
        self.message = None

    @discord.ui.button(label="Start Voting", style=discord.ButtonStyle.danger, emoji="🗳️")
    async def vote_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.player_ids:
            return await interaction.response.send_message(
                "You are not playing!", ephemeral=True
            )

        self.stop()

        try:
            embed = rof_embed(
                title="🗳️ ROF Undercover — Voting Started",
                description="Select who you suspect is the Spy from the dropdown menu below!",
                color=ROFColors.ACCENT,
            )
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception as e:
            print(f"[UNDERCOVER] edit_message failed: {e}")
            try:
                await interaction.response.send_message("Voting has started!", ephemeral=True)
            except Exception:
                pass

        vote_view = UndercoverVote(self.cog, self.players, self.spy, self.word_pair)
        try:
            vote_view.message = await interaction.channel.send(
                "Cast your votes below:", view=vote_view
            )
        except Exception as e:
            print(f"[UNDERCOVER] failed to send vote message: {e}")

    async def on_timeout(self):
        # fix D: nudge the channel if nobody clicked "Start Voting".
        if not self.channel:
            return
        try:
            await self.channel.send(
                "⏰ The voting button expired after 5 minutes. "
                "Start a new game with `/undercover`."
            )
        except Exception:
            pass


# ---------- cog ----------

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
            extra_description=(
                "🕵️ **Players:** 3–6 players\n"
                "💬 Everyone gets a secret word via DM, except the Spy who gets a slightly different word!"
            ),
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
        players = list(players)                   # fix E
        if len(players) < 3:
            return await channel.send(
                "⚠️ Undercover needs at least **3 players** to start."
            )

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
            except discord.Forbidden:             # fix I
                failed_dms.append(p.mention)
            except Exception as e:
                print(f"[UNDERCOVER] DM to {p.id} failed: {type(e).__name__}: {e}")
                failed_dms.append(p.mention)

        if failed_dms:
            # fix H: acknowledge that some DMs may already have been delivered.
            return await channel.send(
                f"⚠️ Could not DM {', '.join(failed_dms)}.\n"
                f"**Fix:** Enable *DMs from server members* in your Privacy Settings, "
                f"then start a new game with `/undercover`.\n"
                f"*Any DMs already delivered can be ignored — this round is cancelled.*"
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
        view = StartVoteView(self, players, spy, pair, channel=channel)
        try:
            view.message = await channel.send(embed=embed, view=view)
        except Exception as e:
            print(f"[UNDERCOVER] failed to send start embed: {e}")

    async def tally_votes(self, channel, players, votes, spy, word_pair):
        players = list(players)                   # fix E

        def _player_name(pid):
            m = discord.utils.get(players, id=pid)
            return m.display_name if m else f"User {pid}"

        counts = {}
        for target_id in votes.values():
            counts[target_id] = counts.get(target_id, 0) + 1

        if not counts:
            return await channel.send("⚠️ No votes were cast — round cancelled.")

        max_votes = max(counts.values())
        eliminated_ids = [pid for pid, c in counts.items() if c == max_votes]
        was_tie = len(eliminated_ids) > 1

        chosen_id = random.choice(eliminated_ids)
        eliminated_player = discord.utils.get(players, id=chosen_id)
        civilian_word, spy_word = word_pair
        arcade = self.bot.get_cog("ArcadeCore")

        # fix G: transparent vote breakdown.
        vote_breakdown = "\n".join(
            f"**{_player_name(pid)}**: {cnt} vote{'s' if cnt != 1 else ''}"
            for pid, cnt in sorted(counts.items(), key=lambda x: -x[1])
        )

        tie_note = ""
        if was_tie:
            names = ", ".join(_player_name(pid) for pid in eliminated_ids)
            tie_note = f"\n\n⚠️ **Tie** between {names} — random elimination!"

        spy_caught = bool(eliminated_player and eliminated_player.id == spy.id)

        if spy_caught:
            embed = rof_embed(
                title="🔍 ROF Undercover — Voting Results",
                description=(
                    f"🎯 **Civilians Win!** {eliminated_player.mention} was caught as the Spy!\n"
                    f"**Words:** Civilian = `{civilian_word}` | Spy = `{spy_word}`"
                    f"{tie_note}"
                ),
                color=ROFColors.SUCCESS,
            )
            embed.add_field(name="Vote Breakdown", value=vote_breakdown, inline=False)
            for p in players:
                won = p.id != spy.id
                try:
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
                except Exception as e:
                    print(f"[UNDERCOVER] db record failed for {p.id}: {e}")
        else:
            elim_name = eliminated_player.mention if eliminated_player else "Nobody"
            embed = rof_embed(
                title="🔍 ROF Undercover — Voting Results",
                description=(
                    f"❌ **Spy Wins!** {elim_name} was innocent.\n"
                    f"The Spy was actually **{spy.mention}**!\n"
                    f"**Words:** Civilian = `{civilian_word}` | Spy = `{spy_word}`"
                    f"{tie_note}"
                ),
                color=ROFColors.ERROR,
            )
            embed.add_field(name="Vote Breakdown", value=vote_breakdown, inline=False)
            for p in players:
                won = p.id == spy.id
                try:
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
                except Exception as e:
                    print(f"[UNDERCOVER] db record failed for {p.id}: {e}")

        # fix C: don't let arcade hiccup kill the result message.
        if arcade:
            try:
                arcade.reload_cache()
            except Exception as e:
                print(f"[UNDERCOVER] arcade reload_cache failed: {e}")

        await channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Undercover(bot))