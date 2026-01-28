"""
Rejestr providerów z logiką wyboru.
"""
from typing import Optional, List, Type
from urllib.parse import urlparse

from .base import BaseProvider
from .otodom import OtodomProvider
from .olx import OlxProvider


class ProviderRegistry:
    """Rejestr providerów do parsowania ogłoszeń."""
    
    _providers: List[Type[BaseProvider]] = [
        OtodomProvider,
        OlxProvider,
    ]
    
    # Dozwolone domeny (walidacja bezpieczeństwa)
    ALLOWED_DOMAINS = [
        'otodom.pl',
        'www.otodom.pl',
        'olx.pl',
        'www.olx.pl',
    ]
    
    @classmethod
    def get_provider(cls, url: str) -> Optional[BaseProvider]:
        """Zwraca odpowiedni provider dla URL lub None."""
        for provider_class in cls._providers:
            provider = provider_class()
            if provider.can_handle(url):
                return provider
        return None
    
    @classmethod
    def is_url_allowed(cls, url: str) -> bool:
        """Sprawdza czy URL jest z dozwolonej domeny."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            return domain in cls.ALLOWED_DOMAINS or domain.replace('www.', '') in cls.ALLOWED_DOMAINS
        except:
            return False
    
    @classmethod
    def validate_url(cls, url: str) -> tuple[bool, str]:
        """
        Waliduje URL.
        Zwraca (is_valid, error_message).
        """
        if not url:
            return False, "URL jest wymagany"
        
        if len(url) > 2048:
            return False, "URL jest zbyt długi (max 2048 znaków)"
        
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ('http', 'https'):
                return False, "URL musi zaczynać się od http:// lub https://"
            
            if not parsed.netloc:
                return False, "Nieprawidłowy format URL"
            
        except Exception:
            return False, "Nieprawidłowy format URL"
        
        if not cls.is_url_allowed(url):
            return False, f"Nieobsługiwana domena. Obsługiwane: {', '.join(set(d.replace('www.', '') for d in cls.ALLOWED_DOMAINS))}"
        
        return True, ""


def get_provider_for_url(url: str) -> Optional[BaseProvider]:
    """Skrót do pobrania providera."""
    return ProviderRegistry.get_provider(url)
