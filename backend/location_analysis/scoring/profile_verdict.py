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
    
    # New: compromise thresholds for specific profiles
    COMPROMISE_THRESHOLDS = {
        'family': {
            'noise_penalty': 8,   # If noise penalty > 8, it's a compromise
            'roads_penalty': 10,  # If roads penalty > 10, it's a compromise
        },
        'car_first': {
            'noise_penalty': 5,
        },
    }

    def generate(self, scoring_result, profile: ProfileConfig) -> Verdict:
        score = scoring_result.total_score
        thresholds = profile.thresholds

        level = self._level_from_score(score, thresholds)
        
        # CRITICAL: If any must-have (critical cap) failed, downgrade verdict
        # A "Polecane" with unmet critical requirements breaks user trust
        critical_caps = getattr(scoring_result, 'critical_caps_applied', [])
        if critical_caps and level == VerdictLevel.RECOMMENDED:
            level = VerdictLevel.CONDITIONAL
        
        # Detect compromise situations (e.g., Family + high traffic)
        compromise_reason = self._detect_compromise(scoring_result, profile)
        
        config = self.VERDICT_CONFIG[level]
        
        # Override label if compromise detected on RECOMMENDED verdict
        label = config['label']
        if compromise_reason and level == VerdictLevel.RECOMMENDED:
            label = f"Polecane z kompromisem ({compromise_reason})"

        confidence = self._calculate_confidence(score, thresholds, critical_caps)
        profile_match = self._determine_profile_match(score, thresholds)
        explanation = self._generate_explanation(level, score, profile, critical_caps, compromise_reason)
        key_factors = self._extract_key_factors(scoring_result, level)

        return Verdict(
            level=level,
            label=label,
            emoji=config['emoji'],
            explanation=explanation,
            key_factors=key_factors,
            score=score,
            confidence=confidence,
            persona_match=profile_match,
        )
    
    def _detect_compromise(self, scoring_result, profile: ProfileConfig) -> str:
        """Detect if there's a significant compromise for this profile."""
        profile_key = profile.key
        thresholds = self.COMPROMISE_THRESHOLDS.get(profile_key, {})
        
        if not thresholds:
            return None
        
        # Check noise penalty
        noise_penalty = getattr(scoring_result, 'noise_penalty', 0)
        noise_threshold = thresholds.get('noise_penalty', 999)
        if noise_penalty > noise_threshold:
            return "hałas"
        
        # Check roads penalty
        roads_penalty = getattr(scoring_result, 'roads_penalty', 0)
        roads_threshold = thresholds.get('roads_penalty', 999)
        if roads_penalty > roads_threshold:
            return "ruch uliczny"
        
        return None

    def _level_from_score(self, score: float, thresholds: VerdictThresholds) -> VerdictLevel:
        if score >= thresholds.recommended:
            return VerdictLevel.RECOMMENDED
        if score >= thresholds.conditional:
            return VerdictLevel.CONDITIONAL
        return VerdictLevel.NOT_RECOMMENDED

    def _calculate_confidence(self, score: float, thresholds: VerdictThresholds, critical_caps: List[str] = None) -> int:
        """Calculate confidence, reduced when critical caps are applied."""
        dist_to_recommended = abs(score - thresholds.recommended)
        dist_to_conditional = abs(score - thresholds.conditional)
        min_distance = min(dist_to_recommended, dist_to_conditional)

        if min_distance >= 20:
            base_confidence = 90
        elif min_distance >= 15:
            base_confidence = 80
        elif min_distance >= 10:
            base_confidence = 70
        elif min_distance >= 5:
            base_confidence = 55
        else:
            base_confidence = 45
        
        # Reduce confidence when critical caps are applied (must-have unmet)
        if critical_caps:
            penalty = min(len(critical_caps) * 15, 30)  # Max -30% for caps
            base_confidence = max(35, base_confidence - penalty)
        
        return base_confidence

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

    def _generate_explanation(self, level: VerdictLevel, score: float, profile: ProfileConfig, critical_caps: List[str] = None, compromise_reason: str = None) -> str:
        """Generate human-readable explanation, accounting for caps and compromises."""
        cap_note = ""
        if critical_caps:
            cap_note = " Niektóre kluczowe kryteria profilu nie zostały w pełni spełnione."
        
        compromise_note = ""
        if compromise_reason:
            compromise_note = f" Zwróć uwagę na {compromise_reason} – może wymagać weryfikacji w terenie."
        
        if level == VerdictLevel.RECOMMENDED:
            base = (
                f"Lokalizacja uzyskała {score:.0f}/100 dla profilu "
                f"{profile.emoji} {profile.name}. Spełnia kluczowe kryteria "
                f"i jest rekomendowana."
            )
            return base + compromise_note
        if level == VerdictLevel.CONDITIONAL:
            base = (
                f"Lokalizacja uzyskała {score:.0f}/100 dla profilu "
                f"{profile.emoji} {profile.name}. Wymaga kompromisów "
                f"do rozważenia."
            )
            return base + cap_note
        return (
            f"Lokalizacja uzyskała {score:.0f}/100 dla profilu "
            f"{profile.emoji} {profile.name}. Nie spełnia kluczowych kryteriów."
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
