import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


class FakeDataFrame:
    def __init__(self, rows):
        self._rows = list(rows)

    def __len__(self):
        return len(self._rows)

    @property
    def empty(self):
        return len(self._rows) == 0

    @property
    def iloc(self):
        return self

    def __getitem__(self, item):
        return self._rows[item]

    def to_csv(self, path, index=False):
        Path(path).write_text("stub\n", encoding="utf-8")


class FakeHoldings:
    def __init__(self, should_raise_permission_error=False):
        self.empty = False
        self.should_raise_permission_error = should_raise_permission_error
        self.saved_path = None
        self.columns = {}

    def __setitem__(self, key, value):
        self.columns[key] = value

    def sort_values(self, by, ascending=False):
        return self

    def to_csv(self, path, index=False):
        if self.should_raise_permission_error:
            raise PermissionError("file in use")
        self.saved_path = path

    def __len__(self):
        return 1


fake_requests = types.SimpleNamespace(Session=lambda: types.SimpleNamespace(headers={}, get=None))
fake_pandas = types.SimpleNamespace(DataFrame=FakeDataFrame)

sys.modules.setdefault("requests", fake_requests)
sys.modules.setdefault("pandas", fake_pandas)

from biotech_fund_tracker import SEC13FTracker, print_menu


class PreviousFilingsTests(unittest.TestCase):
    def test_get_all_previous_filings_uses_second_recent_filing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tracker = SEC13FTracker(output_dir=tmp_dir)

            def fake_recent_filings(cik, fund_name, count=5, include_amendments=True):
                return [
                    {
                        "fund_name": fund_name,
                        "cik": cik,
                        "form_type": "13F-HR",
                        "filing_date": "2026-02-14",
                        "accession_number": "0000000000-26-000002",
                        "primary_document": "latest.xml",
                    },
                    {
                        "fund_name": fund_name,
                        "cik": cik,
                        "form_type": "13F-HR",
                        "filing_date": "2025-11-14",
                        "accession_number": "0000000000-25-000001",
                        "primary_document": "previous.xml",
                    },
                ][:count]

            with patch("biotech_fund_tracker.FUNDS", {"Test Fund": "1234567890"}):
                tracker.get_recent_filings = fake_recent_filings
                df = tracker.get_all_previous_filings()

            self.assertEqual(len(df), 1)
            self.assertEqual(df.iloc[0]["filing_date"], "2025-11-14")
            self.assertTrue(
                Path(tmp_dir, "previous_filings_20260329.csv").exists()
                or any(Path(tmp_dir).glob("previous_filings_*.csv"))
            )

    def test_get_all_previous_filings_skips_amendments(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tracker = SEC13FTracker(output_dir=tmp_dir)

            def fake_recent_filings(cik, fund_name, count=5, include_amendments=True):
                filings = [
                    {
                        "fund_name": fund_name,
                        "cik": cik,
                        "form_type": "13F-HR/A",
                        "filing_date": "2026-02-18",
                        "accession_number": "0000000000-26-000003",
                        "primary_document": "amendment.xml",
                    },
                    {
                        "fund_name": fund_name,
                        "cik": cik,
                        "form_type": "13F-HR",
                        "filing_date": "2026-02-14",
                        "accession_number": "0000000000-26-000002",
                        "primary_document": "latest.xml",
                    },
                    {
                        "fund_name": fund_name,
                        "cik": cik,
                        "form_type": "13F-HR",
                        "filing_date": "2025-11-14",
                        "accession_number": "0000000000-25-000001",
                        "primary_document": "previous.xml",
                    },
                ]
                if not include_amendments:
                    filings = [filing for filing in filings if filing["form_type"] == "13F-HR"]
                return filings[:count]

            with patch("biotech_fund_tracker.FUNDS", {"Test Fund": "1234567890"}):
                tracker.get_recent_filings = fake_recent_filings
                df = tracker.get_all_previous_filings()

            self.assertEqual(df.iloc[0]["form_type"], "13F-HR")
            self.assertEqual(df.iloc[0]["filing_date"], "2025-11-14")

    def test_print_menu_includes_previous_filings_option(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            print_menu()

        output = buffer.getvalue()
        self.assertIn("1. Get latest filings summary for all funds", output)
        self.assertIn("2. Get previous filings summary for all funds", output)
        self.assertIn("3. Get detailed holdings for a specific fund", output)
        self.assertIn("4. Get holdings for ALL funds from most recent filings", output)
        self.assertIn("5. Get holdings for ALL funds from previous recent filings", output)
        self.assertIn("9. Generate full summary report from most recent filings", output)
        self.assertIn("10. Generate full summary report from previous filings", output)
        self.assertIn("11. Get filings summary for any filing period", output)
        self.assertIn("12. Generate full summary report for any filing period", output)
        self.assertIn("13. Exit", output)

    def test_get_fund_holdings_continues_when_csv_is_locked(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tracker = SEC13FTracker(output_dir=tmp_dir)
            tracker.get_recent_filings = lambda cik, fund_name, count=1, include_amendments=True: [
                {
                    "fund_name": fund_name,
                    "cik": cik,
                    "form_type": "13F-HR",
                    "filing_date": "2026-02-13",
                    "accession_number": "0000000000-26-000001",
                    "primary_document": "holdings.xml",
                }
            ]
            holdings = FakeHoldings(should_raise_permission_error=True)
            tracker.parse_13f_xml = lambda accession_number, cik, primary_document=None: holdings

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                result = tracker.get_fund_holdings("Exome Asset Management LLC", "1234567890")

            self.assertIs(result, holdings)
            self.assertIn("Could not save to", buffer.getvalue())
            self.assertEqual(holdings.columns["fund_name"], "Exome Asset Management LLC")
            self.assertEqual(holdings.columns["filing_date"], "2026-02-13")

    def test_main_routes_previous_full_summary_command(self):
        from biotech_fund_tracker import main

        recorded_calls = []

        class FakeTracker:
            def generate_full_summary_report(self, filing_index=0, include_amendments=True, label="most_recent"):
                recorded_calls.append((filing_index, include_amendments, label))

        with patch("biotech_fund_tracker.SEC13FTracker", return_value=FakeTracker()):
            with patch("builtins.input", side_effect=["10", "13"]):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    main()

        self.assertIn((1, False, "previous"), recorded_calls)

    def test_main_routes_any_filings_summary_command(self):
        from biotech_fund_tracker import main

        recorded_calls = []

        class FakeTracker:
            def get_filings_summary(self, filing_index=0, label="latest", include_amendments=True):
                recorded_calls.append((filing_index, include_amendments, label))

        with patch("biotech_fund_tracker.SEC13FTracker", return_value=FakeTracker()):
            with patch("builtins.input", side_effect=["11", "3", "13"]):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    main()

        self.assertIn((2, False, "filing_3"), recorded_calls)

    def test_main_routes_any_full_summary_command(self):
        from biotech_fund_tracker import main

        recorded_calls = []

        class FakeTracker:
            def generate_full_summary_report(self, filing_index=0, include_amendments=True, label="most_recent"):
                recorded_calls.append((filing_index, include_amendments, label))

        with patch("biotech_fund_tracker.SEC13FTracker", return_value=FakeTracker()):
            with patch("builtins.input", side_effect=["12", "4", "13"]):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    main()

        self.assertIn((3, False, "filing_4"), recorded_calls)


if __name__ == "__main__":
    unittest.main()
