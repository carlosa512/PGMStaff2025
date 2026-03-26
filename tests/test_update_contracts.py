import importlib.util
import json
import math
import pathlib
import sys
import tempfile
import types
import unittest


def _load_update_contracts_module():
    # Keep tests independent from local pandas installs.
    fake_pandas = types.ModuleType("pandas")
    fake_pandas.isna = lambda value: value is None or (
        isinstance(value, float) and math.isnan(value)
    )
    sys.modules.setdefault("pandas", fake_pandas)

    module_path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "update_contracts.py"
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
            "guarantee_source": "current_year_bonus_components",
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
        unique = {
            "team": "SEA",
            "original_name": "Unique Player",
            "salary_source": "apy_fallback",
            "guarantee_source": "current_year_bonus_components",
        }
        options = [
            {
                "team": "BAL",
                "original_name": "Shared One",
                "salary_source": "apy_fallback",
                "guarantee_source": "current_year_bonus_components",
            },
            {
                "team": "DET",
                "original_name": "Shared Two",
                "salary_source": "apy_fallback",
                "guarantee_source": "current_year_bonus_components",
            },
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

    def test_salary_uses_limited_remaining_years(self):
        row = {
            "player": "Example Player",
            "team": "Cowboys",
            "year_signed": 2024,
            "years": 4,
            "apy": 42.0,
            "cols": [
                {"year": "2026", "cap_number": 10.0, "base_salary": 2.0},
                {"year": "2027", "cap_number": 20.0, "base_salary": 6.0},
                {"year": "2028", "cap_number": 30.0, "base_salary": 200.0},
            ],
        }

        contract = UC.extract_contract_data(row)
        # remaining_years=2 -> use first two base salaries only: (2+6)/2
        self.assertEqual(contract["salary"], 4_000_000)
        self.assertEqual(contract["salary_source"], "avg_base_salary_remaining_years_limited")
        self.assertEqual(contract["length"], 2)

    def test_salary_window_does_not_pull_later_years(self):
        row = {
            "player": "Window Player",
            "team": "Cowboys",
            "year_signed": 2024,
            "years": 4,
            "apy": 7.0,
            "cols": [
                {"year": "2026", "cap_number": 10.0, "base_salary": 0.0},
                {"year": "2027", "cap_number": 20.0, "base_salary": 0.0},
                {"year": "2028", "cap_number": 30.0, "base_salary": 100.0},
            ],
        }

        contract = UC.extract_contract_data(row)
        self.assertEqual(contract["length"], 2)
        self.assertEqual(contract["salary"], 7_000_000)
        self.assertEqual(contract["salary_source"], "apy_fallback")

    def test_bonus_uses_current_year_components_with_fallback(self):
        row_bonus = {
            "player": "Bonus Player",
            "team": "Cowboys",
            "year_signed": 2024,
            "years": 3,
            "apy": 10.0,
            "cols": [
                {
                    "year": "2026",
                    "cap_number": 11.0,
                    "base_salary": 3.0,
                    "guaranteed_salary": 0.0,
                    "prorated_bonus": 4.0,
                    "roster_bonus": 2.0,
                    "option_bonus": 1.0,
                    "other_bonus": 0.5,
                    "per_game_roster_bonus": 0.25,
                    "workout_bonus": 0.25,
                }
            ],
        }
        contract_bonus = UC.extract_contract_data(row_bonus)
        self.assertEqual(contract_bonus["guarantee"], 8_000_000)
        self.assertEqual(contract_bonus["guarantee_source"], "current_year_bonus_components")

        row_fallback = {
            "player": "Fallback Player",
            "team": "Cowboys",
            "year_signed": 2024,
            "years": 3,
            "apy": 10.0,
            "cols": [
                {
                    "year": "2026",
                    "cap_number": 11.0,
                    "base_salary": 3.0,
                    "guaranteed_salary": 5.0,
                    "prorated_bonus": 0.0,
                    "roster_bonus": 0.0,
                    "option_bonus": 0.0,
                    "other_bonus": 0.0,
                    "per_game_roster_bonus": 0.0,
                    "workout_bonus": 0.0,
                }
            ],
        }
        contract_fallback = UC.extract_contract_data(row_fallback)
        self.assertEqual(contract_fallback["guarantee"], 5_000_000)
        self.assertEqual(
            contract_fallback["guarantee_source"],
            "current_year_guaranteed_salary_fallback",
        )

    def test_zero_contract_fields_for_free_agents(self):
        player = {
            "teamID": "Free Agent",
            "salary": 123,
            "eSalary": 200,
            "guarantee": 456,
            "eGuarantee": 500,
            "length": 3,
            "eLength": 4,
        }
        changed = UC.zero_contract_fields(player, free_agent_length=0)
        self.assertTrue(changed)
        self.assertEqual(player["salary"], 0)
        self.assertEqual(player["eSalary"], 0)
        self.assertEqual(player["guarantee"], 0)
        self.assertEqual(player["eGuarantee"], 0)
        self.assertEqual(player["length"], 0)
        self.assertEqual(player["eLength"], 0)

    def test_release_override_moves_player_to_fa_and_zeroes_contract(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = pathlib.Path(tmp_dir)
            roster_path = tmp_path / "roster.json"
            report_path = tmp_path / "report.csv"
            team_cap_report_path = tmp_path / "team_cap.csv"

            roster = [
                {
                    "forename": "Tyreek",
                    "surname": "Hill",
                    "teamID": "MIA",
                    "salary": 20_000_000,
                    "eSalary": 19_000_000,
                    "guarantee": 30_000_000,
                    "eGuarantee": 29_000_000,
                    "length": 3,
                    "eLength": 2,
                }
            ]
            roster_path.write_text(json.dumps(roster), encoding="utf-8")

            status_counts, total = UC.apply_contracts(
                str(roster_path),
                {},
                {},
                {"tyreek hill": "confirmed_release"},
                str(report_path),
                str(team_cap_report_path),
            )

            updated = json.loads(roster_path.read_text(encoding="utf-8"))
            player = updated[0]
            self.assertEqual(total, 1)
            self.assertEqual(player["teamID"], "Free Agent")
            self.assertEqual(player["salary"], 0)
            self.assertEqual(player["eSalary"], 0)
            self.assertEqual(player["guarantee"], 0)
            self.assertEqual(player["eGuarantee"], 0)
            self.assertEqual(player["length"], 0)
            self.assertEqual(player["eLength"], 0)
            self.assertEqual(status_counts[UC.STATUS_RELEASE_OVERRIDE], 1)
            self.assertEqual(status_counts[UC.STATUS_FA_NORMALIZED], 0)

    def test_free_agent_normalization_zeroes_contract(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = pathlib.Path(tmp_dir)
            roster_path = tmp_path / "roster.json"
            report_path = tmp_path / "report.csv"
            team_cap_report_path = tmp_path / "team_cap.csv"

            roster = [
                {
                    "forename": "Justin",
                    "surname": "Simmons",
                    "teamID": "Free Agent",
                    "salary": 9_000_000,
                    "eSalary": 8_000_000,
                    "guarantee": 3_000_000,
                    "eGuarantee": 2_000_000,
                    "length": 1,
                    "eLength": 1,
                }
            ]
            roster_path.write_text(json.dumps(roster), encoding="utf-8")

            status_counts, _total = UC.apply_contracts(
                str(roster_path),
                {},
                {},
                {},
                str(report_path),
                str(team_cap_report_path),
            )
            updated = json.loads(roster_path.read_text(encoding="utf-8"))
            player = updated[0]
            self.assertEqual(player["salary"], 0)
            self.assertEqual(player["eSalary"], 0)
            self.assertEqual(player["guarantee"], 0)
            self.assertEqual(player["eGuarantee"], 0)
            self.assertEqual(player["length"], 0)
            self.assertEqual(player["eLength"], 0)
            self.assertEqual(status_counts[UC.STATUS_FA_NORMALIZED], 1)

    def test_contract_field_parity_preserved_on_match(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = pathlib.Path(tmp_dir)
            roster_path = tmp_path / "roster.json"
            report_path = tmp_path / "report.csv"
            team_cap_report_path = tmp_path / "team_cap.csv"

            roster = [
                {
                    "forename": "Dak",
                    "surname": "Prescott",
                    "teamID": "DAL",
                    "salary": 1,
                    "eSalary": 2,
                    "guarantee": 3,
                    "eGuarantee": 4,
                    "length": 5,
                    "eLength": 6,
                }
            ]
            roster_path.write_text(json.dumps(roster), encoding="utf-8")

            contract = {
                "salary": 25_000_000,
                "guarantee": 8_000_000,
                "length": 2,
                "team": "DAL",
                "original_name": "Dak Prescott",
                "salary_source": "avg_base_salary_remaining_years_limited",
                "guarantee_source": "current_year_bonus_components",
            }

            UC.apply_contracts(
                str(roster_path),
                {("dak prescott", "DAL"): contract},
                {"dak prescott": [contract]},
                {},
                str(report_path),
                str(team_cap_report_path),
            )

            updated = json.loads(roster_path.read_text(encoding="utf-8"))
            player = updated[0]
            self.assertEqual(player["salary"], 25_000_000)
            self.assertEqual(player["eSalary"], 25_000_000)
            self.assertEqual(player["guarantee"], 8_000_000)
            self.assertEqual(player["eGuarantee"], 8_000_000)
            self.assertEqual(player["length"], 2)
            self.assertEqual(player["eLength"], 2)

    def test_load_release_overrides(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = pathlib.Path(tmp_dir) / "release_overrides.csv"
            csv_path.write_text(
                "forename,surname,reason\n"
                "Tyreek,Hill,confirmed_release\n"
                "Keenan,Allen,confirmed_release\n",
                encoding="utf-8",
            )
            overrides = UC.load_release_overrides(str(csv_path))
            self.assertIn("tyreek hill", overrides)
            self.assertIn("keenan allen", overrides)
            self.assertEqual(overrides["tyreek hill"], "confirmed_release")


if __name__ == "__main__":
    unittest.main()
