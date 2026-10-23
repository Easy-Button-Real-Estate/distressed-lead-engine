"""State directory. Override with ICC_HOME in tests."""

from __future__ import annotations

import os
from pathlib import Path


def state_dir() -> Path:
    override = os.environ.get("ICC_HOME")
    if override:
        return Path(override)
    return Path.home() / ".imessage-command-center"


def ensure_state_dir() -> Path:
    path = state_dir()
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)
    return path
