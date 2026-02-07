"""
Prosty in-memory cache z TTL.
"""
import time
import threading
import hashlib
from typing import Optional, Any, Dict
from dataclasses import dataclass


@dataclass
class CacheEntry:
    """Wpis w cache."""
    value: Any
    expires_at: float


class TTLCache:
    """
    Prosty cache in-memory z TTL (Time To Live).
    Thread-safe.
    """
    
    def __init__(self, default_ttl: int = 3600, max_size: int = 1000):
        """
        Args:
            default_ttl: Domyślny czas życia w sekundach (1 godzina)
            max_size: Maksymalna liczba wpisów
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._default_ttl = default_ttl
        self._max_size = max_size
    
    def get(self, key: str) -> Optional[Any]:
        """Pobiera wartość z cache lub None jeśli nie istnieje/wygasła."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            
            if time.time() > entry.expires_at:
                del self._cache[key]
                return None
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Ustawia wartość w cache.
        
        Args:
            key: Klucz
            value: Wartość
            ttl: Czas życia w sekundach (opcjonalny)
        """
        ttl = ttl or self._default_ttl
        expires_at = time.time() + ttl
        
        with self._lock:
            # Jeśli przekroczono limit, usuń najstarsze
            if len(self._cache) >= self._max_size:
                self._cleanup()
            
            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)
    
    def delete(self, key: str) -> bool:
        """Usuwa wpis z cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """Czyści cały cache."""
        with self._lock:
            self._cache.clear()
    
    def _cleanup(self) -> None:
        """Usuwa wygasłe wpisy i najstarsze jeśli trzeba."""
        now = time.time()
        
        # Usuń wygasłe
        expired_keys = [
            k for k, v in self._cache.items()
            if now > v.expires_at
        ]
        for k in expired_keys:
            del self._cache[k]
        
        # Jeśli nadal za dużo, usuń 20% najstarszych
        if len(self._cache) >= self._max_size:
            sorted_keys = sorted(
                self._cache.keys(),
                key=lambda k: self._cache[k].expires_at
            )
            to_remove = len(self._cache) - int(self._max_size * 0.8)
            for k in sorted_keys[:to_remove]:
                del self._cache[k]
    
    @staticmethod
    def make_key(*args) -> str:
        """Tworzy klucz cache z argumentów."""
        key_str = ':'.join(str(a) for a in args)
        return hashlib.md5(key_str.encode()).hexdigest()


# Globalne instancje cache
listing_cache = TTLCache(default_ttl=3600, max_size=500)  # 1h dla ogłoszeń
overpass_cache = TTLCache(default_ttl=604800, max_size=200)  # 7 dni dla POI
google_details_cache = TTLCache(default_ttl=604800, max_size=2000)  # 7 dni dla Google Details
google_nearby_cache = TTLCache(default_ttl=259200, max_size=2000)  # 3 dni dla Google Nearby


def normalize_coords(lat: float, lon: float, precision: int = 4) -> tuple:
    """
    Normalizuje współrzędne do siatki dla lepszego cache hit rate.
    Precision=4 => ~11m siatka, precision=5 => ~1m siatka.
    """
    return (round(lat, precision), round(lon, precision))
