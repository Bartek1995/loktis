"""
Centralny moduł konfiguracji aplikacji Nest Score.

Single source of truth dla wszystkich ustawień:
- Overpass API (endpointy, timeout)
- Google Places API (klucz, włączenie, retries)
- Domyślne flagi analizy (enrichment, fallback, provider)
- Toggles sekcji raportu (air quality, AI insights, nature)
- Rate limiting
- Cache TTLs

Wartości czytane z django.conf.settings.NEST_SCORE_CONFIG,
z fallbackiem na sensowne defaults.
"""
import os
import threading
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class AppConfig:
    """Centralna konfiguracja aplikacji."""

    # --- Overpass API ---
    overpass_mode: str = "public"  # 'public' lub 'local'
    overpass_local_url: str = "http://localhost:12345/api/interpreter"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    overpass_fallback_urls: List[str] = field(default_factory=lambda: [
        "https://lz4.overpass-api.de/api/interpreter",
        "https://z.overpass-api.de/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ])
    overpass_timeout: int = 60

    # --- Google Places API ---
    google_places_enabled: bool = True
    google_places_api_key: str = ""
    google_max_retries: int = 2

    # --- Domyślne flagi analizy ---
    default_enrichment: bool = False
    default_fallback: bool = True
    default_poi_provider: str = "hybrid"  # 'overpass' | 'google' | 'hybrid'
    default_radius: int = 500

    # --- Sekcje raportu (toggles) ---
    report_air_quality: bool = True
    report_noise_analysis: bool = False  # Placeholder — future
    report_ai_insights: bool = True
    report_nature_metrics: bool = True
    report_data_quality: bool = True

    # --- Air Quality ---
    air_quality_provider: str = "open_meteo"  # 'open_meteo' | future: 'gios'
    air_quality_enabled: bool = True

    # --- AI Provider ---
    ai_provider: str = "ollama"  # 'gemini' | 'ollama' | 'off'
    ai_model_gemini: str = "gemini-2.0-flash"
    ai_model_ollama: str = "qwen2.5:7b-instruct"
    ollama_base_url: str = "http://localhost:11434"
    ai_temperature_gemini: float = 0.6
    ai_temperature_ollama: float = 0.3
    gemini_api_key: str = ""

    # --- Rate Limiting ---
    rate_limit_per_minute: int = 5
    rate_limit_per_hour: int = 30

    # --- Cache TTLs (sekundy) ---
    cache_ttl_listing: int = 3600          # 1h
    cache_ttl_pois: int = 604800           # 7 dni
    cache_ttl_google_details: int = 604800  # 7 dni
    cache_ttl_google_nearby: int = 259200   # 3 dni

    @property
    def overpass_endpoints(self) -> List[str]:
        """Zwraca pełną listę endpointów Overpass (primary + fallbacki)."""
        endpoints = []
        if self.overpass_mode == 'local' and self.overpass_local_url:
            endpoints.append(self.overpass_local_url)
        elif self.overpass_url:
            endpoints.append(self.overpass_url)
        for url in self.overpass_fallback_urls:
            url = url.strip()
            if url and url not in endpoints:
                endpoints.append(url)
        return endpoints

    def to_public_dict(self) -> Dict[str, Any]:
        """
        Zwraca konfigurację bez sekretów — bezpieczne do wystawienia przez API.
        """
        return {
            "overpass": {
                "mode": self.overpass_mode,
                "local_url": self.overpass_local_url,
                "url": self.overpass_url,
                "fallback_urls": self.overpass_fallback_urls,
                "timeout": self.overpass_timeout,
            },
            "google_places": {
                "enabled": self.google_places_enabled,
                "has_api_key": bool(self.google_places_api_key),
                "max_retries": self.google_max_retries,
            },
            "defaults": {
                "enrichment": self.default_enrichment,
                "fallback": self.default_fallback,
                "poi_provider": self.default_poi_provider,
                "radius": self.default_radius,
            },
            "report_sections": {
                "air_quality": self.report_air_quality,
                "noise_analysis": self.report_noise_analysis,
                "ai_insights": self.report_ai_insights,
                "nature_metrics": self.report_nature_metrics,
                "data_quality": self.report_data_quality,
            },
            "air_quality": {
                "provider": self.air_quality_provider,
                "enabled": self.air_quality_enabled,
            },
            "rate_limiting": {
                "per_minute": self.rate_limit_per_minute,
                "per_hour": self.rate_limit_per_hour,
            },
            "cache_ttl": {
                "listing": self.cache_ttl_listing,
                "pois": self.cache_ttl_pois,
                "google_details": self.cache_ttl_google_details,
                "google_nearby": self.cache_ttl_google_nearby,
            },
            "ai": {
                "provider": self.ai_provider,
                "model_gemini": self.ai_model_gemini,
                "model_ollama": self.ai_model_ollama,
                "ollama_base_url": self.ollama_base_url,
                "has_gemini_key": bool(self.gemini_api_key),
            },
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_config_instance: Optional[AppConfig] = None
_config_lock = threading.Lock()


def _parse_bool(value: Any, default: bool = False) -> bool:
    """Parsuje wartość na bool (obsługuje stringi z env vars)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on')
    return default


def _parse_list(value: Any, default: List[str] = None) -> List[str]:
    """Parsuje wartość na listę stringów (obsługuje stringi CSV)."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [v.strip() for v in value.split(',') if v.strip()]
    return default or []


def get_config() -> AppConfig:
    """
    Zwraca singleton AppConfig.
    Ładuje z django.conf.settings.NEST_SCORE_CONFIG (dict),
    fallback na defaults z dataclass.
    """
    global _config_instance
    if _config_instance is not None:
        return _config_instance

    with _config_lock:
        # Double-check locking
        if _config_instance is not None:
            return _config_instance

        try:
            from django.conf import settings
            raw = getattr(settings, 'LOKTIS_CONFIG', {})
        except Exception:
            raw = {}

        defaults = AppConfig()
        _config_instance = AppConfig(
            # Overpass
            overpass_mode=raw.get('OVERPASS_MODE', defaults.overpass_mode),
            overpass_local_url=raw.get('OVERPASS_LOCAL_URL', defaults.overpass_local_url),
            overpass_url=raw.get('OVERPASS_URL', defaults.overpass_url),
            overpass_fallback_urls=_parse_list(
                raw.get('OVERPASS_FALLBACK_URLS'),
                defaults.overpass_fallback_urls,
            ),
            overpass_timeout=int(raw.get('OVERPASS_TIMEOUT', defaults.overpass_timeout)),

            # Google Places
            google_places_enabled=_parse_bool(
                raw.get('GOOGLE_PLACES_ENABLED', defaults.google_places_enabled),
                default=defaults.google_places_enabled,
            ),
            google_places_api_key=raw.get(
                'GOOGLE_PLACES_API_KEY',
                defaults.google_places_api_key,
            ),
            google_max_retries=int(raw.get('GOOGLE_MAX_RETRIES', defaults.google_max_retries)),

            # Defaults analizy
            default_enrichment=_parse_bool(
                raw.get('DEFAULT_ENRICHMENT', defaults.default_enrichment),
                default=defaults.default_enrichment,
            ),
            default_fallback=_parse_bool(
                raw.get('DEFAULT_FALLBACK', defaults.default_fallback),
                default=defaults.default_fallback,
            ),
            default_poi_provider=raw.get('DEFAULT_POI_PROVIDER', defaults.default_poi_provider),
            default_radius=int(raw.get('DEFAULT_RADIUS', defaults.default_radius)),

            # Report toggles
            report_air_quality=_parse_bool(
                raw.get('REPORT_AIR_QUALITY', defaults.report_air_quality),
                default=defaults.report_air_quality,
            ),
            report_noise_analysis=_parse_bool(
                raw.get('REPORT_NOISE_ANALYSIS', defaults.report_noise_analysis),
                default=defaults.report_noise_analysis,
            ),
            report_ai_insights=_parse_bool(
                raw.get('REPORT_AI_INSIGHTS', defaults.report_ai_insights),
                default=defaults.report_ai_insights,
            ),
            report_nature_metrics=_parse_bool(
                raw.get('REPORT_NATURE_METRICS', defaults.report_nature_metrics),
                default=defaults.report_nature_metrics,
            ),
            report_data_quality=_parse_bool(
                raw.get('REPORT_DATA_QUALITY', defaults.report_data_quality),
                default=defaults.report_data_quality,
            ),

            # Air Quality
            air_quality_provider=raw.get('AIR_QUALITY_PROVIDER', defaults.air_quality_provider),
            air_quality_enabled=_parse_bool(
                raw.get('AIR_QUALITY_ENABLED', defaults.air_quality_enabled),
                default=defaults.air_quality_enabled,
            ),

            # Rate Limiting
            rate_limit_per_minute=int(raw.get('RATE_LIMIT_PER_MINUTE', defaults.rate_limit_per_minute)),
            rate_limit_per_hour=int(raw.get('RATE_LIMIT_PER_HOUR', defaults.rate_limit_per_hour)),

            # Cache TTLs
            cache_ttl_listing=int(raw.get('CACHE_TTL_LISTING', defaults.cache_ttl_listing)),
            cache_ttl_pois=int(raw.get('CACHE_TTL_POIS', defaults.cache_ttl_pois)),
            cache_ttl_google_details=int(raw.get('CACHE_TTL_GOOGLE_DETAILS', defaults.cache_ttl_google_details)),
            cache_ttl_google_nearby=int(raw.get('CACHE_TTL_GOOGLE_NEARBY', defaults.cache_ttl_google_nearby)),

            # AI Provider
            ai_provider=raw.get('AI_PROVIDER', defaults.ai_provider),
            ai_model_gemini=raw.get('AI_MODEL_GEMINI', defaults.ai_model_gemini),
            ai_model_ollama=raw.get('AI_MODEL_OLLAMA', defaults.ai_model_ollama),
            ollama_base_url=raw.get('OLLAMA_BASE_URL', defaults.ollama_base_url),
            ai_temperature_gemini=float(raw.get('AI_TEMPERATURE_GEMINI', defaults.ai_temperature_gemini)),
            ai_temperature_ollama=float(raw.get('AI_TEMPERATURE_OLLAMA', defaults.ai_temperature_ollama)),
            gemini_api_key=raw.get('GEMINI_API_KEY', defaults.gemini_api_key),
        )

        return _config_instance


def reset_config() -> None:
    """Resetuje singleton (przydatne w testach)."""
    global _config_instance
    with _config_lock:
        _config_instance = None
