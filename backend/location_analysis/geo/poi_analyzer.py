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
    
    # Wagi kategorii (suma = 100) - używane do podstawowego scoringu
    # Nowe kategorie: nature_place (parki) i nature_background (zieleń/woda)
    CATEGORY_WEIGHTS = {
        'shops': 18,
        'transport': 22,
        'education': 10,
        'health': 14,
        'nature_place': 10,      # Parki, ogrody, rezerwaty
        'nature_background': 6,  # Las, łąka, woda (tło)
        'leisure': 8,
        'food': 7,
        'finance': 5,
    }
    
    # Oczekiwana liczba POI dla 100% score w kategorii
    EXPECTED_COUNTS = {
        'shops': 5,
        'transport': 3,
        'education': 2,
        'health': 3,
        'nature_place': 2,      # Wystarczą 2 parki blisko
        'nature_background': 3,  # Elementy zieleni w tle
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
    
    def analyze(
        self,
        pois_by_category: Dict[str, List[POI]],
        metrics: Optional[Dict[str, Any]] = None
    ) -> NeighborhoodScore:
        """
        Analizuje POI i metryki, zwraca scoring.
        
        Args:
            pois_by_category: Słownik {kategoria: [lista POI]}
            metrics: Słownik metryk (np. {'nature': {...}})
        
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
        
        # Oblicz Quiet Score (z metrykami jeśli dostępne)
        quiet_score = self._calculate_quiet_score(pois_by_category, metrics)
        
        # Generuj podsumowanie
        summary = self._generate_summary(total_score, category_scores, pois_by_category)
        
        return NeighborhoodScore(
            total_score=total_score,
            category_scores=category_scores,
            quiet_score=quiet_score,
            summary=summary,
            details={
                **details,
                'traffic': self._analyze_traffic(pois_by_category),
                'nature_metrics': metrics.get('nature', {}) if metrics else {},
            },
        )

    def _calculate_quiet_score(
        self,
        pois_by_category: Dict[str, List[POI]],
        metrics: Optional[Dict[str, Any]] = None
    ) -> float:
        """Oblicza indeks spokoju (0-100)."""
        score = 60.0 # Baza: umiarkowanie spokojnie

        # Plusy: Zieleń - teraz z metryk zamiast listy POI
        nature_metrics = metrics.get('nature', {}) if metrics else {}
        green_density = nature_metrics.get('green_density_proxy', 0)
        
        # Bonus za gęstość zieleni (zastępuje stary bonus za nature POI)
        if green_density >= 15:
            score += 25  # Wysoka zieleń
        elif green_density >= 5:
            score += 15  # Średnia zieleń
        elif green_density >= 1:
            score += 5   # Niska zieleń
        
        # Bonus za bliskość parku (z metryk)
        nearest_park = nature_metrics.get('nearest_distances', {}).get('park')
        if nearest_park and nearest_park <= 300:
            score += 10
        elif nearest_park and nearest_park <= 500:
            score += 5
        
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

        # Minusy: Ruch drogowy (autostrady, główne drogi, tory)
        roads = pois_by_category.get('roads', [])
        
        # Ciężki ruch (Autostrady, Ekspresówki) - bardzo głośno i daleko niesie
        heavy_traffic = [p for p in roads if p.subcategory in ['motorway', 'trunk']]
        if any(p.distance_m and p.distance_m <= 300 for p in heavy_traffic):
            score -= 40
        elif any(p.distance_m and p.distance_m <= 600 for p in heavy_traffic):
            score -= 20
            
        # Średni/Duży ruch (Główne drogi miejskie)
        primary = [p for p in roads if p.subcategory == 'primary']
        if any(p.distance_m and p.distance_m <= 100 for p in primary):
            score -= 30
        elif any(p.distance_m and p.distance_m <= 250 for p in primary):
            score -= 15
            
        # Minusy: Tory (Tramwaj, Kolej)
        rails = [p for p in roads if p.subcategory in ['tram', 'rail']]
        if any(p.distance_m and p.distance_m <= 80 for p in rails):
            score -= 15

        return max(0.0, min(100.0, score))

    def _analyze_traffic(self, pois_by_category: Dict[str, List[POI]]) -> Dict[str, Any]:
        """Analizuje poziom ruchu ulicznego."""
        roads = pois_by_category.get('roads', [])
        if not roads:
            return {'level': 'Low', 'label': 'Niski', 'description': 'Brak głównych dróg w bezpośrednim sąsiedztwie.'}
            
        # Priorytety
        heavy = [p for p in roads if p.subcategory in ['motorway', 'trunk']]
        primary = [p for p in roads if p.subcategory == 'primary']
        rails = [p for p in roads if p.subcategory in ['tram', 'rail']]
        secondary = [p for p in roads if p.subcategory == 'secondary']
        
        nearest_heavy = min((p.distance_m or 9999 for p in heavy), default=9999)
        nearest_primary = min((p.distance_m or 9999 for p in primary), default=9999)
        nearest_rails = min((p.distance_m or 9999 for p in rails), default=9999)
        
        if nearest_heavy < 300:
            return {'level': 'Extreme', 'label': 'Bardzo Wysoki', 'description': 'Bezpośrednie sąsiedztwo autostrady lub drogi ekspresowej.'}
        if nearest_primary < 100 or nearest_heavy < 800:
            return {'level': 'High', 'label': 'Wysoki', 'description': 'Bliskość głównej arterii komunikacyjnej.'}
        if nearest_rails < 80 or nearest_primary < 300:
             return {'level': 'Moderate', 'label': 'Umiarkowany', 'description': 'Słyszalny ruch miejski lub komunikacja szynowa.'}
             
        return {'level': 'Low', 'label': 'Niski', 'description': 'Okolica oddalona od głównych źródeł hałasu drogowego.'}
    
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
            'nature_place': 'parki i ogrody',
            'nature_background': 'zieleń w otoczeniu',
            'leisure': 'sport i rekreacja',
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
            'nature_place': 'Parki i ogrody',
            'nature_background': 'Zieleń w otoczeniu',
            'leisure': 'Sport i Rekreacja',
            'food': 'Gastronomia',
            'finance': 'Finanse',
        }
        
        for category, pois in pois_by_category.items():
            if not pois:
                continue

            primary_items = []
            secondary_count = 0
            for p in pois:
                primary = getattr(p, 'primary_category', None)
                if primary and primary != category:
                    secondary_count += 1
                    continue
                primary_items.append(p)

            nearest_all = min(p.distance_m or 500 for p in pois)
            nearest_primary = min((p.distance_m or 500 for p in primary_items), default=nearest_all)

            stats[category] = {
                'name': category_names.get(category, category),
                'count': len(primary_items),
                'count_secondary': secondary_count,
                'count_total': len(pois),
                'nearest': nearest_primary,
                'items': [
                    {
                        'name': p.name,
                        'distance_m': round(p.distance_m or 0),
                        'subcategory': p.subcategory,
                        'badges': list(getattr(p, 'badges', []) or []),
                        'secondary_categories': list(getattr(p, 'secondary_categories', []) or []),
                        'source': getattr(p, 'source', None),
                        'rating': p.tags.get('rating'),
                        'reviews': p.tags.get('user_ratings_total') or p.tags.get('reviews_count'),
                    }
                    for p in primary_items[:10]  # Max 10 per category
                ]
            }
        
        
        # Filtruj 'roads' ze statystyk (nie chcemy ich na liście kafelków jako POI)
        if 'roads' in stats:
            del stats['roads']
            
        return stats
