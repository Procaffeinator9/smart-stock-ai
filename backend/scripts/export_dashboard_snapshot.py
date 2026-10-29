"""Export overview dashboard metrics, calculated from the synthetic dataset, as JSON for the frontend.

Local only: generates the dataset in memory (same defaults as generate_synthetic_data.py)
and never connects to Databricks.

Usage (from backend/, with the virtual environment active):
    python scripts/export_dashboard_snapshot.py
"""

import argparse
import json
from pathlib import Path

from app.analytics.overview import build_overview_snapshot
from app.synthetic import GeneratorConfig, generate_dataset

REPO_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO_DIR / "frontend" / "src" / "data" / "overview-snapshot.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=GeneratorConfig().seed)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    snapshot = build_overview_snapshot(generate_dataset(GeneratorConfig(seed=args.seed)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} ({args.output.stat().st_size / 1024:,.0f} KB, seed {args.seed})")


if __name__ == "__main__":
    main()
