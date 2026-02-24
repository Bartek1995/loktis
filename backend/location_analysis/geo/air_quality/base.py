from typing import Optional, Dict
from abc import ABC, abstractmethod


class AirQualityProvider(ABC):
    """
    Abstrakcyjny dostawca danych o jakości powietrza.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Nazwa providera podawana statycznie."""
        pass
        
    @abstractmethod
    def get_air_quality(self, lat: float, lon: float) -> Optional[Dict]:
        """
        Pobiera informację o jakości powietrza z danego API.
        Zwraca słownik w standardowym formacie `air_quality` lub None.
        
        Słownik wynikowy powinien wyglądać tak:
        {
            "aqi": 42,            # Ogólny indeks, np. Europejski
            "pm10": 12.5,         # µg/m³
            "pm25": 8.0,          # µg/m³
            "provider": "nazwa"   # Źródło danych
        }
        """
        pass
