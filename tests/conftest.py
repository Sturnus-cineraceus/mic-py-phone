"""pytest configuration: mock unavailable native dependencies before test collection."""

import sys
from unittest.mock import MagicMock

# Provide stub modules for native dependencies that are not available in the
# test environment (e.g. pywebview, sounddevice).
for _mod in ("webview", "sounddevice"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
