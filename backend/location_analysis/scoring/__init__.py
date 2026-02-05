"""
Scoring package - Silnik scoringu z dynamicznymi wagami.
"""
from .engine import ScoringEngine, ScoringResult
from .verdict import VerdictGenerator, Verdict, VerdictLevel
from .profiles import (
    ProfileConfig, 
    get_profile, 
    get_all_profiles, 
    get_profiles_summary,
    Category,
    DecayMode,
    distance_score,
)
from .profile_engine import ProfileScoringEngine, create_scoring_engine

__all__ = [
    'ScoringEngine',
    'ScoringResult',
    'VerdictGenerator',
    'Verdict',
    'VerdictLevel',
    # Nowy system profili
    'ProfileConfig',
    'get_profile',
    'get_all_profiles',
    'get_profiles_summary',
    'Category',
    'DecayMode',
    'distance_score',
    'ProfileScoringEngine',
    'create_scoring_engine',
]
