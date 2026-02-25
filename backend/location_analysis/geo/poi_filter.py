"""
Filtrowanie POI per kategoria na podstawie promienia.
"""
import logging
from typing import Dict, List, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from .overpass_client import POI

logger = logging.getLogger(__name__)


# ============================================================================
# CATEGORY MEMBERSHIP WHITELISTS
# ============================================================================

# Food category - strict whitelist
FOOD_OSM_AMENITIES = frozenset({
    'restaurant', 'cafe', 'fast_food', 'bar', 'pub', 
    'ice_cream', 'food_court', 'biergarten'
})
FOOD_OSM_SHOPS = frozenset({
    'bakery', 'confectionery', 'deli', 'butcher', 'greengrocer',
    'convenience', 'supermarket', 'grocery', 'cheese', 'seafood',
    'pastry', 'coffee', 'tea', 'wine', 'alcohol', 'beverages'
})
FOOD_GOOGLE_TYPES = frozenset({
    'restaurant', 'cafe', 'meal_takeaway', 'meal_delivery',
    'bakery', 'bar', 'food', 'grocery_or_supermarket'
})

# Health category whitelist
HEALTH_OSM_AMENITIES = frozenset({
    'pharmacy', 'doctors', 'hospital', 'clinic', 'dentist',
    'veterinary', 'optician'
})
HEALTH_OSM_SHOPS = frozenset({
    'optician', 'medical_supply', 'hearing_aids'
})
HEALTH_GOOGLE_TYPES = frozenset({
    'pharmacy', 'hospital', 'doctor', 'dentist', 'health',
    'physiotherapist', 'veterinary_care'
})

# Education category whitelist  
EDUCATION_OSM_AMENITIES = frozenset({
    'school', 'kindergarten', 'university', 'college', 'library',
    'language_school', 'music_school', 'driving_school', 'training'
})
EDUCATION_GOOGLE_TYPES = frozenset({
    'school', 'primary_school', 'secondary_school', 'university',
    'library', 'preschool'
})

# Shops category - daily shopping whitelist (strict mode)
SHOPS_DAILY_OSM = frozenset({
    'supermarket', 'convenience', 'grocery', 'bakery', 'butcher',
    'greengrocer', 'deli', 'chemist', 'pharmacy', 'optician',
    'newsagent', 'kiosk', 'tobacco', 'alcohol', 'beverages'
})


def validate_category_membership(poi: "POI", category: str) -> bool:
    """
    Sprawdza czy POI rzeczywiście należy do danej kategorii.
    
    Returns:
        True jeśli POI pasuje do kategorii, False jeśli nie
    """
    tags = poi.tags or {}
    amenity = tags.get('amenity', '')
    shop = tags.get('shop', '')
    google_types = set(tags.get('types', []) or [])
    source = tags.get('source', poi.source)
    
    # For Google fallback / enriched / merged - check Google types strictly
    if source in ('google_fallback', 'google', 'google_enriched', 'merged'):
        if category == 'food':
            return bool(google_types & FOOD_GOOGLE_TYPES)
        elif category == 'health':
            return bool(google_types & HEALTH_GOOGLE_TYPES)
        elif category == 'education':
            return bool(google_types & EDUCATION_GOOGLE_TYPES)
        # Other categories - trust Google classification
        return True
    
    # For OSM - check OSM tags
    if category == 'food':
        return amenity in FOOD_OSM_AMENITIES or shop in FOOD_OSM_SHOPS
    elif category == 'health':
        return amenity in HEALTH_OSM_AMENITIES or shop in HEALTH_OSM_SHOPS
    elif category == 'education':
        return amenity in EDUCATION_OSM_AMENITIES
    
    # Other categories - trust OSM classification
    return True


def filter_by_membership(
    pois_by_category: Dict[str, List["POI"]],
    trace_ctx: 'AnalysisTraceContext | None' = None,
) -> Dict[str, List["POI"]]:
    """
    Filtruje POI - zostawia tylko te które rzeczywiście pasują do kategorii.
    """
    from ..diagnostics import get_diag_logger, AnalysisTraceContext
    ctx = trace_ctx or AnalysisTraceContext()
    slog = get_diag_logger(__name__, ctx)

    result: Dict[str, List["POI"]] = {}
    
    for category, pois in pois_by_category.items():
        valid = []
        invalid_count = 0
        
        for poi in pois:
            if validate_category_membership(poi, category):
                valid.append(poi)
            else:
                invalid_count += 1
        
        if invalid_count > 0:
            slog.checkpoint(
                stage="filter", category=category,
                count_raw=len(pois), count_kept=len(valid),
                provider="membership", op="filter_membership",
            )
        
        result[category] = valid
    
    return result


def filter_by_radius(
    pois_by_category: Dict[str, List["POI"]],
    radius_by_category: Dict[str, int],
    default_radius: int = 500,
    trace_ctx: 'AnalysisTraceContext | None' = None,
) -> Dict[str, List["POI"]]:
    """
    Filtruje POI - zostawia tylko te w promieniu danej kategorii.
    
    Args:
        pois_by_category: Słownik kategorii → lista POI
        radius_by_category: Słownik kategorii → max promień w metrach
        default_radius: Domyślny promień jeśli kategoria nie ma określonego
        
    Returns:
        Przefiltrowany słownik POI
    """
    from ..diagnostics import get_diag_logger, AnalysisTraceContext
    ctx = trace_ctx or AnalysisTraceContext()
    slog = get_diag_logger(__name__, ctx)

    result: Dict[str, List["POI"]] = {}
    
    for category, pois in pois_by_category.items():
        max_distance = radius_by_category.get(category, default_radius)
        filtered = [p for p in pois if p.distance_m <= max_distance]
        
        if len(filtered) < len(pois):
            slog.checkpoint(
                stage="filter", category=category,
                count_raw=len(pois), count_kept=len(filtered),
                provider="radius", op="filter_radius",
                meta={"max_distance": max_distance},
            )
        
        result[category] = filtered
    
    return result


def compute_coverage(
    pois_by_category: Dict[str, List["POI"]],
    radius_by_category: Dict[str, int],
    default_radius: int = 500
) -> Dict[str, int]:
    """
    Oblicza coverage per kategoria z uwzględnieniem promieni.
    
    Args:
        pois_by_category: Słownik kategorii → lista POI
        radius_by_category: Słownik kategorii → max promień
        default_radius: Domyślny promień
        
    Returns:
        Słownik kategorii → liczba POI w promieniu
    """
    filtered = filter_by_radius(pois_by_category, radius_by_category, default_radius)
    return {cat: len(pois) for cat, pois in filtered.items()}

