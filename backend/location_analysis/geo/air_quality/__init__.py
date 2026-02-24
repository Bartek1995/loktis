from typing import Dict, Type
from .base import AirQualityProvider
from .open_meteo import OpenMeteoAirQualityProvider

# Rejestr providerów by w przyszłości można było tu dopisać 'gios'
_PROVIDERS: Dict[str, Type[AirQualityProvider]] = {
    'open_meteo': OpenMeteoAirQualityProvider,
}

def get_air_quality_provider(name: str = 'open_meteo') -> AirQualityProvider:
    """
    Zwraca instancję dostawcy informacji o jakości powietrza.
    Możliwość dynamicznej wymiany providera w przyszłości.
    """
    provider_class = _PROVIDERS.get(name)
    if not provider_class:
        raise ValueError(f"Nieznany dostawca jakości powietrza: '{name}'")
    
    return provider_class()
