"""
Data Quality Report - tracking POI coverage and confidence.

SEMANTIC DISTINCTION (critical):
- 'empty' = provider OK, but 0 results after filtering → this is SIGNAL, not error
- 'error' = provider failure (timeout, 5xx) → this is DATA QUALITY issue
- 'ok'/'partial' = normal results

Only 'error' status reduces confidence and triggers "Brak pełnych danych" alert.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class CategoryCoverage:
    """Coverage stats for a single POI category."""
    source: str = "none"  # "overpass" | "google" | "mixed" | "none"
    # SEMANTIC STATUS:
    # - "ok": kept >= 3, normal data
    # - "partial": 1-2 kept, sparse but valid
    # - "empty": kept == 0, provider OK → SIGNAL (not error!)
    # - "error": provider failure → DATA QUALITY ISSUE
    status: str = "empty"
    raw_count: int = 0  # Before filters
    kept_count: int = 0  # After filters
    radius_m: int = 1000
    rejects: Dict[str, int] = field(default_factory=dict)  # {"radius": 30, "membership": 4}
    provider_errors: List[str] = field(default_factory=list)  # ["timeout_504"]
    had_provider_error: bool = False  # Was there any error before fallback?
    
    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "status": self.status,
            "raw_count": self.raw_count,
            "kept_count": self.kept_count,
            "radius_m": self.radius_m,
            "rejects": self.rejects,
            "provider_errors": self.provider_errors,
            "had_provider_error": self.had_provider_error,
        }


@dataclass
class DataQualityReport:
    """
    Global data quality report for an analysis.
    
    IMPORTANT SEMANTIC DISTINCTION:
    - empty_categories: provider OK, 0 results → normal signal, NOT an error
    - error_categories: provider failure → data quality issue, TRIGGERS ALERT
    
    confidence_pct only reduced by ERROR, not by EMPTY.
    """
    confidence_pct: int = 100  # 0-100
    reasons: List[str] = field(default_factory=list)  # Human-readable
    overpass_status: str = "ok"  # "ok" | "timeout" | "error" 
    overpass_had_retry: bool = False  # Did overpass need retry?
    fallback_started: List[str] = field(default_factory=list)  # Categories where fallback was initiated
    fallback_contributed: List[str] = field(default_factory=list)  # Categories where fallback added POIs
    coverage: Dict[str, CategoryCoverage] = field(default_factory=dict)
    cache_used: bool = False
    
    # Derived lists for easy access
    empty_categories: List[str] = field(default_factory=list)  # Signal zeros
    error_categories: List[str] = field(default_factory=list)  # Data quality issues
    
    def to_dict(self) -> dict:
        return {
            "confidence_pct": self.confidence_pct,
            "reasons": self.reasons,
            "overpass_status": self.overpass_status,
            "overpass_had_retry": self.overpass_had_retry,
            "fallback_started": self.fallback_started,
            "fallback_contributed": self.fallback_contributed,
            "cache_used": self.cache_used,
            "empty_categories": self.empty_categories,
            "error_categories": self.error_categories,
            "coverage": {k: v.to_dict() for k, v in self.coverage.items()},
        }
    
    def has_data_quality_issues(self) -> bool:
        """Returns True if there are actual data quality problems (not just empty signal)."""
        return len(self.error_categories) > 0 or self.overpass_status == "error"
    
    def log_summary(self, trace_ctx: 'AnalysisTraceContext | None' = None):
        """Log INFO-level summary using structured logging."""
        from .diagnostics import get_diag_logger, AnalysisTraceContext
        ctx = trace_ctx or AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)

        categories_empty = [k for k, v in self.coverage.items() if v.status == "empty"]
        categories_error = [k for k, v in self.coverage.items() if v.status == "error"]
        
        slog.info(
            stage="data_quality", op="coverage_summary",
            meta={
                "confidence": self.confidence_pct,
                "overpass_status": self.overpass_status,
                "cache_used": self.cache_used,
                "fallback_started": self.fallback_started,
                "fallback_contributed": self.fallback_contributed,
                "empty_categories": categories_empty,
                "error_categories": categories_error,
            },
        )
    
    def log_debug(self, trace_ctx: 'AnalysisTraceContext | None' = None):
        """Log DEBUG-level per-category breakdown using structured logging."""
        from .diagnostics import get_diag_logger, AnalysisTraceContext
        ctx = trace_ctx or AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)

        for cat, cov in self.coverage.items():
            slog.debug(
                stage="data_quality", op="coverage_detail",
                meta={
                    "category": cat,
                    "source": cov.source,
                    "status": cov.status,
                    "raw": cov.raw_count,
                    "kept": cov.kept_count,
                    "radius": cov.radius_m,
                    "rejects": cov.rejects or {},
                },
            )


def determine_status(
    kept_count: int,
    raw_count: int,
    had_provider_error: bool,
) -> str:
    """
    Determine category status with correct semantics.
    
    - "ok": >= 3 POIs kept
    - "partial": 1-2 POIs kept
    - "empty": 0 POIs but provider worked → SIGNAL (valid result)
    - "error": provider failure → DATA QUALITY issue
    """
    if had_provider_error and kept_count == 0:
        return "error"  # Provider failed AND we have no data
    
    if kept_count >= 3:
        return "ok"
    elif kept_count >= 1:
        return "partial"
    else:
        # kept_count == 0
        # If raw > 0 → data was there but filtered out
        # If raw == 0 → nothing found in area
        # Both are EMPTY (valid signal), not error
        return "empty"


def calculate_confidence(
    coverage: Dict[str, CategoryCoverage],
    overpass_status: str,
    important_categories: List[str] = None,
    profile_weights: Dict[str, float] = None,
) -> tuple[int, List[str]]:
    """
    Calculate confidence based on DATA QUALITY issues only.
    
    DOES NOT penalize 'empty' status - that's a signal, not an error.
    ONLY penalizes 'error' status and provider failures.
    
    NEW: If profile_weights is provided, penalizes empty categories that
    are CRITICAL for the active profile (weight >= 0.10).
    """
    if important_categories is None:
        important_categories = ["shops", "transport", "education", "health", "nature_place"]
    
    confidence = 100
    reasons = []
    
    # Provider-level errors (these are real data quality issues)
    if overpass_status == "timeout":
        confidence -= 15
        reasons.append("Opóźniona odpowiedź OSM (retry wykonano)")
    elif overpass_status == "error":
        confidence -= 30
        reasons.append("Błąd pobierania danych OSM")
    
    # Category-level errors ONLY (not empty!)
    for cat in important_categories:
        cov = coverage.get(cat)
        if not cov:
            continue
        
        # ONLY penalize actual errors, not empty signals
        if cov.status == "error":
            confidence -= 20
            reasons.append(f"Brak danych: {_category_name(cat)} (błąd źródła)")
        
        # Note: 'empty' is NOT penalized - it's valid signal
        # Note: 'partial' is NOT penalized - sparse data is still valid
    
    # Profile-aware: empty category with high weight = lower confidence
    if profile_weights:
        all_cats = set(important_categories) | set(profile_weights.keys())
        for cat in all_cats:
            weight = abs(profile_weights.get(cat, 0))
            if weight < 0.10:
                continue  # Only care about categories with ≥10% weight
            cov = coverage.get(cat)
            if cov and cov.status == "empty":
                confidence -= 10
                reasons.append(f"Brak obiektów: {_category_name(cat)} w promieniu {cov.radius_m}m")
    
    # Clamp
    confidence = max(0, min(100, confidence))
    
    return confidence, reasons[:5]


def _category_name(cat: str) -> str:
    """Polish category names."""
    names = {
        "shops": "sklepy",
        "transport": "transport",
        "education": "edukacja",
        "health": "zdrowie",
        "nature_place": "zieleń",
        "nature_background": "tło zieleni",
        "leisure": "rekreacja",
        "food": "gastronomia",
        "finance": "finanse",
        "roads": "drogi",
        "car_access": "dostęp samochodem",
    }
    return names.get(cat, cat)


def build_data_quality_report(
    pois_by_category: Dict,
    radii: Dict[str, int],
    overpass_status: str = "ok",
    overpass_had_retry: bool = False,
    fallback_started: List[str] = None,
    fallback_contributed: List[str] = None,
    cache_used: bool = False,
    raw_counts: Dict[str, int] = None,
    reject_counts: Dict[str, Dict[str, int]] = None,
    provider_errors_by_category: Dict[str, List[str]] = None,
    profile_weights: Dict[str, float] = None,
) -> DataQualityReport:
    """
    Build DataQualityReport from POI data and metadata.
    
    Args:
        pois_by_category: Final POIs after filtering
        radii: Radius per category from profile
        overpass_status: "ok" | "timeout" | "error"
        overpass_had_retry: True if Overpass needed retry
        fallback_started: Categories where Google fallback was initiated
        fallback_contributed: Categories where fallback actually added POIs
        cache_used: Whether cache was used
        raw_counts: Raw POI counts before filtering
        reject_counts: Rejection counts per category {"radius": N, "membership": M}
        provider_errors_by_category: Errors per category (if tracked)
    """
    coverage = {}
    empty_categories = []
    error_categories = []
    
    all_categories = set((pois_by_category or {}).keys()) | set(radii.keys())
    queried_categories = set((pois_by_category or {}).keys())
    
    for cat in all_categories:
        pois = (pois_by_category or {}).get(cat, [])
        kept_count = len(pois) if pois else 0
        raw = (raw_counts or {}).get(cat, kept_count)
        rejects = (reject_counts or {}).get(cat, {})
        cat_errors = (provider_errors_by_category or {}).get(cat, [])
        
        # Determine source
        source = "overpass"
        if fallback_started and cat in (fallback_started or []):
            if fallback_contributed and cat in (fallback_contributed or []):
                source = "mixed" if raw > 0 else "google"
            else:
                source = "overpass"  # Fallback was started but didn't contribute
        
        # Category from radii but never queried → not a real data quality issue
        was_queried = cat in queried_categories
        
        # Determine if there was a provider error for this category
        had_error = bool(cat_errors) or (overpass_status == "error" and was_queried)
        
        # Determine status with proper semantics
        if not was_queried and not had_error:
            # Category exists in profile radii but was never queried by any provider
            cat_status = "no_query"
        else:
            cat_status = determine_status(kept_count, raw, had_error)
        
        coverage[cat] = CategoryCoverage(
            source=source,
            status=cat_status,
            raw_count=raw,
            kept_count=kept_count,
            radius_m=radii.get(cat, 1000),
            rejects=rejects,
            provider_errors=cat_errors,
            had_provider_error=had_error,
        )
        
        # Track for easy access
        if cat_status == "empty":
            empty_categories.append(cat)
        elif cat_status == "error":
            error_categories.append(cat)
    
    # Calculate confidence (only penalizes errors, not empty — unless profile-critical)
    confidence, reasons = calculate_confidence(coverage, overpass_status, profile_weights=profile_weights)
    
    report = DataQualityReport(
        confidence_pct=confidence,
        reasons=reasons,
        overpass_status=overpass_status,
        overpass_had_retry=overpass_had_retry,
        fallback_started=fallback_started or [],
        fallback_contributed=fallback_contributed or [],
        coverage=coverage,
        cache_used=cache_used,
        empty_categories=empty_categories,
        error_categories=error_categories,
    )
    
    # Log
    report.log_summary()
    if logger.isEnabledFor(logging.DEBUG):
        report.log_debug()
    
    return report
