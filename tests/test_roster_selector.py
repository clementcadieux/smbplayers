from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smb4_mlb_ratings.cli import main
from smb4_mlb_ratings.models import RatingOutput
from smb4_mlb_ratings.roster_selector import rank_players_by_role, select_roster


class RosterSelectorTests(unittest.TestCase):
    def test_select_roster_fills_expected_slot_counts(self) -> None:
        roster = select_roster(self._team_players())

        self.assertEqual(len(roster), 22)
        self.assertEqual(sum(slot.position_group == "SP" for slot in roster), 4)
        self.assertEqual(sum(slot.position_group == "RP" for slot in roster), 5)
        self.assertEqual(sum(slot.position_group == "C" for slot in roster), 2)
        self.assertEqual(sum(slot.position_group == "IF" for slot in roster), 6)
        self.assertEqual(sum(slot.position_group == "OF" for slot in roster), 5)

    def test_rank_players_by_role_uses_age_as_tiebreaker(self) -> None:
        younger = self._player("Younger IF", "hitter", "2B", projected_pa=400, age=22, overall=72)
        older = self._player("Older IF", "hitter", "3B", projected_pa=400, age=31, overall=72)

        ranked = rank_players_by_role([older, younger])

        self.assertEqual([player.name for player in ranked["IF"]], ["Younger IF", "Older IF"])

    def test_select_roster_chooses_best_two_flex_options(self) -> None:
        roster = select_roster(self._team_players())
        flex_players = {slot.player.name for slot in roster if slot.slot_type.startswith("flex_")}

        self.assertEqual(flex_players, {"Sixth Infielder", "Fifth Outfielder"})

    def test_rank_players_by_role_deprioritizes_injured_players_on_ties(self) -> None:
        healthy = self._player("Healthy OF", "hitter", "CF", projected_pa=350, age=26, overall=70)
        injured = self._player("Injured OF", "hitter", "RF", projected_pa=350, age=26, overall=70)

        ranked = rank_players_by_role([injured, healthy], injured_list={"Injured OF"})

        self.assertEqual([player.name for player in ranked["OF"]], ["Healthy OF", "Injured OF"])

    def test_rank_players_by_role_uses_all_secondary_positions(self) -> None:
        utility = self._player(
            "Multi Position Utility",
            "hitter",
            "1B",
            secondary_positions=["RF", "CF", "3B"],
            projected_pa=350,
            age=26,
            overall=74,
        )

        ranked = rank_players_by_role([utility])

        self.assertEqual([player.name for player in ranked["IF"]], ["Multi Position Utility"])
        self.assertEqual([player.name for player in ranked["OF"]], ["Multi Position Utility"])

    def test_select_roster_assigns_multi_eligible_player_once(self) -> None:
        players = self._team_players()
        players.append(
            self._player(
                "Super Utility",
                "hitter",
                "SS",
                secondary_positions=["2B", "3B", "LF", "CF"],
                projected_pa=360,
                age=24,
                overall=90,
            )
        )

        roster = select_roster(players)
        selected_names = [slot.player.name for slot in roster]

        self.assertEqual(selected_names.count("Super Utility"), 1)

    def test_cli_rank_writes_team_rosters(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            input_path = root / "ratings.json"
            output_path = root / "roster.json"
            input_path.write_text(json.dumps([player.to_dict() for player in self._team_players()], indent=2), encoding="utf-8")

            result = main(["rank", str(input_path), str(output_path)])

            self.assertEqual(result, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["teams"][0]["team"], "NYM")
            self.assertEqual(len(payload["teams"][0]["recommended_roster"]), 22)

    def test_select_roster_rejects_players_from_other_teams_when_target_team_is_given(self) -> None:
        players = self._team_players()
        players.append(self._player("Wrong Team", "hitter", "LF", projected_pa=250, age=26, overall=68, team="ATL"))

        with self.assertRaisesRegex(ValueError, "matching team"):
            select_roster(players, target_team="NYM")

    def _team_players(self) -> list[RatingOutput]:
        players: list[RatingOutput] = []
        for index in range(4):
            players.append(self._player(f"Starter {index + 1}", "pitcher", "P", projected_ip=150 - index * 5, age=27 + index, overall=82 - index, metadata={"pitching_role": "starter"}))
        for index in range(5):
            players.append(self._player(f"Reliever {index + 1}", "pitcher", "P", projected_ip=60 - index * 2, age=28 + index, overall=74 - index, metadata={"pitching_role": "reliever"}))
        for index in range(2):
            players.append(self._player(f"Catcher {index + 1}", "hitter", "C", projected_pa=420 - index * 15, age=25 + index, overall=73 - index))
        players.append(self._player("Third Catcher", "hitter", "C", projected_pa=240, age=29, overall=70))
        for index in range(5):
            players.append(self._player(f"Infielder {index + 1}", "hitter", "2B", projected_pa=500 - index * 20, age=24 + index, overall=78 - index))
        players.append(self._player("Sixth Infielder", "hitter", "SS", projected_pa=330, age=24, overall=88))
        for index in range(4):
            players.append(self._player(f"Outfielder {index + 1}", "hitter", "CF", projected_pa=510 - index * 20, age=23 + index, overall=79 - index))
        players.append(self._player("Fifth Outfielder", "hitter", "RF", projected_pa=315, age=25, overall=85))
        return players

    def _player(
        self,
        name: str,
        role: str,
        primary_position: str,
        *,
        projected_pa: float | None = None,
        projected_ip: float | None = None,
        age: int = 27,
        overall: int = 75,
        metadata: dict[str, object] | None = None,
        team: str = "NYM",
        secondary_positions: list[str] | None = None,
    ) -> RatingOutput:
        return RatingOutput(
            name=name,
            role=role,
            team=team,
            primary_position=primary_position,
            bats=None,
            throws=None,
            ratings={"overall": overall},
            percentiles={"overall": float(overall)},
            overall_numeric=overall,
            overall_grade="B",
            confidence="high",
            review_flags=[],
            suggested_traits=[],
            assigned_traits=[],
            recommended_personalities=[],
            secondary_position=None,
            secondary_positions=secondary_positions or [],
            age=age,
            projected_pa=projected_pa,
            projected_ip=projected_ip,
            metadata=metadata or {},
        )


if __name__ == "__main__":
    unittest.main()