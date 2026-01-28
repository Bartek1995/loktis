"""
Moduł parserów ogłoszeń nieruchomości.
Każdy provider obsługuje jeden serwis (Otodom, OLX, itp.).
"""
from .base import BaseProvider, ListingData
from .otodom import OtodomProvider
from .olx import OlxProvider
from .registry import ProviderRegistry, get_provider_for_url

__all__ = [
    'BaseProvider',
    'ListingData',
    'OtodomProvider',
    'OlxProvider',
    'ProviderRegistry',
    'get_provider_for_url',
]
