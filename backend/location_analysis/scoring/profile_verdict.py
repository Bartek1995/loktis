"""
Profile verdict generator.

Builds a Verdict using profile-based scoring results and profile thresholds.
"""
from typing import List

from .verdict import Verdict, VerdictLevel
from .profiles import ProfileConfig, VerdictThresholds


class ProfileVerdictGenerator:
    """Generates a Verdict from profile-based scoring results."""

    VERDICT_CONFIG = {
        VerdictLevel.RECOMMENDED: {
            'label': 'Polecane',
            'emoji': '✅',
        },
        VerdictLevel.CONDITIONAL: {
            'label': 'Warunkowo polecane',
            'emoji': '⚠️',
        },
        VerdictLevel.NOT_RECOMMENDED: {
            'label': 'Niepolecane',
            'emoji': '❌',
        },
    }

    def generate(self, scoring_result, profile: ProfileConfig) -> Verdict:
        score = scoring_result.total_score
        thresholds = profile.thresholds

        level = self._level_from_score(score, thresholds)
        config = self.VERDICT_CONFIG[level]

        confidence = self._calculate_confidence(score, thresholds)
        profile_match = self._determine_profile_match(score, thresholds)
        explanation = self._generate_explanation(level, score, profile)
        key_factors = self._extract_key_factors(scoring_result, level)

        return Verdict(
            level=level,
            label=config['label'],
            emoji=config['emoji'],
            explanation=explanation,
            key_factors=key_factors,
            score=score,
            confidence=confidence,
            persona_match=profile_match,
        )

    def _level_from_score(self, score: float, thresholds: VerdictThresholds) -> VerdictLevel:
        if score >= thresholds.recommended:
            return VerdictLevel.RECOMMENDED
        if score >= thresholds.conditional:
            return VerdictLevel.CONDITIONAL
        return VerdictLevel.NOT_RECOMMENDED

    def _calculate_confidence(self, score: float, thresholds: VerdictThresholds) -> int:
        dist_to_recommended = abs(score - thresholds.recommended)
        dist_to_conditional = abs(score - thresholds.conditional)
        min_distance = min(dist_to_recommended, dist_to_conditional)

        if min_distance >= 20:
            return 90
        if min_distance >= 15:
            return 80
        if min_distance >= 10:
            return 70
        if min_distance >= 5:
            return 55
        return 45

    def _determine_profile_match(self, score: float, thresholds: VerdictThresholds) -> str:
        if score >= thresholds.recommended + 10:
            return 'excellent'
        if score >= thresholds.recommended:
            return 'good'
        if score >= thresholds.conditional:
            return 'acceptable'
        if score >= thresholds.conditional - 10:
            return 'poor'
        return 'mismatch'

    def _generate_explanation(self, level: VerdictLevel, score: float, profile: ProfileConfig) -> str:
        if level == VerdictLevel.RECOMMENDED:
            return (
                f"Lokalizacja uzyskala {score:.0f}/100 dla profilu "
                f"{profile.emoji} {profile.name}. Spelnia kluczowe kryteria "
                f"i jest rekomendowana."
            )
        if level == VerdictLevel.CONDITIONAL:
            return (
                f"Lokalizacja uzyskala {score:.0f}/100 dla profilu "
                f"{profile.emoji} {profile.name}. Wymaga kompromisow "
                f"do rozwazenia."
            )
        return (
            f"Lokalizacja uzyskala {score:.0f}/100 dla profilu "
            f"{profile.emoji} {profile.name}. Nie spelnia kluczowych kryteriow."
        )

    def _extract_key_factors(self, scoring_result, level: VerdictLevel) -> List[str]:
        factors: List[str] = []

        # Warnings first
        for warning in (scoring_result.warnings or [])[:2]:
            factors.append(warning)

        if level == VerdictLevel.RECOMMENDED:
            factors.extend((scoring_result.strengths or [])[:3])
        elif level == VerdictLevel.CONDITIONAL:
            factors.extend((scoring_result.strengths or [])[:2])
            factors.extend((scoring_result.weaknesses or [])[:2])
        else:
            factors.extend((scoring_result.weaknesses or [])[:3])

        return factors[:5]
