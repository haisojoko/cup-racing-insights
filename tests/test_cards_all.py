import unittest
from unittest import mock

from cup_racing_insights import cards as cards_mod
from cup_racing_insights.cards import ALL_CARDS_TOKEN, Card
from cup_racing_insights.cli import _select_cards


class CardsAllExpansionTests(unittest.TestCase):
    def test_all_token_matches_registry(self):
        # The wildcard must yield exactly the live CARDS keys, in order.
        self.assertEqual(_select_cards(None, ALL_CARDS_TOKEN), list(cards_mod.CARDS.keys()))

    def test_all_token_picks_up_newly_added_cards(self):
        # Simulate a future card landing in the registry: --cards all must
        # include it without any other code change.
        extra = Card(
            name="hypothetical-future-card",
            title="Hypothetical Future Card",
            description="Stand-in for a card added in a future change.",
            include_kinds=(),
        )
        patched = {**cards_mod.CARDS, extra.name: extra}
        with mock.patch.object(cards_mod, "CARDS", patched):
            expanded = _select_cards(None, ALL_CARDS_TOKEN)
        self.assertIn(extra.name, expanded)
        self.assertEqual(expanded[-1], extra.name)

    def test_all_token_works_in_single_card_flag(self):
        self.assertEqual(_select_cards(ALL_CARDS_TOKEN, None), list(cards_mod.CARDS.keys()))

    def test_all_token_mixed_with_other_names_still_expands(self):
        # Any presence of the wildcard wins.
        self.assertEqual(
            _select_cards(None, f"venues,{ALL_CARDS_TOKEN}"),
            list(cards_mod.CARDS.keys()),
        )

    def test_no_card_uses_the_reserved_token(self):
        self.assertNotIn(ALL_CARDS_TOKEN, cards_mod.CARDS)


if __name__ == "__main__":
    unittest.main()
