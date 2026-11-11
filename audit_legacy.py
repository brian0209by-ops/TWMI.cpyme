"""Inspect the TWMI legacy SQLite snapshot without writing to it."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path


def inspect_database(path: Path) -> dict:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as db:
        integrity = [row[0] for row in db.execute("PRAGMA integrity_check")]
        if integrity != ["ok"]:
            raise ValueError("SQLite integrity check failed")

        instrument_counts = dict(db.execute(
            "SELECT kind, COUNT(*) FROM instruments GROUP BY kind ORDER BY kind"
        ))
        observation_count, pit_count = db.execute(
            "SELECT COUNT(*), COUNT(CASE WHEN pit_eligible = 1 THEN 1 END) FROM observations"
        ).fetchone()
        forecast_count, forecasts_with_probabilities = db.execute(
            """SELECT COUNT(*), COUNT(CASE WHEN prob_up IS NOT NULL
                   AND prob_flat IS NOT NULL AND prob_down IS NOT NULL THEN 1 END)
               FROM forecasts"""
        ).fetchone()
        snapshot_count = db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        evaluation_count = db.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
        corporate_action_count = db.execute("SELECT COUNT(*) FROM corporate_actions").fetchone()[0]

    return {
        "integrity": "ok",
        "instrument_counts_by_kind": instrument_counts,
        "observation_count": observation_count,
        "point_in_time_flagged_count": pit_count,
        "snapshot_count": snapshot_count,
        "forecast_count": forecast_count,
        "forecasts_with_all_probabilities": forecasts_with_probabilities,
        "evaluation_count": evaluation_count,
        "corporate_action_count": corporate_action_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="Path to the extracted legacy SQLite file")
    args = parser.parse_args()
    try:
        result = inspect_database(args.database)
    except (sqlite3.Error, ValueError) as error:
        parser.exit(1, f"Audit failed: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
