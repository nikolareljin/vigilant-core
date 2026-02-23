from __future__ import annotations

import unittest

from utils.sources import (
    _subject_context_categories,
    build_contextual_google_news_feeds,
    build_emergency_service_queries,
    infer_region_profile,
    regional_signal_sources,
    regional_signal_source_urls,
    build_utility_search_queries,
)


class SourceQueryTests(unittest.TestCase):
    def test_utility_queries_include_poweroutage_and_multi_utility_terms(self) -> None:
        queries = build_utility_search_queries("Dallas", "75201")
        combined = " || ".join(queries).lower()
        self.assertIn("poweroutage.us", combined)
        self.assertIn("water utility", combined)
        self.assertIn("gas utility", combined)
        self.assertIn("wind farm outage", combined)
        self.assertIn("solar outage", combined)

    def test_emergency_service_queries_include_transport_and_aviation(self) -> None:
        queries = build_emergency_service_queries("Dallas", "75201")
        combined = " || ".join(queries).lower()
        self.assertIn("traffic alerts", combined)
        self.assertIn("transit service alerts", combined)
        self.assertIn("airport operations alerts", combined)
        self.assertIn("faa ground stop", combined)
        self.assertIn("flood warning", combined)
        self.assertIn("tornado warning", combined)

    def test_contextual_google_news_feeds_expand_for_conflict(self) -> None:
        feeds = build_contextual_google_news_feeds(
            "war conflict escalation and missile strikes",
            "Ukraine",
        )
        text = " || ".join(feeds).lower()
        self.assertIn("news.google.com/rss/search", text)
        self.assertIn("ukraine+conflict+escalation", text)
        self.assertIn("global+conflict+alerts", text)

    def test_contextual_google_news_feeds_respects_max_feeds_limit(self) -> None:
        feeds = build_contextual_google_news_feeds(
            "power water gas renewables transport aviation fire flood tornado winter earthquake war conflict",
            "Berlin",
            max_feeds=5,
        )
        self.assertLessEqual(len(feeds), 5)

    def test_region_inference_uses_coordinates_without_location_text(self) -> None:
        region = infer_region_profile(latitude=48.8566, longitude=2.3522)  # Paris
        self.assertEqual(region.key, "europe")
        feeds = build_contextual_google_news_feeds(
            "flooding and transport disruption",
            "",
            latitude=48.8566,
            longitude=2.3522,
        )
        self.assertTrue(any("gl=GB" in feed and "ceid=GB:en" in feed for feed in feeds))

    def test_region_inference_plain_us_city_name_defaults_to_us(self) -> None:
        self.assertEqual(infer_region_profile(location_name="Dallas").key, "us")
        self.assertEqual(infer_region_profile(location_name="Austin").key, "us")

    def test_region_inference_does_not_route_houston_coords_to_central_america(self) -> None:
        region = infer_region_profile(latitude=29.7604, longitude=-95.3698)  # Houston
        self.assertEqual(region.key, "us")

    def test_region_inference_routes_guatemala_city_to_central_america(self) -> None:
        region = infer_region_profile(latitude=14.6349, longitude=-90.5069)  # Guatemala City
        self.assertEqual(region.key, "central_america")

    def test_region_inference_keeps_northern_us_cities_as_us_not_canada(self) -> None:
        seattle = infer_region_profile(latitude=47.6062, longitude=-122.3321)  # Seattle
        chicago = infer_region_profile(latitude=41.8781, longitude=-87.6298)  # Chicago
        self.assertEqual(seattle.key, "us")
        self.assertEqual(chicago.key, "us")

    def test_region_inference_treats_honolulu_as_us_outside_continental_box(self) -> None:
        region = infer_region_profile(latitude=21.3069, longitude=-157.8583)  # Honolulu
        self.assertEqual(region.key, "us")

    def test_regional_signal_sources_cover_requested_regions(self) -> None:
        europe_urls = {s.url for s in regional_signal_sources(latitude=50.1109, longitude=8.6821)}  # Frankfurt
        canada_urls = {s.url for s in regional_signal_sources(latitude=43.6532, longitude=-79.3832)}  # Toronto
        australia_urls = {s.url for s in regional_signal_sources(latitude=-33.8688, longitude=151.2093)}  # Sydney
        sa_urls = {s.url for s in regional_signal_sources(latitude=-26.2041, longitude=28.0473)}  # Johannesburg

        self.assertIn("https://www.meteoalarm.org", europe_urls)
        self.assertIn("https://weather.gc.ca", canada_urls)
        self.assertIn("https://www.bom.gov.au", australia_urls)
        self.assertIn("https://www.eskom.co.za", sa_urls)

    def test_regional_signal_sources_cover_additional_regions_from_coords(self) -> None:
        me_urls = set(regional_signal_source_urls(latitude=25.2048, longitude=55.2708))  # Dubai
        sa_asia_urls = set(regional_signal_source_urls(latitude=28.6139, longitude=77.2090))  # Delhi
        sea_urls = set(regional_signal_source_urls(latitude=13.7563, longitude=100.5018))  # Bangkok
        ssa_urls = set(regional_signal_source_urls(latitude=6.5244, longitude=3.3792))  # Lagos

        self.assertIn("https://www.aljazeera.com", me_urls)
        self.assertIn("https://mausam.imd.gov.in", sa_asia_urls)
        self.assertIn("https://www.bmkg.go.id", sea_urls)
        self.assertIn("https://www.kplc.co.ke", ssa_urls)

    def test_region_overlap_precedence_keeps_north_africa_over_sub_saharan(self) -> None:
        region = infer_region_profile(latitude=18.0, longitude=31.0)  # Sudan overlap band
        self.assertEqual(region.key, "north_africa")

    def test_conflict_keyword_detection_avoids_substring_false_positives(self) -> None:
        self.assertNotIn("conflict", _subject_context_categories("hardware supply chain delays"))
        self.assertIn("conflict", _subject_context_categories("war escalation and missile strikes"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
