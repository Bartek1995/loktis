"""
Rescore Service — przeliczenie raportu na inny profil bez ponownego pobierania POI.

Odtwarza pois_by_category z zapisanych danych w report_data.neighborhood.poi_stats,
przelicza scoring + verdict + AI insights dla nowego profilu.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

from .models import LocationAnalysis
from .scoring.profiles import get_profile, ProfileConfig
from .scoring.profile_engine import create_scoring_engine, ScoringResult
from .scoring.profile_verdict import ProfileVerdictGenerator
from .analysis_factsheet import build_factsheet_from_scoring
from .ai_insights import generate_insights_from_factsheet
from .providers import PropertyData
from .diagnostics import AnalysisTraceContext, get_diag_logger

logger = logging.getLogger(__name__)


class RescoreLimitExceeded(Exception):
    """Raised when rescore limit is reached."""
    pass


class RescoreDataMissing(Exception):
    """Raised when report data is insufficient for rescoring."""
    pass


@dataclass
class FakePOI:
    """Lekki POI wystarczający do rescoringu (bez pełnych tagów OSM)."""
    lat: float = 0.0
    lon: float = 0.0
    name: str = ""
    category: str = ""
    subcategory: str = ""
    distance_m: float = 0.0
    tags: dict = field(default_factory=dict)
    source: str = "rescore"
    primary_category: Optional[str] = None
    secondary_categories: List[str] = field(default_factory=list)
    category_scores: Dict[str, float] = field(default_factory=dict)
    badges: List[str] = field(default_factory=list)
    osm_uid: Optional[str] = None
    place_id: Optional[str] = None


class RescoreService:
    """
    Przelicza raport na inny profil bez ponownego odpytywania API geo.
    """

    def rescore(
        self,
        analysis: LocationAnalysis,
        new_profile_key: str,
    ) -> Dict[str, Any]:
        """
        Przelicza scoring + verdict + AI insights dla nowego profilu.

        Returns:
            dict z kluczami: scoring, verdict, ai_insights, profile,
                             rescore_count, rescore_limit
        Raises:
            RescoreLimitExceeded: gdy limit zmian profilu został osiągnięty
            RescoreDataMissing: gdy brakuje danych POI w raporcie
        """
        ctx = AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)

        # 1. Sprawdź limit
        if analysis.rescore_count >= analysis.rescore_limit:
            raise RescoreLimitExceeded(
                f"Limit zmian profilu osiągnięty ({analysis.rescore_limit}/{analysis.rescore_limit})"
            )

        # 2. Sprawdź, czy dany profil nie jest taki sam jak obecny
        current_profile_key = analysis.profile_key or 'family'
        if new_profile_key == current_profile_key:
            raise ValueError(f"Raport już używa profilu '{new_profile_key}'")

        slog.info(
            stage="rescore", op="start",
            message="Profile rescore",
            meta={
                "public_id": analysis.public_id,
                "from_profile": current_profile_key,
                "to_profile": new_profile_key,
                "rescore_count": analysis.rescore_count,
            }
        )

        # 3. Odtwórz pois_by_category z report_data
        pois_by_category = self._reconstruct_pois(analysis)

        # 4. Odtwórz quiet_score i nature_metrics
        quiet_score = self._extract_quiet_score(analysis)
        nature_metrics = self._extract_nature_metrics(analysis)
        base_neighborhood_score = analysis.neighborhood_score or 50.0

        # 5. Pobierz nowy profil
        profile = get_profile(new_profile_key)

        # 6. Profile scoring
        ctx.start_stage("profile_scoring")
        profile_engine = create_scoring_engine(new_profile_key)
        scoring_result = profile_engine.calculate(
            pois_by_category=pois_by_category,
            quiet_score=quiet_score,
            nature_metrics=nature_metrics,
            base_neighborhood_score=base_neighborhood_score,
        )
        ctx.end_stage("profile_scoring")

        # 7. Verdict
        ctx.start_stage("verdict")
        verdict_generator = ProfileVerdictGenerator()
        verdict = verdict_generator.generate(scoring_result, profile)
        ctx.end_stage("verdict")

        slog.info(
            stage="rescore", op="scored",
            meta={
                "new_score": round(scoring_result.total_score, 1),
                "verdict": verdict.level.value,
                "profile": new_profile_key,
            }
        )

        # 8. AI Insights
        ai_insights = None
        ctx.start_stage("ai")
        try:
            listing = self._build_listing_stub(analysis)
            factsheet = build_factsheet_from_scoring(
                profile=profile,
                scoring_result=scoring_result,
                verdict=verdict,
                quiet_score=quiet_score,
                pois_by_category=pois_by_category,
                listing=listing,
            )
            ai_insights = generate_insights_from_factsheet(factsheet)
            ai_dur = ctx.end_stage("ai")
            slog.info(stage="rescore", op="ai_done", duration_ms=ai_dur)
        except Exception as e:
            ctx.end_stage("ai")
            slog.warning(stage="rescore", op="ai_failed", message=str(e), error_class="runtime")

        # 9. Zapisz do DB
        scoring_data = scoring_result.to_dict()
        verdict_data = verdict.to_dict()
        ai_insights_data = {}
        if ai_insights:
            ai_insights_data = {
                'summary': ai_insights.summary,
                'quick_facts': ai_insights.quick_facts if hasattr(ai_insights, 'quick_facts') else [],
                'attention_points': ai_insights.attention_points,
                'verification_checklist': ai_insights.verification_checklist,
                'recommendation_line': ai_insights.recommendation_line if hasattr(ai_insights, 'recommendation_line') else '',
                'target_audience': ai_insights.target_audience if hasattr(ai_insights, 'target_audience') else '',
                'disclaimer': ai_insights.disclaimer if hasattr(ai_insights, 'disclaimer') else '',
            }

        analysis.profile_key = new_profile_key
        analysis.scoring_data = scoring_data
        analysis.verdict_data = verdict_data
        analysis.ai_insights_data = ai_insights_data
        analysis.persona_adjusted_score = scoring_result.total_score
        analysis.rescore_count += 1

        # Aktualizuj category_scores
        category_scores = {
            cat: result.to_dict()
            for cat, result in scoring_result.category_results.items()
        }
        analysis.category_scores = category_scores

        analysis.save(update_fields=[
            'profile_key', 'scoring_data', 'verdict_data',
            'ai_insights_data', 'persona_adjusted_score',
            'rescore_count', 'category_scores',
        ])

        slog.info(
            stage="rescore", op="complete",
            meta={
                "public_id": analysis.public_id,
                "rescore_count": analysis.rescore_count,
            }
        )

        # 10. Zwróć partial response
        response = {
            'scoring': scoring_data,
            'verdict': verdict_data,
            'ai_insights': ai_insights_data,
            'profile': profile.to_dict(),
            'generation_params': {
                'profile': {
                    'key': profile.key,
                    'name': profile.name,
                    'emoji': profile.emoji,
                    'ux_context': profile.ux_context if hasattr(profile, 'ux_context') else {},
                },
                'radii': dict(profile.radius_m),
            },
            'rescore_count': analysis.rescore_count,
            'rescore_limit': analysis.rescore_limit,
        }
        return response

    def _reconstruct_pois(self, analysis: LocationAnalysis) -> Dict[str, List[FakePOI]]:
        """
        Odtwarza pois_by_category z report_data.neighborhood.poi_stats.
        Każdy item w poi_stats ma: name, distance_m, subcategory, badges, source, rating, reviews.
        """
        report_data = analysis.report_data or {}
        neighborhood = report_data.get('neighborhood', {})
        poi_stats = neighborhood.get('poi_stats', {})

        if not poi_stats:
            raise RescoreDataMissing(
                "Brak danych POI w raporcie — nie można przeliczyć scoringu."
            )

        pois_by_category: Dict[str, List[FakePOI]] = {}

        for category, stats in poi_stats.items():
            items = stats.get('items', [])
            pois = []
            for item in items:
                poi = FakePOI(
                    name=item.get('name', ''),
                    category=category,
                    subcategory=item.get('subcategory', ''),
                    distance_m=item.get('distance_m', 0),
                    primary_category=category,
                    badges=item.get('badges', []),
                    source=item.get('source', 'rescore'),
                    tags={
                        'source': item.get('source', 'rescore'),
                        'rating': item.get('rating'),
                        'reviews_count': item.get('reviews'),
                        'user_ratings_total': item.get('reviews'),
                    },
                )
                pois.append(poi)
            pois_by_category[category] = pois

        return pois_by_category

    def _extract_quiet_score(self, analysis: LocationAnalysis) -> float:
        """Wyciąga quiet_score z istniejących danych scoringu."""
        scoring_data = analysis.scoring_data or {}
        return scoring_data.get('quiet_score', 50.0)

    def _extract_nature_metrics(self, analysis: LocationAnalysis) -> Optional[Dict]:
        """Wyciąga nature_metrics z report_data."""
        report_data = analysis.report_data or {}
        neighborhood = report_data.get('neighborhood', {})
        details = neighborhood.get('details', {})
        return details.get('nature_metrics')

    def _build_listing_stub(self, analysis: LocationAnalysis) -> PropertyData:
        """Buduje minimalny PropertyData z bazy dla factsheet."""
        listing = PropertyData(
            url=analysis.url or '',
            title=analysis.title or analysis.address or '',
            price=float(analysis.price) if analysis.price else None,
            area_sqm=analysis.area_sqm,
            latitude=analysis.latitude,
            longitude=analysis.longitude,
            has_precise_location=analysis.has_precise_location,
            location=analysis.address or '',
        )
        if listing.price and listing.area_sqm:
            listing.price_per_sqm = round(listing.price / listing.area_sqm, 2)
        listing.source = 'user'
        return listing


# Singleton
rescore_service = RescoreService()
