from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from common.scheduler import run_task


def main() -> None:
    print(run_task("market-info-fetcher", enforce_trading_hours=False))


if __name__ == "__main__":
    main()
