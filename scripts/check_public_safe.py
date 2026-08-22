#!/usr/bin/env python3
"""第13部 §6.2 が名指ししているパスからの入口。実体は shiwake.safety.public_safe。"""

import sys

from shiwake.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["check-public-safe", *sys.argv[1:]]))
