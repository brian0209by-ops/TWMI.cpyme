import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from audit_legacy import inspect_database


class LegacyAuditTest(unittest.TestCase):
    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.sqlite"
            with self.assertRaises(sqlite3.OperationalError):
                inspect_database(path)
            self.assertFalse(path.exists())

    def test_counts_and_preserves_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test #fixture.sqlite"
            with closing(sqlite3.connect(path)) as db:
                db.executescript("""
                    CREATE TABLE instruments (kind TEXT);
                    CREATE TABLE observations (pit_eligible INTEGER);
                    CREATE TABLE forecasts (prob_up REAL, prob_flat REAL, prob_down REAL);
                    CREATE TABLE snapshots (id INTEGER);
                    CREATE TABLE evaluations (id INTEGER);
                    CREATE TABLE corporate_actions (id INTEGER);
                    INSERT INTO instruments VALUES ('test_kind');
                    INSERT INTO observations VALUES (1), (0), (NULL);
                    INSERT INTO forecasts VALUES (NULL, NULL, NULL), (0.5, 0.2, 0.3);
                """)
            before = path.read_bytes()
            result = inspect_database(path)
            self.assertEqual(result["observation_count"], 3)
            self.assertEqual(result["point_in_time_flagged_count"], 1)
            self.assertEqual(result["forecast_count"], 2)
            self.assertEqual(result["forecasts_with_all_probabilities"], 1)
            self.assertEqual(path.read_bytes(), before)
