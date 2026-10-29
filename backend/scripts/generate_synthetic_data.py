"""Generate deterministic synthetic retail data as CSV files (local only; nothing is uploaded).

Usage (from backend/, with the virtual environment active):
    python scripts/generate_synthetic_data.py
    python scripts/generate_synthetic_data.py --seed 7 --products 50 --days 30 --output data/synthetic
"""

import argparse
from datetime import date
from pathlib import Path

from app.synthetic import GeneratorConfig, generate_dataset, write_csv

BACKEND_DIR = Path(__file__).resolve().parents[1]


def main() -> None:
    defaults = GeneratorConfig()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=defaults.seed)
    parser.add_argument("--suppliers", type=int, default=defaults.num_suppliers)
    parser.add_argument("--products", type=int, default=defaults.num_products)
    parser.add_argument("--stores", type=int, default=defaults.num_stores)
    parser.add_argument("--days", type=int, default=defaults.num_days)
    parser.add_argument("--start-date", type=date.fromisoformat, default=defaults.start_date)
    parser.add_argument("--output", type=Path, default=BACKEND_DIR / "data" / "synthetic")
    args = parser.parse_args()

    config = GeneratorConfig(
        seed=args.seed,
        num_suppliers=args.suppliers,
        num_products=args.products,
        num_stores=args.stores,
        start_date=args.start_date,
        num_days=args.days,
    )
    dataset = generate_dataset(config)
    paths = write_csv(dataset, args.output)

    print(f"Seed {config.seed}, {config.start_date} to {config.end_date}, {config.num_stores} stores")
    for table, path in paths.items():
        print(f"  {table:<16} {len(dataset.tables()[table]):>8,} rows  -> {path}")


if __name__ == "__main__":
    main()
