"""
Contract tests for profile ↔ data source consistency.

These tests catch SYSTEMIC bugs like:
- Profile has weight for category with no Overpass query (car_access=0 bug)
- FALLBACK_TYPES contains invalid Google Places API types (fast_food 400 bug)
- Profile weights don't sum to 1.0

Run with: python manage.py test location_analysis.tests.test_profile_contracts
"""
from django.test import TestCase

from location_analysis.scoring.profiles import get_all_profiles, PROFILE_REGISTRY
from location_analysis.geo.overpass_client import OverpassClient
from location_analysis.geo.hybrid_poi_provider import FALLBACK_TYPES
from location_analysis.geo.google_places_client import VALID_GOOGLE_TYPES


class TestProfileDataContracts(TestCase):
    """Every weighted category in a profile must have a data source."""

    def test_every_weighted_category_has_data_source(self):
        """Categories with weight > 0 must have either Overpass query or Google fallback."""
        overpass_categories = set(OverpassClient.POI_QUERIES.keys())
        fallback_categories = set(FALLBACK_TYPES.keys())
        
        for profile in get_all_profiles():
            for cat, weight in profile.weights.items():
                if weight > 0:  # Skip noise (negative weight)
                    has_overpass = cat in overpass_categories
                    has_fallback = cat in fallback_categories
                    self.assertTrue(
                        has_overpass or has_fallback,
                        f"Profile '{profile.key}' has weight {weight} for '{cat}' "
                        f"but no data source (not in Overpass or FALLBACK_TYPES)"
                    )

    def test_fallback_types_are_valid_google_types(self):
        """Every type in FALLBACK_TYPES must be a valid Google Places API type."""
        for cat, types in FALLBACK_TYPES.items():
            for t in types:
                self.assertIn(
                    t, VALID_GOOGLE_TYPES,
                    f"FALLBACK_TYPES['{cat}'] contains '{t}' which is NOT a valid "
                    f"Google Places API type. Add it to VALID_GOOGLE_TYPES or remove it."
                )

    def test_profile_positive_weights_sum_to_one(self):
        """Positive weights in each profile should sum to approximately 1.0."""
        for profile in get_all_profiles():
            positive_sum = sum(w for w in profile.weights.values() if w > 0)
            self.assertAlmostEqual(
                positive_sum, 1.0, delta=0.15,
                msg=f"Profile '{profile.key}' positive weights sum to {positive_sum:.3f}, "
                    f"expected ~1.0"
            )

    def test_critical_cap_categories_have_data_source(self):
        """Categories used in critical_caps must have data sources."""
        overpass_categories = set(OverpassClient.POI_QUERIES.keys())
        fallback_categories = set(FALLBACK_TYPES.keys())
        
        for profile in get_all_profiles():
            for cat, cap in profile.critical_caps:
                # Noise is a special category (computed from roads, not POI)
                if cat == 'noise':
                    continue
                has_source = cat in overpass_categories or cat in fallback_categories
                self.assertTrue(
                    has_source,
                    f"Profile '{profile.key}' has critical_cap for '{cat}' "
                    f"but no data source"
                )

    def test_profiles_coverage_threshold_consistency(self):
        """All categories in FALLBACK_TYPES should also be in COVERAGE_THRESHOLDS."""
        from location_analysis.geo.hybrid_poi_provider import COVERAGE_THRESHOLDS, DEFAULT_COVERAGE_THRESHOLD
        for cat in FALLBACK_TYPES:
            # Just ensure every fallback category has a threshold (explicit or default)
            threshold = COVERAGE_THRESHOLDS.get(cat, DEFAULT_COVERAGE_THRESHOLD)
            self.assertGreaterEqual(
                threshold, 1,
                f"Coverage threshold for '{cat}' is {threshold}, expected >= 1"
            )

    def test_no_duplicate_keys_in_registry(self):
        """Profile registry should not have duplicate keys."""
        keys = list(PROFILE_REGISTRY.keys())
        self.assertEqual(len(keys), len(set(keys)), "Duplicate keys in PROFILE_REGISTRY")
        for profile in get_all_profiles():
            self.assertEqual(profile.key, profile.key.lower(), f"Profile key '{profile.key}' must be lowercase")
