"""
Nowy silnik scoringu z profilami konfiguracyjnymi.

Oblicza CategoryUtilityScore na podstawie:
- odległości (z krzywymi spadku)
- jakości (rating/reviews z Google)
- critical caps

Ten moduł zastępuje stary ScoringEngine.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import math
import logging

from .profiles import (
    ProfileConfig, 
    get_profile, 
    distance_score, 
    Category,
    DecayMode,
)

logger = logging.getLogger(__name__)


@dataclass
class POIContribution:
    """Wkład pojedynczego POI do score'u kategorii."""
    name: str
    distance_m: float
    distance_score: float      # Score z krzywej spadku (0-100)
    quality_multiplier: float  # Mnożnik jakości (0.85-1.15)
    final_contribution: float  # distance_score * quality_multiplier * weight_factor
    subcategory: str = ""      # e.g. bus_stop, platform, pharmacy
    rating: Optional[float] = None
    reviews: Optional[int] = None


@dataclass
class CategoryScoreResult:
    """Wynik scoringu dla pojedynczej kategorii."""
    category: str
    score: float               # Końcowy score kategorii (0-100)
    utility_score: float       # Score użyteczności (suma wkładów)
    utility_sum: float         # Surowa suma wkładów (przed saturacją)
    coverage_bonus: float      # Bonus za pokrycie (jeśli applicable)
    nearest_distance_m: Optional[float] = None
    poi_count: int = 0
    radius_used: int = 0
    contributions: List[POIContribution] = field(default_factory=list)
    is_critical: bool = False
    critical_threshold: Optional[float] = None
    critical_cap: Optional[float] = None
    critical_reason: str = ""
    
    def to_dict(self) -> dict:
        return {
            'category': self.category,
            'score': round(self.score, 1),
            'utility_score': round(self.utility_score, 1),
            'utility_sum': round(self.utility_sum, 2),
            'coverage_bonus': round(self.coverage_bonus, 1),
            'nearest_distance_m': self.nearest_distance_m,
            'poi_count': self.poi_count,
            'radius_used': self.radius_used,
            'is_critical': self.is_critical,
            'critical_threshold': self.critical_threshold,
            'critical_cap': self.critical_cap,
            'critical_reason': self.critical_reason,
            'top_pois': [
                {
                    'name': c.name,
                    'subcategory': c.subcategory,
                    'distance_m': c.distance_m,
                    'score': round(c.final_contribution, 1),
                    'rating': c.rating,
                }
                for c in self.contributions[:3]  # Top 3
            ],
        }


@dataclass
class ScoringResult:
    """Pełny wynik scoringu z breakdownem."""
    total_score: float
    base_score: float          # Score przed critical caps
    noise_penalty: float       # Kara za hałas
    roads_penalty: float       # Kara za infrastrukturę drogową
    quiet_score: float         # Quiet score (0-100)
    
    category_results: Dict[str, CategoryScoreResult] = field(default_factory=dict)
    profile_key: str = ""
    profile_config_version: int = 1
    
    verdict: str = ""          # recommended/conditional/not_recommended
    critical_caps_applied: List[str] = field(default_factory=list)
    
    warnings: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    debug: Dict[str, Any] = field(default_factory=dict)
    
    # Roads infrastructure debug info (proper field, not extracted from debug)
    # Used for deterministic gating of "Spokojna okolica" and primary_blocker selection
    roads_debug: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'total_score': round(self.total_score, 1),
            'base_score': round(self.base_score, 1),
            'noise_penalty': round(self.noise_penalty, 3),
            'roads_penalty': round(self.roads_penalty, 3),
            'quiet_score': round(self.quiet_score, 1),
            'profile_key': self.profile_key,
            'profile_config_version': self.profile_config_version,
            'verdict': self.verdict,
            'critical_caps_applied': self.critical_caps_applied,
            'category_scores': {
                cat: result.to_dict()
                for cat, result in self.category_results.items()
            },
            'warnings': self.warnings,
            'strengths': self.strengths,
            'weaknesses': self.weaknesses,
            'roads_debug': self.roads_debug,
            'debug': self.debug,
        }


