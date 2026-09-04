#!/usr/bin/env python3
"""PRN16 Johor polling-night poller.

Backward-compatibility wrapper around the generalized polling engine
in `pipeline/live/poller.py`, defaulting to the PRN16 Johor election.
"""
from __future__ import annotations

import os
import sys

# Ensure pipeline/live is on sys.path so poller is importable
_LIVE_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIVE_DIR not in sys.path:
    sys.path.insert(0, _LIVE_DIR)

from poller import *  # noqa: F401, F403
from poller import main as _poller_main


def main(argv: list[str] | None = None) -> int:
    return _poller_main(default_election="prn16-johor", argv=argv)


if __name__ == "__main__":
    sys.exit(main())
