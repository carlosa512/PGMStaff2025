import importlib.util
import math
import pathlib
import sys
import types
import unittest


def _load_update_contracts_module():
    # Keep tests independent from local pandas installs.
    fake_pandas = types.ModuleType("pandas")
    fake_pandas.isna = lambda value: value is None or (
        isinstance(value, float) and math.isnan(value)
    )
    sys.modules.setdefault("pandas", fake_pandas)

    module_path = (
        pathlib.Path(__file__).resolve().parents[1] / "scripts" / "update_contracts.py"
    )
    spec = importlib.util.spec_from_file_location("update_contracts", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


UC = _load_update_contracts_module()


class UpdateContractsTests(unittest.TestCase):
    def test_normalize_name_and_alias(self):
        self.assertEqual(UC.normalize_name("  Micah Parson Jr. "), "micah parson")
        canonical, alias_used = UC.apply_alias("micah parson")
        self.assertEqual(canonical, "micah parsons")
        self.assertEqual(alias_used, "micah parson -> micah parsons")

    def test_team_gated_matching(self):
        contract = {
            "original_name": "John Smith",
            "team": "DAL",
            "salary_source": "apy_fallback",
        }
        lookup_by_team = {("john smith", "DAL"): contract}
        lookup_by_name = {"john smith": [contract]}

        matched, status, _reason = UC.select_contract_for_player(
            "john smith", "DAL", lookup_by_team, lookup_by_name
        )
        self.assertIs(matched, contract)
        self.assertEqual(status, UC.STATUS_MATCHED_TEAM)

        matched, status, reason = UC.select_contract_for_player(
            "john smith", "NYJ", lookup_by_team, lookup_by_name
        )
        self.assertIsNone(matched)
        self.assertEqual(status, UC.STATUS_SKIPPED_TEAM_MISMATCH)
        self.assertIn("team_mismatch", reason)

    def test_teamless_unique_vs_ambiguous_matching(self):
        unique = {"team": "SEA", "original_name": "Unique Player", "salary_source": "apy_fallback"}
        options = [
            {"team": "BAL", "original_name": "Shared One", "salary_source": "apy_fallback"},
            {"team": "DET", "original_name": "Shared Two", "salary_source": "apy_fallback"},
        ]

        matched, status, _reason = UC.select_contract_for_player(
            "unique player",
            "Free Agent",
            {("unique player", "SEA"): unique},
            {"unique player": [unique]},
        )
        self.assertIs(matched, unique)
        self.assertEqual(status, UC.STATUS_MATCHED_NAME_ONLY)

        matched, status, reason = UC.select_contract_for_player(
            "shared name",
            "Rookie",
            {("shared name", "BAL"): options[0], ("shared name", "DET"): options[1]},
            {"shared name": options},
        )
        self.assertIsNone(matched)
        self.assertEqual(status, UC.STATUS_SKIPPED_AMBIGUOUS)
        self.assertIn("candidates", reason)

    def test_salary_uses_average_base_salary_and_length_uses_metadata(self):
        row = {
            "player": "Example Player",
            "team": "Cowboys",
            "year_signed": 2024,
            "years": 6,
            "apy": 42.0,
            "guaranteed": 7.0,
            "cols": [
                {"year": "2026", "cap_number": 10.0, "base_salary": 2.0, "guaranteed_salary": 1.0},
                {"year": "2027", "cap_number": 20.0, "base_salary": 6.0, "guaranteed_salary": 3.0},
            ],
        }

        contract = UC.extract_contract_data(row)
        self.assertEqual(contract["salary"], 4_000_000)
        self.assertEqual(contract["salary_source"], "avg_base_salary_remaining_years")
        self.assertEqual(contract["guarantee"], 4_000_000)
        # length must come from year_signed + years - CURRENT_YEAR, not year_data length
        self.assertEqual(contract["length"], 4)


if __name__ == "__main__":
    unittest.main()
