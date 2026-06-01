import unittest

from cup_racing_insights.models import Insight, InsightCategory
from cup_racing_insights.render.infographic import CareerSummary, build_card_payload


class InfographicPayloadTests(unittest.TestCase):
    def make_insights(self, count: int) -> list[Insight]:
        return [
            Insight(
                category=InsightCategory.STREAK,
                kind=f"streak_kind_{idx}",
                subject="Josie",
                headline=f"Streak insight {idx}",
            )
            for idx in range(count)
        ]

    def test_card_payload_can_bypass_generic_diversification(self):
        career = CareerSummary(
            races=1,
            wins=0,
            podiums=0,
            poles=0,
            points=0,
            top5=0,
            top5_pct=0.0,
        )

        payload = build_card_payload(
            "Josie",
            self.make_insights(6),
            career,
            top=6,
            diversify_output=False,
        )

        self.assertEqual(len(payload["insights"]), 6)

    def test_default_card_payload_still_diversifies(self):
        career = CareerSummary(
            races=1,
            wins=0,
            podiums=0,
            poles=0,
            points=0,
            top5=0,
            top5_pct=0.0,
        )

        payload = build_card_payload(
            "Josie",
            self.make_insights(6),
            career,
            top=6,
        )

        self.assertEqual(len(payload["insights"]), 4)


if __name__ == "__main__":
    unittest.main()
