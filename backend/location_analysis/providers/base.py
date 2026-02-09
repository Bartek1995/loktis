"""
Bazowa klasa dla providerów ogłoszeń.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List
from decimal import Decimal


@dataclass
class PropertyData:
    """
    Ustandaryzowane dane o nieruchomości.
    Używane zarówno przez parsery ogłoszeń jak i wprowadzanie ręczne (location-first).
    """
    url: str = ""
    title: str = ""
    address: str = ""
    price: Optional[Decimal] = None
    price_per_sqm: Optional[Decimal] = None
    area_sqm: Optional[float] = None
    rooms: Optional[int] = None
    floor: str = ""
    location: str = ""
    description: str = ""
    images: List[str] = field(default_factory=list)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    has_precise_location: bool = False
    raw_data: dict = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    
    # Source mode: "none" = no listing data, "manual" = user entered, "fetched" = parsed from URL
    source: str = "none"
    
    def to_dict(self) -> dict:
        return {
            'url': self.url,
            'title': self.title,
            'address': self.address,
            'price': float(self.price) if self.price else None,
            'price_per_sqm': float(self.price_per_sqm) if self.price_per_sqm else None,
            'area_sqm': self.area_sqm,
            'rooms': self.rooms,
            'floor': self.floor,
            'location': self.location or self.address,
            'description': self.description,
            'images': self.images[:10],
            'latitude': self.latitude,
            'longitude': self.longitude,
            'has_precise_location': self.has_precise_location,
            'errors': self.errors,
            'source': self.source,
        }


# Alias for backward compatibility
ListingData = PropertyData


class BaseProvider(ABC):
    """Bazowa klasa dla providerów parsujących ogłoszenia."""
    
    name: str = "base"
    domains: List[str] = []
    
    REQUEST_TIMEOUT = 15
    
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    
    def get_headers(self) -> dict:
        return {
            'User-Agent': self.USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pl-PL,pl;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
    
    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Sprawdza czy provider obsługuje dany URL."""
        pass
    
    @abstractmethod
    def parse(self, url: str) -> PropertyData:
        """
        Parsuje ogłoszenie z podanego URL.
        Zwraca PropertyData z danymi (mogą być niepełne).
        Błędy zapisuje w PropertyData.errors.
        """
        pass
    
    def _extract_number(self, text: str) -> Optional[float]:
        import re
        if not text:
            return None
        cleaned = re.sub(r'\s+', '', text).replace(',', '.')
        match = re.search(r'[\d.]+', cleaned)
        if match:
            try:
                return float(match.group())
            except ValueError:
                return None
        return None
    
    def _extract_price(self, text: str) -> Optional[Decimal]:
        import re
        if not text:
            return None
        cleaned = re.sub(r'[^\d,.\s]', '', text).strip()
        cleaned = re.sub(r'\s+', '', cleaned).replace(',', '.')
        cleaned = cleaned.replace(' ', '')
        try:
            return Decimal(cleaned)
        except:
            return None
