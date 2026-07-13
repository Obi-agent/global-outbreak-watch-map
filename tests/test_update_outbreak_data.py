import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update_outbreak_data.py"
SPEC = importlib.util.spec_from_file_location("update_outbreak_data", SCRIPT)
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class OutbreakDataTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)
        self.source = updater.SOURCES[0]

    def test_drc_does_not_also_emit_republic_of_congo(self):
        found = updater.places("Ebola update in the Democratic Republic of the Congo")
        self.assertIn("Democratic Republic of the Congo", found)
        self.assertNotIn("Congo", found)

    def test_lowercase_us_is_not_treated_as_united_states(self):
        self.assertEqual(["Global"], updater.places("Contact us for more information"))

    def test_signal_location_prefers_specific_outbreak_title(self):
        found = updater.signal_places(
            self.source,
            "Ebola virus disease - Democratic Republic of the Congo",
            "The authority notice also references technical support from France.",
        )
        self.assertEqual(["Democratic Republic of the Congo"], found)

    def test_weekly_signal_uses_leading_outbreak_context(self):
        source = next(item for item in updater.SOURCES if item["id"] == "ukhsa-monitoring")
        found = updater.signal_places(
            source,
            "Outbreaks under monitoring: week 27",
            "An outbreak was declared in the Democratic Republic of the Congo and Uganda. "
            + ("Operational context. " * 30)
            + "A technical partner in the United Kingdom provided support.",
        )
        self.assertEqual(["Democratic Republic of the Congo", "Uganda"], found)

    def test_navigation_and_date_labels_are_suspicious(self):
        self.assertTrue(updater.label_is_suspicious("Pagination"))
        self.assertTrue(updater.label_is_suspicious("13 July 2026"))
        self.assertFalse(updater.label_is_suspicious("Cholera outbreak update in Angola"))

    def test_feature_has_explainable_assessments(self):
        item = updater.feature(
            self.source,
            "Cholera outbreak update in Uganda",
            "The health ministry reports a cholera outbreak with hospitalised cases and response measures.",
            "https://example.test/cholera-update",
            self.now,
            "Uganda",
            0,
            self.now,
        )
        props = item["properties"]
        self.assertEqual("High", props["Severity"])
        self.assertGreaterEqual(props["Confidence_Score"], 80)
        self.assertEqual("Country", props["Geographic_Precision"])
        self.assertTrue(props["Severity_Rationale"])
        self.assertTrue(props["Confidence_Rationale"])

    def test_missing_publication_date_is_visible_in_quality_notes(self):
        item = updater.feature(
            self.source,
            "Dengue outbreak in Brazil",
            "The authority reports a dengue outbreak and continuing response measures in affected communities.",
            "https://example.test/dengue-undated",
            None,
            "Brazil",
            0,
            self.now,
        )
        props = item["properties"]
        self.assertIn("Publication date unavailable; refresh time used.", props["Quality_Notes"])
        self.assertFalse(any("publication date was parsed" in reason.lower() for reason in props["Confidence_Rationale"]))

    def test_incident_builder_merges_matching_disease_and_country(self):
        first = updater.feature(
            self.source,
            "Measles update in the United States",
            "A public health authority reports continued measles monitoring and response activity.",
            "https://example.test/measles-one",
            self.now,
            "United States",
            0,
            self.now,
        )
        second_source = updater.SOURCES[1]
        second = updater.feature(
            second_source,
            "Measles outbreak in the United States",
            "A second authority has published an update on the same measles incident.",
            "https://example.test/measles-two",
            self.now,
            "United States",
            0,
            self.now,
        )
        incidents = updater.build_incidents([first, second], self.now)
        self.assertEqual(1, len(incidents))
        self.assertEqual(2, incidents[0]["Source_Count"])
        self.assertEqual(2, incidents[0]["Update_Count"])
        self.assertEqual("Stable", incidents[0]["Trend"])
        self.assertEqual("Country centroid", incidents[0]["Geographic_Precision"])

    def test_directional_trend_uses_authority_language(self):
        worsening, worsening_reason = updater.trend_assessment(
            [{"Title": "Cholera update", "Situation_Snapshot": "Cases increased by 120 and cross-border spread was reported.", "Date_Last_Updated": "2026-07-13"}],
            "Open",
            self.now,
        )
        improving, improving_reason = updater.trend_assessment(
            [{"Title": "Outbreak update", "Situation_Snapshot": "No new cases have been reported and the outbreak is contained.", "Date_Last_Updated": "2026-07-13"}],
            "Monitoring",
            self.now,
        )
        self.assertEqual("Worsening", worsening)
        self.assertIn("rising burden", worsening_reason)
        self.assertEqual("Improving", improving)
        self.assertIn("no new cases", improving_reason)

    def test_quality_summary_distinguishes_last_known_good(self):
        item = updater.feature(
            self.source,
            "Dengue update in Brazil",
            "The authority reports a dengue outbreak and continuing public health monitoring activity.",
            "https://example.test/dengue",
            self.now,
            "Brazil",
            0,
            self.now,
        )
        statuses = [
            {"status": "ok"},
            {"status": "using_last_known_good"},
            {"status": "error"},
        ]
        summary = updater.build_quality_summary([item], [], statuses)
        self.assertEqual(1, summary["sources_ok"])
        self.assertEqual(1, summary["sources_last_known_good"])
        self.assertEqual(1, summary["sources_error"])

    def test_failed_source_can_retain_recent_last_known_good_signal(self):
        item = updater.feature(
            self.source,
            "Cholera outbreak in Uganda",
            "The authority reports a cholera outbreak with public health response measures in Uganda.",
            "https://example.test/cholera-retained",
            self.now,
            "Uganda",
            0,
            self.now,
        )
        carried = updater.carry_forward_features({"features": [item]}, self.source, self.now, set())
        self.assertEqual(1, len(carried))
        self.assertTrue(carried[0]["properties"]["Is_Stale"])
        self.assertEqual("Last known good", carried[0]["properties"]["Data_State"])


if __name__ == "__main__":
    unittest.main()
