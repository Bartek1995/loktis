"""
Analizator POI i scoring okolicy.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

from .overpass_client import POI


@dataclass
class NeighborhoodScore:
    """Wynik analizy okolicy."""
    total_score: float  # 0-100
    category_scores: Dict[str, float] = field(default_factory=dict)
    quiet_score: Optional[float] = None
    summary: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'total_score': round(self.total_score, 1),
            'category_scores': {k: round(v, 1) for k, v in self.category_scores.items()},
            'quiet_score': round(self.quiet_score, 1) if self.quiet_score is not None else None,
            'summary': self.summary,
            'details': self.details,
        }


class POIAnalyzer:
    """
    Analizuje POI i generuje scoring okolicy.
    Używa prostej heurystyki wagowej.
    """
    
    # Wagi kategorii (suma = 100)
    CATEGORY_WEIGHTS = {
        'shops': 20,
        'transport': 25,
        'education': 10,
        'health': 15,
        'leisure': 10,
        'food': 10,
        'finance': 10,
    }
    
    # Oczekiwana liczba POI dla 100% score w kategorii
    EXPECTED_COUNTS = {
        'shops': 5,
        'transport': 3,
        'education': 2,
        'health': 3,
        'leisure': 2,
        'food': 5,
        'finance': 2,
    }
    
    # Progi odległości (bliżej = lepiej)
    DISTANCE_THRESHOLDS = {
        'excellent': 200,   # < 200m
        'good': 350,        # < 350m
        'ok': 500,          # < 500m
    }
    
    def analyze(self, pois_by_category: Dict[str, List[POI]]) -> NeighborhoodScore:
        """
        Analizuje POI i zwraca scoring.
        
        Args:
            pois_by_category: Słownik {kategoria: [lista POI]}
        
        Returns:
            NeighborhoodScore z wynikiem
        """
        category_scores = {}
        details = {}
        
        for category, weight in self.CATEGORY_WEIGHTS.items():
            pois = pois_by_category.get(category, [])
            score, cat_details = self._score_category(category, pois)
            category_scores[category] = score
            details[category] = cat_details
        
        # Oblicz łączny score (ważona średnia)
        total_score = sum(
            category_scores.get(cat, 0) * weight / 100
            for cat, weight in self.CATEGORY_WEIGHTS.items()
        )
        
        # Oblicz Quiet Score
        quiet_score = self._calculate_quiet_score(pois_by_category)
        
        # Generuj podsumowanie
        summary = self._generate_summary(total_score, category_scores, pois_by_category)
        
        return NeighborhoodScore(
            total_score=total_score,
            category_scores=category_scores,
            quiet_score=quiet_score,
            summary=summary,
            details=details,
        )

    def _calculate_quiet_score(self, pois_by_category: Dict[str, List[POI]]) -> float:
        """Oblicza indeks spokoju (0-100)."""
        score = 60.0 # Baza: umiarkowanie spokojnie

        # Plusy: Parki i zieleń (blisko)
        leisure = pois_by_category.get('leisure', [])
        parks = [p for p in leisure if 'park' in p.subcategory or 'park' in p.tags.get('leisure', '')]
        if any(p.distance_m and p.distance_m <= 400 for p in parks):
            score += 20
        
        # Minusy: Transport (hałas uliczny)
        transport = pois_by_category.get('transport', [])
        # Przystanki bardzo blisko (< 100m) generują duży hałas/ruch
        near_transport = [p for p in transport if p.distance_m and p.distance_m <= 100]
        score -= min(30, len(near_transport) * 10)

        # Minusy: Gastronomia (hałas wieczorny)
        food = pois_by_category.get('food', [])
        near_food = [p for p in food if p.distance_m and p.distance_m <= 50]
        score -= min(20, len(near_food) * 10)
        
        # Minusy: Duże sklepy/markety (ruch samochodowy/ludzi)
        shops = pois_by_category.get('shops', [])
        malls = [p for p in shops if p.subcategory in ['mall', 'supermarket']]
        if any(p.distance_m and p.distance_m <= 150 for p in malls):
            score -= 15

        # Szkoły (hałas w ciągu dnia)
        education = pois_by_category.get('education', [])
        schools = [p for p in education if p.subcategory in ['school', 'kindergarten']]
        if any(p.distance_m and p.distance_m <= 100 for p in schools):
            score -= 10

        return max(0.0, min(100.0, score))
    
    def _score_category(
        self,
        category: str,
        pois: List[POI]
    ) -> tuple[float, dict]:
        """Oblicza score dla kategorii (0-100)."""
        
        expected = self.EXPECTED_COUNTS.get(category, 3)
        
        if not pois:
            return 0.0, {
                'count': 0,
                'nearest_m': None,
                'names': [],
                'rating': 'brak'
            }
        
        # Score za ilość (max 60%)
        count = len(pois)
        count_score = min(60, (count / expected) * 60)
        
        # Score za bliskość (max 40%)
        nearest = min(p.distance_m or 500 for p in pois)
        if nearest <= self.DISTANCE_THRESHOLDS['excellent']:
            distance_score = 40
            rating = 'doskonale'
        elif nearest <= self.DISTANCE_THRESHOLDS['good']:
            distance_score = 30
            rating = 'dobrze'
        elif nearest <= self.DISTANCE_THRESHOLDS['ok']:
            distance_score = 20
            rating = 'ok'
        else:
            distance_score = 10
            rating = 'daleko'
        
        total = count_score + distance_score
        
        # Top 5 najbliższych nazw
        names = [p.name for p in pois[:5] if p.name != 'Bez nazwy']
        
        return total, {
            'count': count,
            'nearest_m': round(nearest),
            'names': names,
            'rating': rating,
        }
    
    def _generate_summary(
        self,
        total_score: float,
        category_scores: Dict[str, float],
        pois_by_category: Dict[str, List[POI]]
    ) -> str:
        """Generuje tekstowe podsumowanie."""
        
        if total_score >= 80:
            intro = "Bardzo dobra lokalizacja!"
        elif total_score >= 60:
            intro = "Dobra lokalizacja."
        elif total_score >= 40:
            intro = "Przeciętna lokalizacja."
        else:
            intro = "Słaba lokalizacja pod względem infrastruktury."
        
        # Znajdź mocne strony
        strong = [cat for cat, score in category_scores.items() if score >= 70]
        weak = [cat for cat, score in category_scores.items() if score <= 30]
        
        parts = [intro]
        
        category_names = {
            'shops': 'sklepy',
            'transport': 'transport publiczny',
            'education': 'edukacja',
            'health': 'służba zdrowia',
            'leisure': 'rekreacja',
            'food': 'gastronomia',
            'finance': 'banki',
        }
        
        if strong:
            strong_names = [category_names.get(c, c) for c in strong[:3]]
            parts.append(f"Mocne strony: {', '.join(strong_names)}.")
        
        if weak:
            weak_names = [category_names.get(c, c) for c in weak[:3]]
            parts.append(f"Do poprawy: {', '.join(weak_names)}.")
        
        return ' '.join(parts)
    
    def get_statistics(self, pois_by_category: Dict[str, List[POI]]) -> Dict[str, Any]:
        """Zwraca statystyki POI do wyświetlenia."""
        stats = {}
        
        category_names = {
            'shops': 'Sklepy',
            'transport': 'Transport publiczny',
            'education': 'Edukacja',
            'health': 'Zdrowie',
            'leisure': 'Rekreacja',
            'food': 'Gastronomia',
            'finance': 'Finanse',
        }
        
        for category, pois in pois_by_category.items():
            if not pois:
                continue
            
            stats[category] = {
                'name': category_names.get(category, category),
                'count': len(pois),
                'nearest': min(p.distance_m or 500 for p in pois),
                'items': [
                    {
                        'name': p.name,
                        'distance_m': round(p.distance_m or 0),
                        'subcategory': p.subcategory,
                    }
                    for p in pois[:10]  # Max 10 per category
                ]
            }
        
        return stats
