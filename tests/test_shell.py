import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_dino.shell import START, install, should_wrap, uninstall


class ShellTests(unittest.TestCase):
    def test_install_is_idempotent_and_uninstall_preserves_user_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "zshrc"
            original = "# my settings\nexport EDITOR=vim\n"
            path.write_text(original)
            install(["codex", "claude"], path)
            first = path.read_text()
            install(["codex", "claude"], path)
            self.assertEqual(path.read_text(), first)
            self.assertEqual(first.count(START), 1)
            self.assertTrue(list(path.parent.glob("zshrc.agent-dino-backup-*")))
            uninstall(path)
            self.assertEqual(path.read_text().rstrip(), original.rstrip())

    @patch.dict(os.environ, {}, clear=True)
    def test_interactive_sessions_wrap_but_automation_management_and_nested_calls_do_not(self):
        for agent, args in (("codex", []), ("codex", ["--model", "example", "my prompt"]),
                            ("codex", ["resume", "--last"]), ("claude", ["--permission-mode", "auto"])):
            self.assertTrue(should_wrap(agent, args, interactive=True))
        for agent, args in (("codex", ["--version"]), ("codex", ["exec", "task"]),
                            ("codex", ["--model", "example", "exec", "task"]),
                            ("codex", ["plugin", "list"]), ("claude", ["-p", "task"]),
                            ("claude", ["auth", "status"]), ("codex", ["--remote=unix://x"])):
            self.assertFalse(should_wrap(agent, args, interactive=True))
        self.assertFalse(should_wrap("codex", [], interactive=False))
        os.environ["AGENT_DINO_ACTIVE"] = "1"
        self.assertFalse(should_wrap("codex", [], interactive=True))


if __name__ == "__main__":
    unittest.main()
