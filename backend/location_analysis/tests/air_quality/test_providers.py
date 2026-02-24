import json
import pytest
from unittest.mock import patch, Mock

from location_analysis.geo.air_quality.open_meteo import OpenMeteoAirQualityProvider
from location_analysis.geo.air_quality import get_air_quality_provider
from location_analysis.geo.air_quality.base import AirQualityProvider


class TestAirQualityProviders:
    """Testy dla modułu Air Quality."""
    
    @patch('requests.get')
    def test_open_meteo_success(self, mock_get):
        """Test poprawnego pobrania i uśrednienia danych z Open-Meteo z ostatnich 365 dni."""
        # Przygotuj mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "hourly": {
                "time": ["2023-10-27T12:00", "2023-10-27T13:00", "2023-10-27T14:00"],
                "european_aqi": [34, 40, 28], # avg: 34
                "pm10": [15.2, 10.0, 20.4], # avg: 15.2
                "pm2_5": [8.1, 5.0, 11.2] # avg: 8.1
            }
        }
        mock_get.return_value = mock_response
        
        provider = OpenMeteoAirQualityProvider()
        result = provider.get_air_quality(52.2297, 21.0122)
        
        # Aserty
        assert result is not None
        assert result["aqi"] == 34
        assert result["pm10"] == 15.2
        assert result["pm25"] == 8.1
        assert result["provider"] == "open_meteo"
        assert result["period"] == "last_365_days_average"
        assert "monthly_history" in result
        assert len(result["monthly_history"]) == 1
        assert result["monthly_history"][0]["month"] == "2023-10"
        assert result["monthly_history"][0]["aqi"] == 34
        
        # Weryfikacja parametrów zapytania
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert "latitude" in kwargs["params"]
        assert "longitude" in kwargs["params"]
        assert "hourly" in kwargs["params"]
        assert "past_days" in kwargs["params"]
        assert kwargs["params"]["past_days"] == 365
        
    @patch('requests.get')
    def test_open_meteo_missing_data(self, mock_get):
        """Test braku danych AQI w responsie (np. awaria stacji wirtualnej lub zła struktura)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "hourly": {
                "time": ["2023-10-27T12:00"],
                "european_aqi": [None], # AQI jest nulem
                "pm10": [10]
            }
        }
        mock_get.return_value = mock_response
        
        provider = OpenMeteoAirQualityProvider()
        result = provider.get_air_quality(52.2297, 21.0122)
        
        # Powinno zwrócić None gdy brakuje kluczowego wskaźnika
        assert result is None
        
    @patch('requests.get')
    def test_open_meteo_network_error(self, mock_get):
        """Test bezpiecznego ubijania w przypadku błędu sieciowego."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout("Timeout")
        
        provider = OpenMeteoAirQualityProvider()
        result = provider.get_air_quality(52.2297, 21.0122)
        
        # Powinno elegancko oddać None, nie wywalając aplikacji
        assert result is None

    def test_provider_factory(self):
        """Test fabryki dostawców."""
        provider = get_air_quality_provider('open_meteo')
        assert isinstance(provider, AirQualityProvider)
        assert isinstance(provider, OpenMeteoAirQualityProvider)
        assert provider.name == 'open_meteo'
        
        # Nieistniejący provider rzuca wyjątek
        with pytest.raises(ValueError):
            get_air_quality_provider('unknown_provider')
