from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
REQUESTED_AGENT_STACK_ROOT = os.environ.get("AWP_EXPECT_AGENT_STACK_ROOT")

sys.dont_write_bytecode = True

if REQUESTED_AGENT_STACK_ROOT is not None:
    sys.path.insert(0, REQUESTED_AGENT_STACK_ROOT)
elif SRC.is_dir():
    sys.path.insert(0, str(SRC))
