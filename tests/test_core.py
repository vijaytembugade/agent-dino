import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from agent_dino.adapters import command, hooks, toml
from agent_dino.game import Game, Obstacle
from agent_dino.hook import relay
from agent_dino.lifecycle import Lifecycle


def event(name, **fields):
    return {"session_id": "main", "hook_event_name": name, **fields}


class GameTests(unittest.TestCase):
    def test_jump_lands_and_cannot_double_jump(self):
        game = Game(1)
        game.jump()
        game.tick(0.1, 80)
        velocity = game.velocity
        game.jump()
        self.assertEqual(game.velocity, velocity)
        self.assertGreater(game.height, 0)
        for _ in range(20):
            game.tick(0.05, 80)
        self.assertEqual(game.height, 0)

    def test_ground_collision_and_jump_clearance(self):
        grounded = Game(1)
        grounded.obstacles = [Obstacle(8)]
        grounded.tick(0.01, 80)
        self.assertTrue(grounded.over)
        jumping = Game(1)
        jumping.height = 4
        jumping.obstacles = [Obstacle(8)]
        jumping.tick(0.01, 80)
        self.assertFalse(jumping.over)

    def test_collision_stops_score_and_restart_preserves_best(self):
        game = Game(1)
        game.distance = 99
        game.obstacles = [Obstacle(8)]
        game.tick(0.05, 80)
        score = game.score
        game.tick(0.2, 80)
        self.assertEqual(game.score, score)
        game.jump()
        self.assertFalse(game.over)
        self.assertEqual(game.score, 0)
        self.assertGreaterEqual(game.best, 99)

    def test_long_frame_cannot_tunnel_through_cactus(self):
        game = Game(1)
        game.obstacles = [Obstacle(14)]
        game.tick(10, 80)
        self.assertTrue(game.over)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.state = Lifecycle()
        self.state.handle(event("SessionStart"))
        self.state.handle(event("UserPromptSubmit", turn_id="1"))

    def test_permission_pause_and_resume(self):
        self.state.handle(event("PermissionRequest", tool_name="Bash"))
        self.assertEqual(self.state.status, "waiting")
        self.state.handle(event("PreToolUse", tool_name="Read"))
        self.state.handle(event("PostToolUse", tool_name="Read"))
        self.assertEqual(self.state.status, "waiting")
        self.state.handle(event("PostToolUse", tool_name="Bash", tool_use_id="call-1"))
        self.assertEqual(self.state.status, "busy")

    def test_question_waits_until_answered(self):
        self.state.handle(event("PreToolUse", tool_name="AskUserQuestion", tool_use_id="ask"))
        self.assertEqual(self.state.status, "waiting")
        self.state.handle(event("PostToolUse", tool_name="AskUserQuestion", tool_use_id="ask"))
        self.assertEqual(self.state.status, "busy")

    def test_parallel_permissions_for_same_tool_require_both_results(self):
        for _ in range(2):
            self.state.handle(event("PermissionRequest", tool_name="Bash"))
        self.state.handle(event("PostToolUse", tool_name="Bash"))
        self.assertEqual(self.state.status, "waiting")
        self.state.handle(event("PostToolUse", tool_name="Bash"))
        self.assertEqual(self.state.status, "busy")

    def test_late_tool_result_does_not_restart_completed_turn(self):
        self.state.handle(event("Stop"))
        self.state.handle(event("PostToolUse", tool_name="Bash"))
        self.assertEqual(self.state.status, "idle")

    def test_other_sessions_subagents_and_old_turns_cannot_stop_game(self):
        for extra in ({"session_id": "other"}, {"agent_id": "subagent"}, {"turn_id": "old"}):
            self.state.handle(event("Stop", **extra))
            self.assertEqual(self.state.status, "busy")
        self.state.handle(event("Stop", turn_id="1"))
        self.assertEqual(self.state.status, "idle")

    def test_stop_interrupt_failure_and_end(self):
        for name in ("Stop", "StopFailure", "Interrupt", "SessionEnd"):
            self.state.handle(event("UserPromptSubmit"))
            self.state.handle(event(name))
            self.assertEqual(self.state.status, "idle")

    def test_auto_only_respects_mode(self):
        state = Lifecycle(auto_only=True)
        state.handle(event("UserPromptSubmit", permission_mode="default"))
        self.assertEqual(state.status, "idle")
        for mode in ("auto", "dontAsk", "bypassPermissions"):
            state.handle(event("UserPromptSubmit", permission_mode=mode))
            self.assertEqual(state.status, "busy")

    def test_unrelated_notifications_and_malformed_payloads_are_ignored(self):
        for payload in (None, [], {}, {"session_id": []}, event("Notification", notification_type="auth_success")):
            self.state.handle(payload)
            self.assertEqual(self.state.status, "busy")


class HookTests(unittest.TestCase):
    def test_concurrent_hooks_produce_complete_separate_events(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda i: relay(event("PostToolUse", tool_use_id=str(i)), directory), range(32)))
            payloads = [json.loads(path.read_text()) for path in Path(directory).glob("*.json")]
            self.assertEqual({p["tool_use_id"] for p in payloads}, {str(i) for i in range(32)})
            self.assertEqual(len(list(Path(directory).iterdir())), 32)

    def test_inbox_receives_only_lifecycle_metadata(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            relay(event("UserPromptSubmit", prompt="private", tool_input={"secret": "private"}), directory)
            files = list(Path(directory).glob("*.json"))
            self.assertEqual(len(files), 1)
            payload = json.loads(files[0].read_text())
            self.assertEqual(payload, event("UserPromptSubmit"))

    def test_missing_listener_and_bad_json_do_not_block_agent(self):
        for payload in ("not-json", "[]", json.dumps(event("Stop"))):
            result = subprocess.run([sys.executable, "-m", "agent_dino.hook"], input=payload,
                                    text=True, capture_output=True,
                                    env={**os.environ, "AGENT_DINO_EVENTS": "/tmp/nonexistent-agent-dino-test-inbox"})
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")


class AdapterTests(unittest.TestCase):
    def test_toml_preserves_shell_quoted_paths(self):
        try:
            import tomllib
        except ImportError:
            self.skipTest("tomllib requires Python 3.11")
        config = hooks("codex", "'/a path/python' '/a path/hook.py'")
        parsed = tomllib.loads("hooks=" + toml(config))
        self.assertEqual(parsed["hooks"], config)

    def test_agent_arguments_are_preserved_and_no_permissions_are_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            args = ["--model", "my-model", "a prompt with $(literal) text"]
            for agent in ("codex", "claude"):
                argv = command(agent, args, directory)
                self.assertEqual(argv[-3:], args)
                self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
                self.assertNotIn("--dangerously-skip-permissions", argv)
                self.assertNotIn("--dangerously-bypass-hook-trust", argv)

    def test_packaged_hooks_match_adapters(self):
        root = Path(__file__).resolve().parents[1]
        for agent, filename in (("claude", "legacy-claude.json"), ("codex", "codex.json")):
            config = json.loads((root / "hooks" / filename).read_text())
            self.assertEqual(set(config["hooks"]), set(hooks(agent)))
            for groups in config["hooks"].values():
                self.assertEqual(groups[0]["hooks"][0]["type"], "command")
                self.assertEqual(groups[0]["hooks"][0]["statusMessage"], "Agent Dino")

    def test_session_hooks_have_a_visible_name(self):
        for agent in ("codex", "claude"):
            for groups in hooks(agent).values():
                self.assertEqual(groups[0]["hooks"][0]["statusMessage"], "Agent Dino")


if __name__ == "__main__":
    unittest.main()

