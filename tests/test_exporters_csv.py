from __future__ import annotations

import csv
import io
import tempfile
import unittest
from pathlib import Path

from github_harvester.exporters import export_to_csv, _sanitize_csv_cell
from github_harvester.models import Repo


class TestExportersCSV(unittest.TestCase):
    def test_sanitize_csv_cell_dangerous_characters(self):
        # Formula injection characters at the start of strings
        self.assertEqual(_sanitize_csv_cell("=1+1"), "'=1+1")
        self.assertEqual(_sanitize_csv_cell("+cmd|' /C calc'!A0"), "'+cmd|' /C calc'!A0")
        self.assertEqual(_sanitize_csv_cell("-5"), "'-5")
        self.assertEqual(_sanitize_csv_cell("@SUM(A1:A10)"), "'@SUM(A1:A10)")
        self.assertEqual(_sanitize_csv_cell("\tTabPrefix"), "'\tTabPrefix")
        self.assertEqual(_sanitize_csv_cell("\rReturnPrefix"), "'\rReturnPrefix")

        # Safe values should remain intact
        self.assertEqual(_sanitize_csv_cell("normal text"), "normal text")
        self.assertEqual(_sanitize_csv_cell(12345), 12345)
        self.assertEqual(_sanitize_csv_cell(""), "")

    def test_export_repositories_to_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "repos.csv"
            sample_repo = Repo(
                id=1,
                full_name="=calc_app",
                html_url="https://github.com/attacker/calc_app",
                description="+Malicious description payload",
                stargazers_count=100,
                language="Python",
                topics=["security", "calc"],
                default_branch="main",
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-02T00:00:00Z",
                pushed_at="2026-01-02T00:00:00Z",
                size_kb=500,
                clone_url="https://github.com/attacker/calc_app.git",
            )

            export_to_csv(csv_path, [sample_repo])

            self.assertTrue(csv_path.exists())
            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            self.assertEqual(len(rows), 1)
            row = rows[0]
            # Verify dangerous leading symbols were sanitized with a leading single quote
            self.assertTrue(row["full_name"].startswith("'="))
            self.assertTrue(row["description"].startswith("'+"))


if __name__ == "__main__":
    unittest.main()