# Nazwy kategorii po polsku
CATEGORY_NAMES_PL = {
    'shops': 'Sklepy',
    'transport': 'Transport publiczny',
    'education': 'Edukacja',
    'health': 'Zdrowie',
    'nature_place': 'Parki i ogrody',
    'nature_background': 'Zieleń w otoczeniu',
    'leisure': 'Sport i rekreacja',
    'food': 'Gastronomia',
    'finance': 'Banki i finanse',
    'noise': 'Poziom hałasu',
    'car_access': 'Dostęp samochodem',
}


class ProfileScoringEngine:
    """
    Silnik scoringu oparty na profilach konfiguracyjnych.
    
    Proces:
    1. Dla każdej kategorii: oblicz CategoryUtilityScore
    2. Oblicz noise score (Quiet Score) i przekształć na penalty
    3. Oblicz TotalScore = sum(weight * category_score) + noise_penalty
    4. Aplikuj critical_caps
    5. Zwróć wynik z pełnym breakdown
    """
    
    # Progi oceny
    RATING_THRESHOLDS = {
        'excellent': 75,
        'good': 50,
        'poor': 25,
    }
    
    # Parametry normalizacji utility score
    MAX_POIS_FOR_SCORE = 10  # Bierzemy max N najbliższych POI
    UTILITY_NORMALIZATION = 300  # Suma wkładów dzielona przez to = score (capped to 100)
    
    # Coverage bonus (tylko dla daily categories)
    COVERAGE_BONUS_3 = 5   # >= 3 sensownych POI
    COVERAGE_BONUS_6 = 10  # >= 6 sensownych POI
    DAILY_CATEGORIES = {'shops', 'transport', 'finance'}
    
    # Nameless POI weight reduction
    NAMELESS_WEIGHT = 0.6
    
    # Base neighborhood adjustment (profil koryguje bazę, nie buduje nowej skali)
    MAX_BASE_ADJUSTMENT = 20.0
    MIN_DISTANCE_FACTOR = 0.4

    # Diminishing returns (saturation) per category
    DEFAULT_SATURATION_K = 0.005
    SATURATION_K = {
        'shops': 0.006,
        'transport': 0.0065,
        'education': 0.0045,
        'health': 0.0045,
        'nature_place': 0.004,
        'nature_background': 0.0035,
        'leisure': 0.0045,
        'food': 0.0035,
        'finance': 0.006,
    }
    
    def __init__(self, profile: ProfileConfig):
        """
        Inicjalizuje silnik dla danego profilu.
        
        Args:
            profile: Konfiguracja profilu
        """
        self.profile = profile
        logger.debug(f"ProfileScoringEngine initialized for profile: {profile.key}")
    
    def calculate(
        self,
        pois_by_category: Dict[str, List[Any]],
        quiet_score: float,
        nature_metrics: Optional[Dict] = None,
        base_neighborhood_score: Optional[float] = None,
    ) -> ScoringResult:
        """
        Oblicza pełny scoring na podstawie POI i profilu.
        
        Args:
            pois_by_category: Słownik {kategoria: [lista POI]}
            quiet_score: Quiet Score (0-100)
            nature_metrics: Metryki natury (opcjonalne)
            base_neighborhood_score: Bazowy score okolicy (0-100) do korekty profilu
        
        Returns:
            ScoringResult z pełnym breakdown
        """
        category_results = {}
        category_scores = {}
        debug_categories: Dict[str, Any] = {}
        
        # 1. Oblicz score dla każdej kategorii (oprócz noise)
        for category in [c.value for c in Category if c != Category.NOISE]:
            weight = self.profile.get_weight(category)
            if weight == 0 and category not in [Category.NATURE_BACKGROUND.value]:
                continue
            
            pois = pois_by_category.get(category, [])
            radius = self.profile.get_radius(category)
            
            # Filtruj POI poza promieniem (twardy cutoff)
            pois_in_radius = [p for p in pois if p.distance_m <= radius]
            
            result = self._calculate_category_score(
                category=category,
                pois=pois_in_radius,
                radius=radius,
                nature_metrics=nature_metrics if category == Category.NATURE_BACKGROUND.value else None,
            )
            
            # Sprawdź czy kategoria jest krytyczna + dodaj reason
            result.is_critical = False
            for cap_cat, cap_config in self.profile.critical_caps:
                if cap_cat == category:
                    result.is_critical = True
                    result.critical_threshold = cap_config.threshold
                    result.critical_cap = cap_config.cap
                    result.critical_reason = (
                        f"weight≥{self.profile.get_weight(category):.0%}, "
                        f"score<{cap_config.threshold}→cap {cap_config.cap}"
                    )
                    break
            
            category_results[category] = result
            category_scores[category] = result.score

            debug_categories[category] = {
                'count_raw': len(pois),
                'count_in_radius': len(pois_in_radius),
                'radius_used_m': radius,
                'utility_sum': round(result.utility_sum, 2),
                'utility_score': round(result.utility_score, 2),
                'coverage_bonus': round(result.coverage_bonus, 2),
                'score_before_distance': round(min(100.0, result.utility_score + result.coverage_bonus), 2),
                'score_final': round(result.score, 2),
                'nearest_distance_m': result.nearest_distance_m,
                'distance_factor': round(
                    self._distance_factor(
                        result.nearest_distance_m,
                        radius,
                        self.profile.get_decay_mode(category),
                    ),
                    3,
                ),
                'weight': round(weight, 4),
                'weighted_subscore': round(weight * result.score, 3),
            }
        
        # 2. Quiet Score → noise score (odwrócony)
        # Wysoki quiet_score = niska kara, niski quiet_score = wysoka kara
        noise_score = quiet_score  # Używamy bezpośrednio jako "score ciszy"
        category_scores[Category.NOISE.value] = noise_score
        
        # 3. Oblicz base score (ważona suma)
        base_score = 0.0
        noise_penalty = 0.0
        
        for category, weight in self.profile.weights.items():
            cat_score = category_scores.get(category, 0)
            
            if category == Category.NOISE.value:
                # Noise ma ujemną wagę - działa jako kara
                # Jeśli quiet_score=100 (cicho) → penalty=0
                # Jeśli quiet_score=0 (głośno) → max penalty
                # penalty = |weight| * (100 - quiet_score)
                noise_penalty = abs(weight) * (100 - quiet_score)
            else:
                base_score += weight * cat_score
        
        # Normalizuj base_score (wagi dodatnie sumują się do ~1.0)
        # ale mamy też noise jako karę
        base_score_raw = base_score
        total_positive_weight = sum(w for w in self.profile.weights.values() if w > 0)
        if total_positive_weight > 0:
            base_score = base_score / total_positive_weight

        # Uzupełnij debug o znormalizowane wkłady
        if total_positive_weight > 0:
            for category, debug_item in debug_categories.items():
                weight = debug_item.get('weight', 0)
                if weight > 0:
                    debug_item['weighted_subscore_normalized'] = round(
                        (weight / total_positive_weight) * debug_item.get('score_final', 0), 3
                    )
        
        # Roads penalty (infrastruktura drogowa jako minus)
        roads_penalty, roads_debug = self._calculate_roads_penalty(pois_by_category.get('roads', []))

        # Aplikuj kary
        total_score = base_score - noise_penalty - roads_penalty
        
        # 4. Aplikuj critical caps
        critical_caps_applied: List[str] = []
        total_score, critical_caps_applied = self._apply_critical_caps(
            total_score, category_scores, critical_caps_applied
        )
        
        # 5. Clamp do 0-100
        total_score = max(0, min(100, total_score))
        total_score_pre_adjust = total_score
        
        # 6. Profil koryguje bazową ocenę okolicy (jeśli dostępna)
        base_adjustment = None
        if base_neighborhood_score is not None:
            delta = total_score - base_neighborhood_score
            delta = max(-self.MAX_BASE_ADJUSTMENT, min(self.MAX_BASE_ADJUSTMENT, delta))
            base_adjustment = delta
            total_score = base_neighborhood_score + delta
            total_score = max(0, min(100, total_score))
            total_score, critical_caps_applied = self._apply_critical_caps(
                total_score, category_scores, critical_caps_applied
            )
        total_score_post_adjust = total_score
        
        # 7. Verdict
        verdict = self.profile.thresholds.get_verdict(total_score)
        
        # 8. Strengths & Weaknesses (with roads_debug gating)
        strengths, weaknesses = self._extract_highlights(category_results, quiet_score, roads_debug)
        
        # 9. Warnings
        warnings = self._generate_warnings(category_results, quiet_score, critical_caps_applied)
        
        debug_payload = {
            'categories': debug_categories,
            'penalties': {
                'noise_penalty': round(noise_penalty, 3),
                'roads_penalty': round(roads_penalty, 3),
            },
            'roads': roads_debug,
            'total_positive_weight': round(total_positive_weight, 4),
            'base_score_raw': round(base_score_raw, 3),
            'base_score_normalized': round(base_score, 3),
            'base_neighborhood_score': round(base_neighborhood_score, 3) if base_neighborhood_score is not None else None,
            'base_adjustment': round(base_adjustment, 3) if base_adjustment is not None else None,
            'total_score_pre_adjust': round(total_score_pre_adjust, 3),
            'total_score_post_adjust': round(total_score_post_adjust, 3),
        }

        logger.debug(
            f"Profile scoring breakdown ({self.profile.key}): "
            f"base={base_score:.1f} noise_penalty={noise_penalty:.1f} roads_penalty={roads_penalty:.1f}"
        )
        log_suffix = ""
        if base_neighborhood_score is not None:
            adj = base_adjustment if base_adjustment is not None else 0.0
            log_suffix = f" base_neighborhood={base_neighborhood_score:.1f} adj={adj:.1f}"

        logger.info(
            f"Profile scoring summary ({self.profile.key}): "
            f"total={total_score:.1f} base={base_score:.1f} "
            f"noise_penalty={noise_penalty:.1f} roads_penalty={roads_penalty:.1f}"
            f"{log_suffix}"
        )

        return ScoringResult(
            total_score=total_score,
            base_score=base_score,
            noise_penalty=noise_penalty,
            roads_penalty=roads_penalty,
            quiet_score=quiet_score,
            category_results=category_results,
            profile_key=self.profile.key,
            profile_config_version=self.profile.version,
            verdict=verdict,
            critical_caps_applied=critical_caps_applied,
            warnings=warnings,
            strengths=strengths,
            weaknesses=weaknesses,
            roads_debug=roads_debug,
            debug=debug_payload,
        )

    def _apply_critical_caps(
        self,
        total_score: float,
        category_scores: Dict[str, float],
        applied: List[str],
    ) -> Tuple[float, List[str]]:
        """Aplikuje critical caps do total_score."""
        applied_set = set(applied)
        for category, cap_config in self.profile.critical_caps:
            cat_score = category_scores.get(category, 0)
            if cat_score < cap_config.threshold and total_score > cap_config.cap:
                total_score = cap_config.cap
                msg = (
                    f"{CATEGORY_NAMES_PL.get(category, category)}: "
                    f"{cat_score:.0f} < {cap_config.threshold} → cap {cap_config.cap}"
                )
                if msg not in applied_set:
                    applied.append(msg)
                    applied_set.add(msg)
        return total_score, applied
    
    def _calculate_category_score(
        self,
        category: str,
        pois: List[Any],
        radius: int,
        nature_metrics: Optional[Dict] = None,
    ) -> CategoryScoreResult:
        """Oblicza score dla pojedynczej kategorii."""
        
        if not pois and not nature_metrics:
            return CategoryScoreResult(
                category=category,
                score=0,
                utility_score=0,
                utility_sum=0,
                coverage_bonus=0,
                nearest_distance_m=None,
                poi_count=0,
                radius_used=radius,
            )
        
        decay_mode = self.profile.get_decay_mode(category)
        
        # Dla nature_background możemy też użyć metryk
        if category == Category.NATURE_BACKGROUND.value and nature_metrics:
            return self._calculate_nature_background_score(radius, nature_metrics, pois)
        
        # Sortuj po odległości i weź top N
        sorted_pois = sorted(pois, key=lambda p: p.distance_m)[:self.MAX_POIS_FOR_SCORE]
        
        contributions = []
        utility_sum = 0.0
        
        for poi in sorted_pois:
            # Distance score z krzywej spadku
            dist_score = distance_score(poi.distance_m, radius, decay_mode)
            
            # Quality multiplier (rating/reviews)
            quality_mult = self._calculate_quality_multiplier(poi)
            
            # Nameless penalty
            nameless_mult = self.NAMELESS_WEIGHT if poi.tags.get('_nameless') else 1.0
            
            # Wkład POI
            contribution = dist_score * quality_mult * nameless_mult
            utility_sum += contribution
            
            contributions.append(POIContribution(
                name=poi.name,
                distance_m=poi.distance_m,
                distance_score=dist_score,
                quality_multiplier=quality_mult * nameless_mult,
                final_contribution=contribution,
                subcategory=poi.subcategory or '',
                rating=poi.tags.get('rating'),
                reviews=poi.tags.get('user_ratings_total'),
            ))
        
        # Normalizacja utility do 0-100 (saturacja / diminishing returns)
        saturation_k = self.SATURATION_K.get(category, self.DEFAULT_SATURATION_K)
        utility_score = self._saturating_score(utility_sum, saturation_k)
        
        # Coverage bonus (tylko dla daily categories)
        coverage_bonus = 0.0
        if category in self.DAILY_CATEGORIES:
            sensible_pois = [p for p in sorted_pois if p.distance_m <= radius * 0.8]
            if len(sensible_pois) >= 6:
                coverage_bonus = self.COVERAGE_BONUS_6
            elif len(sensible_pois) >= 3:
                coverage_bonus = self.COVERAGE_BONUS_3
        
        score_before_distance = min(100, utility_score + coverage_bonus)
        nearest_distance = sorted_pois[0].distance_m if sorted_pois else None
        distance_factor = self._distance_factor(nearest_distance, radius, decay_mode)
        final_score = min(100, score_before_distance * distance_factor)
        
        return CategoryScoreResult(
            category=category,
            score=final_score,
            utility_score=utility_score,
            utility_sum=utility_sum,
            coverage_bonus=coverage_bonus,
            nearest_distance_m=nearest_distance,
            poi_count=len(pois),
            radius_used=radius,
            contributions=contributions,
        )
    
    def _calculate_nature_background_score(
        self,
        radius: int,
        nature_metrics: Dict,
        pois: List[Any],
    ) -> CategoryScoreResult:
        """
        Oblicza score dla nature_background na podstawie metryk + POI wody.
        """
        score = 0.0
        
        # 1. Green density score (0-50 punktów)
        green_density = nature_metrics.get('green_density_proxy', 0)
        if green_density >= 15:
            density_score = 50
        elif green_density >= 8:
            density_score = 35
        elif green_density >= 3:
            density_score = 20
        elif green_density >= 1:
            density_score = 10
        else:
            density_score = 0
        
        # 2. Nearest green distance score (0-30 punktów)
        nearest_distances = nature_metrics.get('nearest_distances', {})
        nearest_green = None
        for green_type in ['forest', 'wood', 'meadow', 'grass', 'park']:
            dist = nearest_distances.get(green_type)
            if dist and (nearest_green is None or dist < nearest_green):
                nearest_green = dist
        
        if nearest_green:
            decay_mode = DecayMode.BACKGROUND
            distance_component = distance_score(nearest_green, radius, decay_mode) * 0.3
        else:
            distance_component = 0
        
        # 3. Water bonus (0-20 punktów)
        water_bonus = 0
        nearest_water = nature_metrics.get('nearest_water_m')
        if nearest_water:
            if nearest_water <= 200:
                water_bonus = 20
            elif nearest_water <= 400:
                water_bonus = 15
            elif nearest_water <= 600:
                water_bonus = 10
            elif nearest_water <= 1000:
                water_bonus = 5
        
        score = density_score + distance_component + water_bonus
        score = min(100, score)
        
        return CategoryScoreResult(
            category=Category.NATURE_BACKGROUND.value,
            score=score,
            utility_score=density_score + distance_component,
            utility_sum=density_score + distance_component,
            coverage_bonus=water_bonus,
            nearest_distance_m=nearest_green,
            poi_count=nature_metrics.get('total_green_elements', 0),
            radius_used=radius,
        )
    
    def _calculate_quality_multiplier(self, poi) -> float:
        """
        Oblicza mnożnik jakości na podstawie rating/reviews.
        
        Formula:
        - Base: 1.0
        - Rating contribution: 0.90 + 0.20 * (rating/5.0) → range 0.90-1.10
        - Reviews confidence: clamp(reviews/200, 0, 1)
        - Final: lerp(1.0, rating_mult, reviews_confidence)
        """
        rating = poi.tags.get('rating')
        reviews = (
            poi.tags.get('user_ratings_total')
            or poi.tags.get('reviews_count')
        )
        
        if not rating:
            return 1.0
        
        # Rating component: 0.90 - 1.10 (premia jakość)
        rating_mult = 0.90 + 0.20 * (float(rating) / 5.0)
        
        # Reviews confidence: 0-1
        reviews_confidence = min(1.0, (reviews or 0) / 200) if reviews else 0.3

        # Jeżeli mało opinii, nie przyznawaj bonusu jakości
        if poi.tags.get('low_reviews'):
            rating_mult = min(rating_mult, 1.0)
        
        # Interpolate between 1.0 and rating_mult based on confidence
        final_mult = 1.0 + (rating_mult - 1.0) * reviews_confidence
        
        return final_mult

    def _distance_factor(self, nearest_distance_m: Optional[float], radius: int, decay_mode: DecayMode) -> float:
        """Skaluje score kategorii na podstawie najbliższego POI."""
        if nearest_distance_m is None:
            return 0.0

        nearest_score = distance_score(nearest_distance_m, radius, decay_mode) / 100.0
        # Minimalny udział, żeby nie wyzerować całej kategorii przy dalekich POI
        return self.MIN_DISTANCE_FACTOR + (1.0 - self.MIN_DISTANCE_FACTOR) * nearest_score

    def _saturating_score(self, value: float, k: float) -> float:
        """Saturacja wyniku (diminishing returns)."""
        if value <= 0:
            return 0.0
        return min(100.0, 100 * (1 - math.exp(-k * value)))

    def _calculate_roads_penalty(self, roads: List[Any]) -> Tuple[float, Dict[str, Any]]:
        """Kara za infrastrukturę drogową i szyny."""
        if not roads:
            return 0.0, {'count': 0}

        def nearest(subcats: List[str]) -> Optional[float]:
            dists = [p.distance_m for p in roads if p.subcategory in subcats and p.distance_m is not None]
            return min(dists) if dists else None

        nearest_heavy = nearest(['motorway', 'trunk'])
        nearest_primary = nearest(['primary'])
        nearest_secondary = nearest(['secondary'])
        nearest_rails = nearest(['tram', 'rail'])

        penalty = 0.0
        if nearest_heavy is not None:
            if nearest_heavy <= 300:
                penalty += 20
            elif nearest_heavy <= 600:
                penalty += 12
            elif nearest_heavy <= 1000:
                penalty += 6

        if nearest_primary is not None:
            if nearest_primary <= 100:
                penalty += 12
            elif nearest_primary <= 250:
                penalty += 8
            elif nearest_primary <= 500:
                penalty += 4

        if nearest_secondary is not None:
            if nearest_secondary <= 150:
                penalty += 6
            elif nearest_secondary <= 300:
                penalty += 3

        if nearest_rails is not None:
            if nearest_rails <= 80:
                penalty += 8
            elif nearest_rails <= 150:
                penalty += 4

        # Road density — only count significant (noisy) roads, not tertiary/residential
        SIGNIFICANT_ROAD_TYPES = {'motorway', 'trunk', 'primary', 'secondary', 'tram', 'rail'}
        significant_count = sum(1 for r in roads if r.subcategory in SIGNIFICANT_ROAD_TYPES)
        road_count = len(roads)  # total for debug
        if significant_count >= 10:
            penalty += 5
        elif significant_count >= 5:
            penalty += 3

        # Skalowanie karą ciszy profilu
        noise_weight = abs(self.profile.get_weight(Category.NOISE.value))
        scale = 0.5 + min(1.5, noise_weight / 0.05)
        penalty = min(30.0, penalty * scale)

        debug = {
            'count': road_count,
            'nearest_heavy_m': nearest_heavy,
            'nearest_primary_m': nearest_primary,
            'nearest_secondary_m': nearest_secondary,
            'nearest_rails_m': nearest_rails,
            'scale': round(scale, 2),
        }
        return penalty, debug
    
    def _extract_highlights(
        self,
        category_results: Dict[str, CategoryScoreResult],
        quiet_score: float,
        roads_debug: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[str], List[str]]:
        """Ekstrahuje mocne i słabe strony."""
        strengths = []
        weaknesses = []
        
        for cat, result in category_results.items():
            name = CATEGORY_NAMES_PL.get(cat, cat)
            
            if result.score >= 70:
                if result.nearest_distance_m and result.nearest_distance_m <= 300:
                    strengths.append(f"✅ {name}: doskonały dostęp ({result.nearest_distance_m:.0f}m)")
                else:
                    strengths.append(f"✅ {name}: wysoki wynik ({result.score:.0f})")
            
            elif result.score <= 30 and result.is_critical:
                weaknesses.append(f"⚠️ {name}: słaby wynik ({result.score:.0f})")
        
        # Quiet Score - GATED by roads infrastructure proximity
        # Block "Spokojna okolica" when roads_debug indicates noise risk
        is_quiet_blocked = False
        if roads_debug:
            # Gate based on specific infrastructure distances (more robust than penalty threshold)
            if roads_debug.get('nearest_primary_m') and roads_debug['nearest_primary_m'] <= 250:
                is_quiet_blocked = True
            if roads_debug.get('nearest_rails_m') and roads_debug['nearest_rails_m'] <= 200:
                is_quiet_blocked = True
            if roads_debug.get('nearest_secondary_m') and roads_debug['nearest_secondary_m'] <= 300:
                is_quiet_blocked = True
            if roads_debug.get('nearest_heavy_m') and roads_debug['nearest_heavy_m'] <= 600:
                is_quiet_blocked = True
            if roads_debug.get('count', 0) >= 10:
                is_quiet_blocked = True
        
        if quiet_score >= 70:
            if not is_quiet_blocked:
                strengths.append(f"🔇 Spokojna okolica ({quiet_score:.0f}/100)")
            # else: blocked due to roads infrastructure, don't emit the claim
        elif quiet_score <= 35:
            weaknesses.append(f"🔊 Głośna okolica ({quiet_score:.0f}/100)")
        
        return strengths[:4], weaknesses[:4]
    
    def _generate_warnings(
        self,
        category_results: Dict[str, CategoryScoreResult],
        quiet_score: float,
        critical_caps_applied: List[str],
    ) -> List[str]:
        """Generuje ostrzeżenia."""
        warnings = []
        
        # Critical caps
        for cap_msg in critical_caps_applied:
            warnings.append(f"🚨 LIMIT: {cap_msg}")
        
        # Low quiet score dla profili wymagających ciszy
        noise_weight = abs(self.profile.get_weight(Category.NOISE.value))
        if noise_weight >= 0.08 and quiet_score < 45:
            warnings.append(
                f"⚠️ Okolica jest głośna ({quiet_score:.0f}/100), "
                f"a profil {self.profile.name} wymaga ciszy."
            )
        
        return warnings


def create_scoring_engine(
    profile_key: str,
    radius_overrides: Optional[Dict[str, int]] = None,
) -> ProfileScoringEngine:
    """
    Factory function do tworzenia silnika scoringu.
    
    Args:
        profile_key: Klucz profilu (urban, family, etc.)
        radius_overrides: Opcjonalne nadpisanie promieni per kategoria
    """
    from dataclasses import replace
    
    profile = get_profile(profile_key)
    
    # Apply radius overrides if provided
    if radius_overrides:
        effective_radius_m = dict(profile.radius_m)
        for category, override_radius in radius_overrides.items():
            if category in effective_radius_m:
                effective_radius_m[category] = override_radius
                logger.info(f"ScoringEngine radius override: {category} = {override_radius}m")
        
        # Create a modified profile with the new radii
        profile = replace(profile, radius_m=effective_radius_m)
    
    return ProfileScoringEngine(profile)
