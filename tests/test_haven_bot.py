# tests/test_haven_bot.py
"""
Automated unit & integration test suite for Haven (HAV) Discord Bot.
Runs with Python's built-in unittest module (no external test runner required).
"""
import asyncio
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

# Ensure project root is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Provide lightweight stubs for discord/pymongo ONLY if not installed in the test environment
if "discord" not in sys.modules:
    try:
        import discord  # noqa: F401
    except ImportError:
        discord_mod = types.ModuleType("discord")

        class _Embed:
            def __init__(self, title="", description="", color=0):
                self.title = title
                self.description = description
                self.color = color
                self.fields = []
                self.footer = None
                self.thumbnail = None

            def add_field(self, *, name="", value="", inline=False):
                self.fields.append(types.SimpleNamespace(name=name, value=value, inline=inline))
                return self

            def set_footer(self, *, text=""):
                self.footer = types.SimpleNamespace(text=text)
                return self

            def set_thumbnail(self, *, url=None):
                self.thumbnail = types.SimpleNamespace(url=url)
                return self

        class _View:
            def __init__(self, timeout=180.0):
                self.timeout = timeout
                self.children = []
                self._stopped = False

            def add_item(self, item):
                self.children.append(item)

            def clear_items(self):
                self.children.clear()

            def stop(self):
                self._stopped = True

        class _Modal:
            def __init_subclass__(cls, **kwargs):
                super().__init_subclass__()

            def __init__(self, title=""):
                self.title = title
                self.children = []

            def add_item(self, item):
                self.children.append(item)

        class _Button:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
                self.disabled = kwargs.get("disabled", False)
                self.callback = None

        class _Select:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
                self.disabled = kwargs.get("disabled", False)
                self.values = []
                self.options = kwargs.get("options", [])
                self.callback = None

        class _SelectOption:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        class _TextInput:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
                self.value = kwargs.get("default", "")

        class _Label:
            def __init__(self, text="", component=None, **kwargs):
                self.text = text
                self.component = component

        def _button_deco(**kwargs):
            def wrapper(fn):
                return fn
            return wrapper

        ui_mod = types.ModuleType("discord.ui")
        ui_mod.View = _View
        ui_mod.Modal = _Modal
        ui_mod.Button = _Button
        ui_mod.Select = _Select
        ui_mod.SelectOption = _SelectOption
        ui_mod.TextInput = _TextInput
        ui_mod.Label = _Label
        ui_mod.Item = object
        ui_mod.button = _button_deco

        app_mod = types.ModuleType("discord.app_commands")

        class _Group:
            def __init__(self, **kwargs):
                pass

            def command(self, **kwargs):
                def dec(fn):
                    return fn
                return dec

        class _Choice:
            def __init__(self, name="", value=None):
                self.name = name
                self.value = value

            def __class_getitem__(cls, item):
                return cls

        class _Checks:
            @staticmethod
            def cooldown(*args, **kwargs):
                def dec(fn):
                    return fn
                return dec

        app_mod.Group = _Group
        app_mod.Choice = _Choice
        app_mod.AppCommandContext = lambda **kwargs: kwargs
        app_mod.AppCommandError = Exception
        app_mod.CommandOnCooldown = type("CommandOnCooldown", (Exception,), {})
        app_mod.NoPrivateMessage = type("NoPrivateMessage", (Exception,), {})
        app_mod.BotMissingPermissions = type("BotMissingPermissions", (Exception,), {})
        app_mod.MissingPermissions = type("MissingPermissions", (Exception,), {})
        app_mod.CheckFailure = type("CheckFailure", (Exception,), {})
        app_mod.CommandNotFound = type("CommandNotFound", (Exception,), {})
        app_mod.checks = _Checks
        app_mod.command = lambda **kwargs: (lambda fn: fn)
        app_mod.describe = lambda **kwargs: (lambda fn: fn)
        app_mod.choices = lambda **kwargs: (lambda fn: fn)
        app_mod.autocomplete = lambda **kwargs: (lambda fn: fn)
        app_mod.allowed_contexts = lambda **kwargs: (lambda fn: fn)

        ext_mod = types.ModuleType("discord.ext")
        commands_mod = types.ModuleType("discord.ext.commands")

        class _Cog:
            @staticmethod
            def listener(*args, **kwargs):
                def dec(fn):
                    return fn
                return dec

        commands_mod.Cog = _Cog
        commands_mod.Bot = object

        tasks_mod = types.ModuleType("discord.ext.tasks")

        class _LoopWrapper:
            def __init__(self, fn):
                self.fn = fn

            def start(self):
                pass

            def cancel(self):
                pass

            def before_loop(self, fn):
                return fn

        tasks_mod.loop = lambda **kwargs: (lambda fn: _LoopWrapper(fn))

        abc_mod = types.ModuleType("discord.abc")
        abc_mod.User = object

        utils_mod = types.ModuleType("discord.utils")
        utils_mod.get = lambda iterable, **attrs: next(
            (x for x in iterable if all(getattr(x, k, None) == v for k, v in attrs.items())),
            None,
        )

        discord_mod.Embed = _Embed
        discord_mod.ui = ui_mod
        discord_mod.app_commands = app_mod
        discord_mod.ext = ext_mod
        discord_mod.abc = abc_mod
        discord_mod.utils = utils_mod
        discord_mod.Interaction = object
        discord_mod.Message = object
        discord_mod.Member = object
        discord_mod.User = object
        discord_mod.Role = object
        discord_mod.Guild = object
        discord_mod.TextChannel = object
        discord_mod.Client = object
        discord_mod.File = MagicMock
        discord_mod.AllowedMentions = lambda **kwargs: kwargs
        discord_mod.ButtonStyle = types.SimpleNamespace(
            primary=1, secondary=2, success=3, danger=4
        )
        discord_mod.TextStyle = types.SimpleNamespace(short=1, paragraph=2)
        discord_mod.HTTPException = type("HTTPException", (Exception,), {})
        discord_mod.NotFound = type("NotFound", (Exception,), {})
        discord_mod.Forbidden = type("Forbidden", (Exception,), {})
        discord_mod.InteractionResponded = type("InteractionResponded", (Exception,), {})

        sys.modules["discord"] = discord_mod
        sys.modules["discord.ui"] = ui_mod
        sys.modules["discord.app_commands"] = app_mod
        sys.modules["discord.ext"] = ext_mod
        sys.modules["discord.ext.commands"] = commands_mod
        sys.modules["discord.ext.tasks"] = tasks_mod
        sys.modules["discord.abc"] = abc_mod
        sys.modules["discord.utils"] = utils_mod


