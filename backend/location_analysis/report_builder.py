"""
Builder raportów z analizy ogłoszeń.
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from decimal import Decimal

from .providers.base import ListingData
from .geo.poi_analyzer import NeighborhoodScore


@dataclass
class AnalysisReport:
    """Pełny raport z analizy."""
    
    # Status
    success: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # TL;DR
    pros: List[str] = field(default_factory=list)
    cons: List[str] = field(default_factory=list)
    
    # Dane z ogłoszenia
    listing_data: Dict[str, Any] = field(default_factory=dict)
    
    # Okolica
    has_location: bool = False
    neighborhood_score: Optional[float] = None
    quiet_score: Optional[float] = None
    neighborhood_summary: str = ""
    neighborhood_details: Dict[str, Any] = field(default_factory=dict)
    poi_stats: Dict[str, Any] = field(default_factory=dict)
    map_markers: List[Dict[str, Any]] = field(default_factory=list)
    
    # Checklista
    checklist: List[str] = field(default_factory=list)
    
    # Ograniczenia
    limitations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'errors': self.errors,
            'warnings': self.warnings,
            'tldr': {
                'pros': self.pros,
                'cons': self.cons,
            },
            'listing': self.listing_data,
            'neighborhood': {
                'has_location': self.has_location,
                'score': self.neighborhood_score,
                'quiet_score': self.quiet_score,
                'summary': self.neighborhood_summary,
                'details': self.neighborhood_details,
                'poi_stats': self.poi_stats,
                'markers': self.map_markers,
            },
            'checklist': self.checklist,
            'limitations': self.limitations,
        }


class ReportBuilder:
    """Buduje raport z analizy ogłoszenia."""
    
    # Średnie ceny za m² w Polsce (uproszczone, 2025)
    AVG_PRICE_PER_SQM = {
        'warszawa': 15000,
        'kraków': 12000,
        'wrocław': 11000,
        'poznań': 10500,
        'gdańsk': 11000,
        'łódź': 7500,
        'katowice': 7000,
        'default': 8000,
    }
    
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
        listing: ListingData,
        neighborhood_score: Optional[NeighborhoodScore] = None,
        poi_stats: Optional[Dict[str, Any]] = None,
        all_pois: Optional[Dict[str, list]] = None,
    ) -> AnalysisReport:
        """
        Buduje pełny raport.
        
        Args:
            listing: Dane z ogłoszenia
            neighborhood_score: Wynik analizy okolicy (opcjonalny)
            poi_stats: Statystyki POI (opcjonalny)
        
        Returns:
            AnalysisReport
        """
        report = AnalysisReport()
        
        # Przekaż błędy z parsowania
        report.errors = listing.errors.copy()
        
        # Dane z ogłoszenia
        report.listing_data = listing.to_dict()
        
        # Analiza lokalizacji
        if listing.has_precise_location and listing.latitude and listing.longitude:
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
        else:
            report.has_location = False
            report.limitations.append(
                "Brak dokładnej lokalizacji - analiza okolicy jest ograniczona."
            )
        
        # Generuj TL;DR
        pros, cons = self._generate_tldr(listing, neighborhood_score)
        report.pros = pros
        report.cons = cons
        
        # Dodaj ostrzeżenia
        report.warnings = self._generate_warnings(listing)
        
        # Dodaj ograniczenia
        if listing.errors:
            report.limitations.append(
                "Niektóre dane mogły nie zostać poprawnie pobrane."
            )
        
        return report
    
    def _generate_tldr(
        self,
        listing: ListingData,
        neighborhood_score: Optional[NeighborhoodScore]
    ) -> tuple[List[str], List[str]]:
        """Generuje 3 plusy i 3 potencjalne ryzyka."""
        pros = []
        cons = []
        
        # === PLUSY ===
        
        # Cena za m²
        if listing.price_per_sqm and listing.location:
            city = self._detect_city(listing.location)
            avg = self.AVG_PRICE_PER_SQM.get(city, self.AVG_PRICE_PER_SQM['default'])
            
            if float(listing.price_per_sqm) < avg * 0.85:
                pros.append(f"Cena za m² poniżej średniej dla {city.title() if city != 'default' else 'regionu'}")
            elif float(listing.price_per_sqm) > avg * 1.2:
                cons.append(f"Cena za m² powyżej średniej dla {city.title() if city != 'default' else 'regionu'}")
        
        # Metraż
        if listing.area_sqm:
            if listing.area_sqm >= 60:
                pros.append(f"Przestronne mieszkanie ({listing.area_sqm} m²)")
            elif listing.area_sqm < 35:
                cons.append(f"Mały metraż ({listing.area_sqm} m²)")
        
        # Okolica
        if neighborhood_score:
            # Peace & Quiet
            if neighborhood_score.quiet_score is not None:
                if neighborhood_score.quiet_score >= 70:
                    pros.append("Cicha, zielona okolica")
                elif neighborhood_score.quiet_score <= 35:
                     # Only add as negative if we don't have too many cons yet
                     cons.append("Głośna okolica / duży ruch")

            if neighborhood_score.total_score >= 70:
                pros.append("Bardzo dobra infrastruktura w okolicy")
            elif neighborhood_score.total_score >= 50:
                pros.append("Dobra infrastruktura w okolicy")
            elif neighborhood_score.total_score < 30:
                cons.append("Słaba infrastruktura w okolicy")
            
            # Szczegóły kategorii
            for cat, score in neighborhood_score.category_scores.items():
                if score >= 80 and len(pros) < 3:
                    cat_names = {
                        'transport': 'Doskonały dostęp do transportu publicznego',
                        'shops': 'Wiele sklepów w pobliżu',
                        'leisure': 'Blisko terenów rekreacyjnych',
                        'education': 'Szkoły/przedszkola w zasięgu spaceru',
                    }
                    if cat in cat_names:
                        pros.append(cat_names[cat])
                elif score <= 20 and len(cons) < 3:
                    cat_names = { # Only mention if relevant
                        'transport': 'Słaby dostęp do transportu publicznego',
                    }
                    if cat in cat_names:
                        cons.append(cat_names[cat])
        
        # Piętro
        if listing.floor:
            floor_lower = listing.floor.lower()
            if floor_lower == 'parter' or floor_lower == '0':
                cons.append("Parter - potencjalnie mniej prywatności i bezpieczeństwa")
            elif floor_lower in ['1', '2', '3']:
                pros.append(f"Wygodne piętro ({listing.floor})")
        
        # Liczba pokoi vs metraż
        if listing.rooms and listing.area_sqm:
            avg_room_size = listing.area_sqm / listing.rooms
            if avg_room_size >= 18:
                if len(pros) < 3:
                    pros.append("Duże pokoje")
            elif avg_room_size < 12:
                if len(cons) < 3:
                    cons.append("Małe pokoje")
        
        # Uzupełnij do 3 jeśli brak
        while len(pros) < 3:
            defaults = [
                "Sprawdź dokumentację prawną",
                "Zweryfikuj stan techniczny przy oględzinach",
                "Porównaj z podobnymi ofertami w okolicy",
            ]
            for d in defaults:
                if d not in pros and len(pros) < 3:
                    pros.append(d)
                    break
            else:
                break
        
        while len(cons) < 3:
            defaults = [
                "Brak pełnych danych o lokalizacji",
                "Zweryfikuj aktualność ogłoszenia",
                "Sprawdź koszty eksploatacji",
            ]
            for d in defaults:
                if d not in cons and len(cons) < 3:
                    cons.append(d)
                    break
            else:
                break
        
        return pros[:3], cons[:3]
    

    
    def _generate_warnings(self, listing: ListingData) -> List[str]:
        """Generuje ostrzeżenia."""
        warnings = []
        
        if not listing.price:
            warnings.append("Nie udało się pobrać ceny z ogłoszenia.")
        
        if not listing.area_sqm:
            warnings.append("Brak informacji o metrażu.")
        
        if not listing.description:
            warnings.append("Brak opisu - może to być niekompletne ogłoszenie.")
        
        if listing.description and len(listing.description) < 100:
            warnings.append("Bardzo krótki opis ogłoszenia.")
        
        return warnings
    
    def _detect_city(self, location: str) -> str:
        """Próbuje wykryć miasto z lokalizacji."""
        location_lower = location.lower()
        
        cities = ['warszawa', 'kraków', 'wrocław', 'poznań', 'gdańsk', 'łódź', 'katowice']
        for city in cities:
            if city in location_lower:
                return city
        
        return 'default'
    
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
            'food': '#EC4899',           # pink-500
            'finance': '#64748B',        # slate-500
        }

        water_subcategories = {
            'water', 'beach', 'river', 'stream', 'canal', 'lake', 'pond', 'reservoir'
        }
        
        for category, pois in pois_by_category.items():
            for poi in pois:
                color = category_colors.get(category, '#6B7280')
                if category == 'nature_background' and (poi.subcategory or '').lower() in water_subcategories:
                    # Wyróżnij wodę innym kolorem na mapie
                    color = '#F97316'  # orange-500

                markers.append({
                    'lat': poi.lat,
                    'lon': poi.lon,
                    'name': poi.name,
                    'category': category,
                    'subcategory': poi.subcategory,
                    'color': color,
                    'distance': round(poi.distance_m) if poi.distance_m else None
                })
        
        return markers
