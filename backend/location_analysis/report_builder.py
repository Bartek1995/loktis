"""
Builder raportów z analizy lokalizacji.
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from decimal import Decimal

from .providers.base import ListingData as PropertyData  # Aliased for semantic clarity
from .geo.poi_analyzer import NeighborhoodScore


@dataclass
class AnalysisReport:
    """Pełny raport z analizy."""
    
    # Status
    success: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # TL;DR removed - now handled by AI insights and not displayed in frontend
    
    # Dane nieruchomości (opcjonalne, podane przez użytkownika)
    property_data: Dict[str, Any] = field(default_factory=dict)
    property_completeness: Dict[str, bool] = field(default_factory=dict)
    
    # Okolica
    has_location: bool = False
    neighborhood_score: Optional[float] = None
    quiet_score: Optional[float] = None
    neighborhood_summary: str = ""
    neighborhood_details: Dict[str, Any] = field(default_factory=dict)
    poi_stats: Dict[str, Any] = field(default_factory=dict)
    map_markers: List[Dict[str, Any]] = field(default_factory=list)
    air_quality: Optional[Dict[str, Any]] = None
    
    # Checklista
    checklist: List[str] = field(default_factory=list)
    
    # Ograniczenia
    limitations: List[str] = field(default_factory=list)
    
    # Parametry generowania raportu (profil, promienie, etc.)
    generation_params: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'errors': self.errors,
            'warnings': self.warnings,
            'tldr': {'pros': [], 'cons': []},  # Legacy - kept for API compatibility
            'property': self.property_data,
            'property_completeness': self.property_completeness,
            # Legacy alias for backwards compatibility
            'listing': self.property_data,
            'neighborhood': {
                'has_location': self.has_location,
                'score': self.neighborhood_score,
                'quiet_score': self.quiet_score,
                'summary': self.neighborhood_summary,
                'details': self.neighborhood_details,
                'poi_stats': self.poi_stats,
                'markers': self.map_markers,
                'air_quality': self.air_quality,
            },
            'checklist': self.checklist,
            'limitations': self.limitations,
            'generation_params': self.generation_params,
        }


class ReportBuilder:
    """Buduje raport z analizy lokalizacji."""
    
    # Price comparisons removed - no verifiable benchmark data available
    
    # Standardowe pytania do checklisty
    BASE_CHECKLIST = [
        "Jaki jest dokładny adres nieruchomości?",
        "Czy cena jest do negocjacji?",
        "Jaki jest powód sprzedaży?",
        "Jak długo nieruchomość jest na rynku?",
        "Czy są jakieś ukryte wady lub planowane remonty w budynku?",
        "Jaka jest wysokość czynszu i co obejmuje?",
        "Jaki jest stan prawny nieruchomości (hipoteka, służebności)?",
        "Kiedy możliwe jest przekazanie kluczy?",
        "Czy w cenie są zawarte miejsca parkingowe/komórka lokatorska?",
        "Jacy są sąsiedzi i jaka jest atmosfera w budynku?",
    ]
    
    def build(
        self,
        property_input: PropertyData,
        neighborhood_score: Optional[NeighborhoodScore] = None,
        poi_stats: Optional[Dict[str, Any]] = None,
        all_pois: Optional[Dict[str, list]] = None,
        air_quality: Optional[Dict[str, Any]] = None,
    ) -> AnalysisReport:
        """
        Buduje pełny raport.
        
        Args:
            property_input: Dane nieruchomości (opcjonalne, od użytkownika)
            neighborhood_score: Wynik analizy okolicy (opcjonalny)
            poi_stats: Statystyki POI (opcjonalny)
            all_pois: Słownik odnalezionych POI
            air_quality: Poziom i dane jakości powietrza
        
        Returns:
            AnalysisReport
        """
        report = AnalysisReport()
        
        # Przekaż błędy z parsowania
        report.errors = property_input.errors.copy()
        
        # Dane nieruchomości + completeness
        source = getattr(property_input, 'source', 'user')
        prop_dict = property_input.to_dict()
        prop_dict['source'] = source
        report.property_data = prop_dict
        
        # Build property_completeness with per-field source
        has_price = property_input.price is not None
        has_area = property_input.area_sqm is not None
        has_ppm = property_input.price_per_sqm is not None
        
        report.property_completeness = {
            'has_any': has_price or has_area,
            'source': source,
            'fields': {
                'price': {'value': property_input.price, 'source': source} if has_price else None,
                'area_sqm': {'value': property_input.area_sqm, 'source': source} if has_area else None,
                'price_per_sqm': {'value': property_input.price_per_sqm, 'source': 'computed'} if has_ppm else None,
                'rooms': {'value': property_input.rooms, 'source': source} if property_input.rooms else None,
                'floor': {'value': property_input.floor, 'source': source} if property_input.floor else None,
            },
            # Legacy flat flags for backwards compatibility
            'has_price': has_price,
            'has_area': has_area,
            'has_price_per_sqm': has_ppm,
            'has_rooms': property_input.rooms is not None,
            'has_floor': bool(property_input.floor),
        }
        
        # Analiza lokalizacji
        if property_input.has_precise_location and property_input.latitude and property_input.longitude:
            report.has_location = True
            
            if neighborhood_score:
                report.neighborhood_score = neighborhood_score.total_score
                report.quiet_score = neighborhood_score.quiet_score
                report.neighborhood_summary = neighborhood_score.summary
                report.neighborhood_details = neighborhood_score.details
            
            if poi_stats:
                report.poi_stats = poi_stats
            
            if all_pois:
                report.map_markers = self._generate_markers(all_pois)
            
            if air_quality:
                report.air_quality = air_quality
        else:
            report.has_location = False
            report.limitations.append(
                "Brak dokładnej lokalizacji - analiza okolicy jest ograniczona."
            )
        
        
        # Dodaj ostrzeżenia (tylko gdy source != 'user' - dane z providera)
        report.warnings = self._generate_warnings(property_input)
        
        # Dodaj ograniczenia
        if property_input.errors:
            report.limitations.append(
                "Niektóre dane mogły nie zostać poprawnie pobrane."
            )
        
        return report
    
    
    def _generate_warnings(self, property_input: PropertyData) -> List[str]:
        """Generuje ostrzeżenia - tylko dla danych z providerów, nie user input."""
        warnings = []
        
        # If user-provided data, don't generate "missing" warnings
        source = getattr(property_input, 'source', 'user')
        if source == 'user' or source == 'none':
            return warnings
        
        # Only generate warnings for provider-sourced data
        if not property_input.price:
            warnings.append("Nie udało się pobrać ceny z ogłoszenia.")
        
        if not property_input.area_sqm:
            warnings.append("Brak informacji o metrażu.")
        
        if not property_input.description:
            warnings.append("Brak opisu - może to być niekompletne ogłoszenie.")
        
        if property_input.description and len(property_input.description) < 100:
            warnings.append("Bardzo krótki opis ogłoszenia.")
        
        return warnings
    
    def _generate_markers(self, pois_by_category: Dict[str, list]) -> List[Dict[str, Any]]:
        """Generuje markery POI dla mapy."""
        markers = []
        
        # Kolory zgodne z frontendem (Tailwind colors)
        category_colors = {
            'shops': '#F59E0B',          # amber-500
            'transport': '#3B82F6',      # blue-500
            'education': '#8B5CF6',      # violet-500
            'health': '#EF4444',         # red-500
            'nature_place': '#10B981',   # emerald-500 (Parki, ogrody)
            'nature_background': '#06B6D4',  # cyan-500 (Woda, lasy, łąki)
            'nature': '#10B981',         # legacy (Zieleń)
            'leisure': '#F97316',        # orange-500 (Sport)
            'food': '#EC4899',           # pink-500p
            'finance': '#64748B',        # slate-500
        }

        water_subcategories = {
            'water', 'beach', 'river', 'stream', 'canal', 'lake', 'pond', 'reservoir'
        }
        
        seen_keys = set()
        for category, pois in pois_by_category.items():
            for poi in pois:
                place_id = getattr(poi, 'place_id', None)
                osm_uid = getattr(poi, 'osm_uid', None)
                key = None
                if place_id:
                    key = f"place:{place_id}"
                elif osm_uid:
                    key = f"osm:{osm_uid}"
                else:
                    key = f"grid:{round(poi.lat,4)}:{round(poi.lon,4)}:{(poi.name or '').lower()}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                marker_category = getattr(poi, 'primary_category', None) or category
                color = category_colors.get(marker_category, '#6B7280')
                if marker_category == 'nature_background' and (poi.subcategory or '').lower() in water_subcategories:
                    # Wyróżnij wodę innym kolorem na mapie
                    color = '#F97316'  # orange-500

                markers.append({
                    'lat': poi.lat,
                    'lon': poi.lon,
                    'name': poi.name,
                    'category': marker_category,
                    'subcategory': poi.subcategory,
                    'color': color,
                    'distance': round(poi.distance_m) if poi.distance_m else None
                })
        
        return markers