class TestCoreConfig(unittest.TestCase):
    def test_format_tz_label(self):
        from core.config import format_tz_label
        self.assertEqual(format_tz_label(-2.0), "UTC-02:00")
        self.assertEqual(format_tz_label(5.5), "UTC+05:30")
        self.assertEqual(format_tz_label(0.0), "UTC+00:00")

    def test_format_dual_timestamps(self):
        from core.config import format_dual_timestamps
        dt = datetime(2026, 11, 28, 18, 0, tzinfo=timezone.utc)
        res = format_dual_timestamps(dt, offset_hours=-2.0)
        self.assertEqual(res["game_time_short"], "16:00")
        self.assertEqual(res["india_time_short"], "23:30")
        self.assertIn("<t:", res["discord_relative"])

    def test_rank_ladder(self):
        from core.config import get_rank
        self.assertEqual(get_rank(0)[0], "Recruit")
        self.assertEqual(get_rank(2500)[0], "HAV Legend")


class TestSQLiteDatabase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test_haven.db")
        from core.database import Database
        self.db = Database(db_path=self.db_path)

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_player_recording_and_leaderboard(self):
        pts = self.db.record_game_result(
            user_id=101, game_name="Wordle", result="win",
            score=100, points_earned=50, attempts=2, username="Alice",
        )
        self.assertEqual(pts, 50)
        prof = self.db.get_player_profile(101)
        self.assertEqual(prof["points"], 50)
        self.assertEqual(prof["wins"], 1)
        self.assertEqual(prof["favourite_game"], "Wordle")

        lb_all = self.db.get_leaderboard("overall")
        self.assertTrue(any(r["user_id"] == 101 and r["points"] == 50 for r in lb_all))

        lb_game = self.db.get_leaderboard("game", game_name="wordle")
        self.assertTrue(any(r["user_id"] == 101 for r in lb_game))

        lb_week = self.db.get_leaderboard("weekly")
        self.assertTrue(any(r["user_id"] == 101 for r in lb_week))

    def test_event_case_insensitive_update_cancel_delete_and_reminder(self):
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        ev = self.db.create_event(
            event_id="ab12cd",
            name="Turmoil Surge",
            description="Rally up",
            start_time_utc=future,
            duration_minutes=60,
            channel_id=999,
            creator_id=1,
            reminder_minutes=10,
            repeat_days=2,
        )
        self.assertEqual(ev["id"], "ab12cd")

        # Update using UPPERCASE event ID (previously failed silently in SQLite!)
        updated = self.db.update_event("AB12CD", name="Turmoil Surge Updated")
        self.assertIsNotNone(updated)
        self.assertEqual(updated["name"], "Turmoil Surge Updated")

        # Mark reminder sent using mixed-case ID
        self.db.mark_reminder_sent("Ab12Cd")
        ev_after = self.db.get_event("ab12cd")
        self.assertEqual(ev_after["reminder_sent"], 1)

        # Cancel using uppercase ID
        self.db.cancel_or_delete_event("AB12CD", delete_permanently=False)
        ev_cancelled = self.db.get_event("ab12cd")
        self.assertEqual(ev_cancelled["status"], "cancelled")

        # Delete permanently using uppercase ID
        self.db.cancel_or_delete_event("AB12CD", delete_permanently=True)
        self.assertIsNone(self.db.get_event("ab12cd"))

    def test_kv_json_and_path_traversal_guard(self):
        self.db.save_kv_json("test_kv_unit", {"a": 1})
        self.assertEqual(self.db.load_kv_json("test_kv_unit"), {"a": 1})
        with self.assertRaises(ValueError):
            self.db.load_kv_json("../escape")
        with self.assertRaises(ValueError):
            self.db.save_kv_json("../../evil", {})
        # Cleanup test kv file
        p = self.db._safe_kv_path("test_kv_unit")
        if os.path.exists(p):
            os.remove(p)

    def test_rules_and_knowledge_crud(self):
        num = self.db.add_rule("Be kind to teammates", actor_id=1)
        self.assertGreaterEqual(num, 1)
        self.assertTrue(self.db.edit_rule(num, "Be super kind", actor_id=1))
        self.assertTrue(self.db.remove_rule(num))

        saved = self.db.upsert_knowledge("custom_tip", "Custom Tip", "Guides", "Hello", "tip", actor_id=1)
        self.assertEqual(saved["key"], "custom_tip")
        self.assertIsNotNone(self.db.get_knowledge("CUSTOM_TIP"))
        self.assertTrue(self.db.remove_knowledge("CUSTOM_TIP"))


