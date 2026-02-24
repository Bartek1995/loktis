import logging
import requests
from typing import Optional, Dict

from .base import AirQualityProvider


logger = logging.getLogger(__name__)


class OpenMeteoAirQualityProvider(AirQualityProvider):
    """
    Dostawca danych o jakości powietrza wykorzystujący darmowe, niewymagające 
    klucza API dostarczane przez Open-Meteo.
    Zwraca ustandaryzowany wektor (EAQI, PM10, PM2.5).
    """

    BASE_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
    
    @property
    def name(self) -> str:
        return "open_meteo"
        
    def get_air_quality(self, lat: float, lon: float) -> Optional[Dict]:
        """
        Pobiera historyczne (ostatnie 365 dni) dane o jakości powietrza dla punktu 
        i oblicza średnie wartości (AQI, PM10, PM2.5). Używamy średniej rocznej, 
        aby uwzględnić sezonowość (np. sezon grzewczy/smog w zimie).
        Dokumentacja: https://open-meteo.com/en/docs/air-quality-api
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "european_aqi,pm10,pm2_5",
            "past_days": 365
        }
        
        try:
            logger.debug(f"Pobieranie jakości powietrza Open-Meteo (365 dni) dla {lat}, {lon}")
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            hourly = data.get("hourly", {})
            
            if not hourly:
                logger.warning("Brak sekcji 'hourly' w odpowiedzi Open-Meteo Air Quality")
                return None
            
            time_list = hourly.get("time", [])
            aqi_list = hourly.get("european_aqi", [])
            pm10_list = hourly.get("pm10", [])
            pm25_list = hourly.get("pm2_5", [])
            
            if not time_list or not aqi_list:
                logger.debug(f"Open-Meteo nie zwróciło historycznych wartości (time lub EAQI) dla {lat}, {lon}")
                return None
                
            # Ogólne średnie dla całego roku
            valid_aqi = [v for v in aqi_list if v is not None]
            valid_pm10 = [v for v in pm10_list if v is not None]
            valid_pm25 = [v for v in pm25_list if v is not None]
            
            avg_aqi = round(sum(valid_aqi) / len(valid_aqi)) if valid_aqi else None
            avg_pm10 = round(sum(valid_pm10) / len(valid_pm10), 1) if valid_pm10 else None
            avg_pm25 = round(sum(valid_pm25) / len(valid_pm25), 1) if valid_pm25 else None
            
            if avg_aqi is None:
                return None
            
            # Grupowanie po miesiącach do wykresu
            # time to ISO stringi np. "2023-11-20T12:00"
            monthly_data = {}
            for i, ts in enumerate(time_list):
                if not ts: continue
                # Weź samo YYYY-MM
                month_key = ts[:7]
                
                if month_key not in monthly_data:
                    monthly_data[month_key] = {"aqi": [], "pm10": [], "pm25": []}
                
                if i < len(aqi_list) and aqi_list[i] is not None:
                    monthly_data[month_key]["aqi"].append(aqi_list[i])
                if i < len(pm10_list) and pm10_list[i] is not None:
                    monthly_data[month_key]["pm10"].append(pm10_list[i])
                if i < len(pm25_list) and pm25_list[i] is not None:
                    monthly_data[month_key]["pm25"].append(pm25_list[i])
            
            monthly_history = []
            for m_key, m_vals in monthly_data.items():
                m_avg_aqi = round(sum(m_vals["aqi"]) / len(m_vals["aqi"])) if m_vals["aqi"] else None
                m_avg_pm10 = round(sum(m_vals["pm10"]) / len(m_vals["pm10"]), 1) if m_vals["pm10"] else None
                m_avg_pm25 = round(sum(m_vals["pm25"]) / len(m_vals["pm25"]), 1) if m_vals["pm25"] else None
                
                if m_avg_aqi is not None:
                    monthly_history.append({
                        "month": m_key,
                        "aqi": m_avg_aqi,
                        "pm10": m_avg_pm10,
                        "pm25": m_avg_pm25
                    })
            
            # Sort chronologicznie
            monthly_history.sort(key=lambda x: x["month"])
                
            return {
                "aqi": avg_aqi,
                "pm10": avg_pm10,
                "pm25": avg_pm25,
                "provider": self.name,
                "period": "last_365_days_average",
                "monthly_history": monthly_history
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd sieci podczas łączenia z Open-Meteo Air Quality: {e}")
            return None
        except Exception as e:
            logger.exception(f"Nieoczekiwany błąd przy parsowaniu Open-Meteo Air Quality: {e}")
            return None
