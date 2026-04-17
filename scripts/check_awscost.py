import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.aws_costs import fetch_aws_cost_summary


def main():
    print(asyncio.get_event_loop().run_until_complete(fetch_aws_cost_summary()))


if __name__ == "__main__":
    main()