class TestGameLogicAndFixes(unittest.TestCase):
    def test_wordle_evaluate_guess(self):
        from cogs.wordle import evaluate_guess, GREEN, YELLOW, GREY
        self.assertEqual(evaluate_guess("crane", "crane"), [GREEN] * 5)
        # Repeated letter edge case: answer has one 'e', guess has two 'e's
        res = evaluate_guess("geese", "crane")
        self.assertEqual(res[4], GREEN)
        self.assertEqual(res[1], GREY)
        self.assertEqual(res[2], GREY)

    def test_codebreaker_logic(self):
        from cogs.codebreaker import generate_secret_code, evaluate_codebreaker_guess
        for _ in range(50):
            code = generate_secret_code(allow_repeats=False)
            self.assertEqual(len(code), 4)
            self.assertNotEqual(code[0], "0")
            self.assertEqual(len(set(code)), 4)
        self.assertEqual(evaluate_codebreaker_guess("1234", "1234"), (4, 0))
        self.assertEqual(evaluate_codebreaker_guess("1234", "4321"), (0, 4))
        self.assertEqual(evaluate_codebreaker_guess("1234", "1325"), (1, 2))

    def test_ascii_int_text_rejects_unicode_digits(self):
        from cogs.singleplayer_games import _is_int_text
        self.assertTrue(_is_int_text("42"))
        self.assertTrue(_is_int_text("-7"))
        self.assertFalse(_is_int_text("١٢٣"))  # Arabic-Indic digits
        self.assertFalse(_is_int_text("²³"))   # Superscript digits

    def test_trivia_difficulty_filtering(self):
        from cogs.singleplayer_games import TriviaSessionView
        user = types.SimpleNamespace(id=1, display_name="Tester")
        view = TriviaSessionView(cog=None, user=user, category="All", difficulty="easy", total_questions=5)
        self.assertEqual(len(view.questions), 5)
        self.assertTrue(all(q["diff"] == "easy" for q in view.questions))

    def test_owner_stealth_board_helpers_do_not_mutate_input(self):
        from core.owner_stealth import best_tictactoe_move, best_connect4_col
        ttt = [1, 1, 0, 2, 2, 0, 0, 0, 0]
        ttt_copy = list(ttt)
        move = best_tictactoe_move(ttt, 1)
        self.assertEqual(move, 3)
        self.assertEqual(ttt, ttt_copy)

        c4 = [[0] * 7 for _ in range(6)]
        c4[5][0] = c4[5][1] = c4[5][2] = 1
        c4_copy = [row[:] for row in c4]
        col = best_connect4_col(c4, 1)
        self.assertEqual(col, 4)
        self.assertEqual(c4, c4_copy)

    def test_dm_assistant_queries(self):
        from cogs.dm_handler import answer_alliance_query
        title, body = answer_alliance_query("make me admin right now")
        self.assertIn("Security", title)

        title, body = answer_alliance_query("how do I play c4?")
        self.assertIn("Connect4", title)

        title, body = answer_alliance_query("who built you?")
        self.assertIn("Sam", body)

    def test_launcher_ping_with_nan_and_finite_latency(self):
        from cogs.launcher import Launcher

        async def _run():
            bot = types.SimpleNamespace(latency=float("nan"), started_at=datetime.now(timezone.utc))
            cog = Launcher(bot)
            inter = types.SimpleNamespace(
                response=types.SimpleNamespace(send_message=AsyncMock()),
            )
            await cog.ping_cmd(inter)
            inter.response.send_message.assert_awaited_once()
            emb = inter.response.send_message.call_args.kwargs["embed"]
            self.assertIn("Connecting...", emb.description)
            self.assertIn("Active Rooms", emb.description)

            bot.latency = 0.042
            inter2 = types.SimpleNamespace(
                response=types.SimpleNamespace(send_message=AsyncMock()),
            )
            await cog.ping_cmd(inter2)
            emb2 = inter2.response.send_message.call_args.kwargs["embed"]
            self.assertIn("42 ms", emb2.description)

        asyncio.run(_run())

    def test_launcher_help_embed_field_limits(self):
        from cogs.launcher import build_game_help_embed
        emb = build_game_help_embed()
        for f in emb.fields:
            self.assertLessEqual(len(f.value), 1024, f"Field {f.name} exceeds 1024 chars")

    def test_hav_embed_truncation_guards(self):
        from core.ui import hav_embed
        emb = hav_embed(title="T" * 300, description="D" * 5000, footer_extra="F" * 3000)
        self.assertLessEqual(len(emb.title), 256)
        self.assertLessEqual(len(emb.description), 4096)
        self.assertLessEqual(len(emb.footer.text), 2048)

    def test_multiplayer_rps_tied_timeout_does_not_award_false_win(self):
        from cogs.multiplayer_games import MultiplayerRPSView
        from core.rooms import MultiplayerRoom

        async def _run():
            p1 = types.SimpleNamespace(id=11, mention="<@11>", display_name="P1")
            p2 = types.SimpleNamespace(id=22, mention="<@22>", display_name="P2")
            room = MultiplayerRoom("HAV-0001", "rps_multi", "RPS", p1, 2, 2)
            room.players = [p1, p2]
            room.message = types.SimpleNamespace(edit=AsyncMock())
            view = MultiplayerRPSView(cog=None, room=room, best_of=3)
            await view.on_timeout()
            self.assertTrue(view.finished)
            room.message.edit.assert_awaited_once()
            emb = room.message.edit.call_args.kwargs["embed"]
            self.assertTrue(any("Draw" in f.name for f in emb.fields))

        asyncio.run(_run())

    def test_quickdraw_reaction_race_ready_embed_display(self):
        from cogs.quickdraw import ReactionRaceActiveView
        from core.rooms import MultiplayerRoom
        p1 = types.SimpleNamespace(id=11, mention="<@11>", display_name="P1")
        p2 = types.SimpleNamespace(id=22, mention="<@22>", display_name="P2")
        room = MultiplayerRoom("HAV-0002", "reaction_race", "Reaction Race", p1, 2, 10)
        room.players = [p1, p2]
        view = ReactionRaceActiveView(cog=None, room=room)
        emb_wait = view.build_embed()
        self.assertIn("READY SOON", emb_wait.title)
        emb_ready = view.build_embed(force_ready_display=True)
        self.assertIn("CLICK NOW", emb_ready.title)


    def test_room_manager_cancels_background_task_on_solo_replace(self):
        from core.rooms import RoomManager
        rm = RoomManager()

        async def _run():
            old_view = MagicMock()
            old_view.children = []
            old_view._stealth_id = None
            task = asyncio.create_task(asyncio.sleep(60))
            old_view.timer_task = task
            new_view = MagicMock()
            rm.register_solo_view(999, "quickmath", old_view)
            rm.register_solo_view(999, "quickmath", new_view)
            await asyncio.sleep(0)
            self.assertTrue(task.cancelled())
            old_view.stop.assert_called_once()

        asyncio.run(_run())

if __name__ == "__main__":
    unittest.main()
