"""Stable absolute entry point for tmux, without changing the agent's PYTHONPATH."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent_dino.cli import main

raise SystemExit(main())
