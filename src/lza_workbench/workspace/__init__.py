"""Core Workbench behavior.

Keep workspace, metadata, and template logic independent from CLI presentation.
"""

from pathlib import Path

WORKSPACE_CONFIG_FILE = Path("lza-workspace.yaml")
WORKSPACE_STATE_FILE = Path(".lza") / "state.json"
