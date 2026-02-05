"""
Profile konfiguracyjne dla systemu scoringu lokalizacji.

Każdy profil zawiera:
- weights: wagi kategorii (sumują się do 1.0, noise jako kara)
- radius_m: max promień per kategoria (twardy cutoff)
- decay_mode: tryb krzywej spadku per kategoria
- critical_caps: jeśli kategoria < threshold -> cap na total score
- thresholds: progi werdyktów (recommended/conditional/not_recommended)
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class DecayMode(str, Enum):
    """Tryby krzywej spadku użyteczności odległości."""
    DAILY = "daily"           # codzienność: sklepy, przystanki
    DESTINATION = "destination"  # cel: park, leisure, health, education
    BACKGROUND = "background"    # tło: zieleń/woda


class Category(str, Enum):
    """Stałe kategorie POI."""
    SHOPS = "shops"
    TRANSPORT = "transport"
    EDUCATION = "education"
    HEALTH = "health"
    NATURE_PLACE = "nature_place"      # park/garden/rezerwat - cel spaceru
    NATURE_BACKGROUND = "nature_background"  # forest/grass/water - tło
    LEISURE = "leisure"
    FOOD = "food"
    FINANCE = "finance"
    NOISE = "noise"           # kara za hałas
    CAR_ACCESS = "car_access"  # proxy dla dojazdu samochodem


# Domyślne przypisanie decay mode do kategorii
DEFAULT_DECAY_MODES: Dict[str, DecayMode] = {
    Category.SHOPS.value: DecayMode.DAILY,
    Category.TRANSPORT.value: DecayMode.DAILY,
    Category.EDUCATION.value: DecayMode.DESTINATION,
    Category.HEALTH.value: DecayMode.DESTINATION,
    Category.NATURE_PLACE.value: DecayMode.DESTINATION,
    Category.NATURE_BACKGROUND.value: DecayMode.BACKGROUND,
    Category.LEISURE.value: DecayMode.DESTINATION,
    Category.FOOD.value: DecayMode.DESTINATION,
    Category.FINANCE.value: DecayMode.DAILY,
    Category.CAR_ACCESS.value: DecayMode.DESTINATION,
}


def distance_score(distance_m: float, max_radius_m: float, mode: DecayMode) -> float:
    """
    Oblicza score użyteczności (0-100) na podstawie odległości i krzywej spadku.
    
    Args:
        distance_m: Odległość do POI w metrach
        max_radius_m: Maksymalny promień dla kategorii
        mode: Tryb krzywej spadku
    
    Returns:
        Score 0-100, gdzie 100 = pełna użyteczność
    """
    if distance_m >= max_radius_m:
        return 0.0
    
    ratio = distance_m / max_radius_m
    
    if mode == DecayMode.DAILY:
        # A) daily (codzienność: sklepy, przystanki)
        # 0–0.25*r: 100%, 0.25–0.5*r: 70%, 0.5–0.8*r: 40%, 0.8–1.0*r: 15%
        if ratio <= 0.25:
            return 100.0
        elif ratio <= 0.5:
            return 70.0
        elif ratio <= 0.8:
            return 40.0
        else:
            return 15.0
    
    elif mode == DecayMode.DESTINATION:
        # B) destination (cel: park, leisure)
        # 0–0.3*r: 100%, 0.3–0.6*r: 75%, 0.6–0.9*r: 45%, 0.9–1.0*r: 20%
        if ratio <= 0.3:
            return 100.0
        elif ratio <= 0.6:
            return 75.0
        elif ratio <= 0.9:
            return 45.0
        else:
            return 20.0
    
    elif mode == DecayMode.BACKGROUND:
        # C) background (tło: zieleń/woda)
        # 0–0.2*r: 100%, 0.2–0.4*r: 60%, 0.4–0.6*r: 25%, 0.6–1.0*r: 10%
        if ratio <= 0.2:
            return 100.0
        elif ratio <= 0.4:
            return 60.0
        elif ratio <= 0.6:
            return 25.0
        else:
            return 10.0
    
    return 0.0


@dataclass
class VerdictThresholds:
    """Progi dla werdyktu decyzyjnego."""
    recommended: int = 70     # Score >= tego = POLECANE
    conditional: int = 50     # Score >= tego = WARUNKOWO
    # Score < conditional = NIEPOLECANE
    
    def get_verdict(self, score: float) -> str:
        """Zwraca werdykt na podstawie score'u."""
        if score >= self.recommended:
            return 'recommended'
        elif score >= self.conditional:
            return 'conditional'
        return 'not_recommended'


@dataclass
class CriticalCap:
    """Konfiguracja critical cap dla kategorii."""
    threshold: float  # Jeśli score kategorii < threshold
    cap: float       # To total score max = cap


@dataclass
class ProfileConfig:
    """
    Pełna konfiguracja profilu scoringu.
    
    Atrybuty:
        key: Unikalny klucz profilu
        name: Nazwa wyświetlana
        description: Opis profilu
        emoji: Emoji dla UI
        weights: Wagi kategorii (float, suma dodatnich = 1.0, noise ujemne jako kara)
        radius_m: Max promień per kategoria
        decay_modes: Opcjonalne nadpisanie decay mode per kategoria
        critical_caps: Lista krytycznych ograniczeń (kategoria + threshold -> cap)
        thresholds: Progi werdyktu
        version: Wersja konfiguracji (do śledzenia zmian)
    """
    key: str
    name: str
    description: str
    emoji: str
    
    weights: Dict[str, float]
    radius_m: Dict[str, int]
    
    thresholds: VerdictThresholds = field(default_factory=VerdictThresholds)
    critical_caps: List[Tuple[str, CriticalCap]] = field(default_factory=list)
    decay_modes: Dict[str, DecayMode] = field(default_factory=dict)
    
    version: int = 1
    
    def get_decay_mode(self, category: str) -> DecayMode:
        """Zwraca decay mode dla kategorii."""
        return self.decay_modes.get(category, DEFAULT_DECAY_MODES.get(category, DecayMode.DESTINATION))
    
    def get_weight(self, category: str) -> float:
        """Zwraca wagę dla kategorii (0 jeśli brak)."""
        return self.weights.get(category, 0.0)
    
    def get_radius(self, category: str) -> int:
        """Zwraca promień dla kategorii (domyślnie 1000m)."""
        return self.radius_m.get(category, 1000)
    
    def apply_critical_caps(self, category_scores: Dict[str, float], total_score: float) -> float:
        """
        Aplikuje critical caps do total score.
        
        Args:
            category_scores: Scores per kategoria
            total_score: Obliczony total score
        
        Returns:
            Total score po aplikacji caps
        """
        for category, cap_config in self.critical_caps:
            cat_score = category_scores.get(category, 0)
            if cat_score < cap_config.threshold:
                total_score = min(total_score, cap_config.cap)
        return total_score
    
    def to_dict(self) -> dict:
        """Serializacja do słownika."""
        return {
            'key': self.key,
            'name': self.name,
            'description': self.description,
            'emoji': self.emoji,
            'weights': self.weights,
            'radius_m': self.radius_m,
            'thresholds': {
                'recommended': self.thresholds.recommended,
                'conditional': self.thresholds.conditional,
            },
            'critical_caps': [
                {'category': cat, 'threshold': cap.threshold, 'cap': cap.cap}
                for cat, cap in self.critical_caps
            ],
            'version': self.version,
        }


# ==============================================================================
# DEFINICJE PROFILI
# ==============================================================================


PROFILE_URBAN = ProfileConfig(
    key="urban",
    name="City Life",
    description="Wszystko pieszo, transport i jedzenie są krytyczne",
    emoji="🏙️",
    
    weights={
        Category.TRANSPORT.value: 0.25,
        Category.FOOD.value: 0.18,
        Category.SHOPS.value: 0.16,
        Category.LEISURE.value: 0.12,
        Category.HEALTH.value: 0.08,
        Category.FINANCE.value: 0.05,
        Category.NATURE_PLACE.value: 0.06,
        Category.NATURE_BACKGROUND.value: 0.03,
        Category.EDUCATION.value: 0.02,
        Category.NOISE.value: -0.03,  # Kara za hałas
    },
    
    radius_m={
        Category.TRANSPORT.value: 700,
        Category.FOOD.value: 800,
        Category.SHOPS.value: 600,
        Category.LEISURE.value: 800,
        Category.HEALTH.value: 1200,
        Category.FINANCE.value: 800,
        Category.NATURE_PLACE.value: 900,
        Category.NATURE_BACKGROUND.value: 450,
        Category.EDUCATION.value: 900,
    },
    
    thresholds=VerdictThresholds(recommended=65, conditional=45),
    
    critical_caps=[
        (Category.TRANSPORT.value, CriticalCap(threshold=35, cap=65)),
        (Category.FOOD.value, CriticalCap(threshold=25, cap=75)),
    ],
)


PROFILE_FAMILY = ProfileConfig(
    key="family",
    name="Rodzina z dziećmi",
    description="Szkoły/przedszkola, zdrowie i park mają priorytet",
    emoji="👨‍👩‍👧‍👦",
    
    weights={
        Category.EDUCATION.value: 0.25,
        Category.HEALTH.value: 0.16,
        Category.NATURE_PLACE.value: 0.16,
        Category.SHOPS.value: 0.14,
        Category.TRANSPORT.value: 0.10,
        Category.LEISURE.value: 0.08,  # place zabaw, boiska
        Category.NATURE_BACKGROUND.value: 0.06,
        Category.FOOD.value: 0.03,
        Category.FINANCE.value: 0.02,
        Category.NOISE.value: -0.04,  # Kara za hałas (mocniejsza dla rodziny)
    },
    
    radius_m={
        Category.EDUCATION.value: 1200,
        Category.HEALTH.value: 1500,
        Category.NATURE_PLACE.value: 900,
        Category.SHOPS.value: 700,
        Category.TRANSPORT.value: 900,
        Category.LEISURE.value: 700,
        Category.NATURE_BACKGROUND.value: 450,
        Category.FOOD.value: 700,
        Category.FINANCE.value: 900,
    },
    
    thresholds=VerdictThresholds(recommended=65, conditional=45),
    
    critical_caps=[
        (Category.EDUCATION.value, CriticalCap(threshold=35, cap=70)),
        (Category.NATURE_PLACE.value, CriticalCap(threshold=30, cap=75)),
    ],
)


PROFILE_QUIET_GREEN = ProfileConfig(
    key="quiet_green",
    name="Spokojnie i zielono",
    description="Cisza i zieleń, mniej usług",
    emoji="🌿",
    
    weights={
        Category.NATURE_PLACE.value: 0.22,
        Category.NATURE_BACKGROUND.value: 0.20,
        Category.NOISE.value: -0.12,  # Mocna kara za hałas!
        Category.SHOPS.value: 0.12,
        Category.TRANSPORT.value: 0.08,
        Category.HEALTH.value: 0.10,
        Category.LEISURE.value: 0.10,
        Category.FOOD.value: 0.05,
        Category.EDUCATION.value: 0.05,
        Category.FINANCE.value: 0.03,
    },
    
    radius_m={
        Category.NATURE_PLACE.value: 1200,  # Park może być "celem" spaceru
        Category.NATURE_BACKGROUND.value: 500,  # Tło ma być blisko
        Category.SHOPS.value: 900,
        Category.TRANSPORT.value: 1200,
        Category.HEALTH.value: 2000,
        Category.LEISURE.value: 1200,
        Category.FOOD.value: 1200,
        Category.EDUCATION.value: 1500,
        Category.FINANCE.value: 1000,
    },
    
    thresholds=VerdictThresholds(recommended=65, conditional=45),
    
    critical_caps=[
        # noise_score < 40 → total_cap = 60 (jak głośno, to nie przejdzie)
        (Category.NOISE.value, CriticalCap(threshold=40, cap=60)),
        (Category.NATURE_BACKGROUND.value, CriticalCap(threshold=35, cap=75)),
    ],
)


PROFILE_REMOTE_WORK = ProfileConfig(
    key="remote_work",
    name="Home Office",
    description="Cisza w dzień i podstawy w pobliżu",
    emoji="💻",
    
    weights={
        Category.NOISE.value: -0.10,  # Cisza ważna
        Category.SHOPS.value: 0.18,
        Category.HEALTH.value: 0.14,
        Category.NATURE_BACKGROUND.value: 0.12,
        Category.NATURE_PLACE.value: 0.10,
        Category.TRANSPORT.value: 0.10,
        Category.FOOD.value: 0.08,
        Category.LEISURE.value: 0.10,
        Category.EDUCATION.value: 0.03,
        Category.FINANCE.value: 0.05,
    },
    
    radius_m={
        Category.SHOPS.value: 700,
        Category.HEALTH.value: 1500,
        Category.NATURE_BACKGROUND.value: 450,
        Category.NATURE_PLACE.value: 900,
        Category.TRANSPORT.value: 1000,
        Category.FOOD.value: 900,
        Category.LEISURE.value: 900,
        Category.EDUCATION.value: 1200,
        Category.FINANCE.value: 800,
    },
    
    thresholds=VerdictThresholds(recommended=65, conditional=45),
    
    critical_caps=[
        (Category.NOISE.value, CriticalCap(threshold=45, cap=70)),
    ],
)


PROFILE_ACTIVE_SPORT = ProfileConfig(
    key="active_sport",
    name="Aktywny sportowo",
    description="Trasy, zieleń, obiekty sportowe",
    emoji="🏃",
    
    weights={
        Category.LEISURE.value: 0.22,
        Category.NATURE_PLACE.value: 0.18,
        Category.NATURE_BACKGROUND.value: 0.14,
        Category.SHOPS.value: 0.12,
        Category.HEALTH.value: 0.10,
        Category.TRANSPORT.value: 0.08,
        Category.FOOD.value: 0.06,
        Category.NOISE.value: -0.05,
        Category.FINANCE.value: 0.05,
        Category.EDUCATION.value: 0.0,
    },
    
    radius_m={
        Category.LEISURE.value: 1200,
        Category.NATURE_PLACE.value: 1200,
        Category.NATURE_BACKGROUND.value: 500,
        Category.SHOPS.value: 800,
        Category.TRANSPORT.value: 1000,
        Category.HEALTH.value: 1800,
        Category.FOOD.value: 900,
        Category.FINANCE.value: 1000,
        Category.EDUCATION.value: 1500,
    },
    
    thresholds=VerdictThresholds(recommended=65, conditional=45),
    
    critical_caps=[],  # Brak krytycznych
)


PROFILE_CAR_FIRST = ProfileConfig(
    key="car_first",
    name="Pod auto / przedmieścia",
    description="Transport publiczny ma niską wagę, liczy się dojazd i spokój",
    emoji="🚗",
    
    weights={
        Category.CAR_ACCESS.value: 0.20,
        Category.NOISE.value: -0.08,
        Category.SHOPS.value: 0.16,
        Category.HEALTH.value: 0.12,
        Category.NATURE_PLACE.value: 0.10,
        Category.NATURE_BACKGROUND.value: 0.10,
        Category.LEISURE.value: 0.10,
        Category.TRANSPORT.value: 0.06,
        Category.EDUCATION.value: 0.10,
        Category.FOOD.value: 0.04,
        Category.FINANCE.value: 0.02,
    },
    
    radius_m={
        Category.SHOPS.value: 1200,
        Category.HEALTH.value: 2500,
        Category.EDUCATION.value: 2000,
        Category.TRANSPORT.value: 1500,
        Category.NATURE_PLACE.value: 1500,
        Category.NATURE_BACKGROUND.value: 600,
        Category.LEISURE.value: 1500,
        Category.FOOD.value: 1200,
        Category.FINANCE.value: 1200,
        Category.CAR_ACCESS.value: 1000,
    },
    
    thresholds=VerdictThresholds(recommended=65, conditional=45),
    
    critical_caps=[
        (Category.CAR_ACCESS.value, CriticalCap(threshold=35, cap=70)),
    ],
)


PROFILE_INVESTOR = ProfileConfig(
    key="investor",
    name="Inwestor",
    description="Potencjał wynajmu: transport, infrastruktura, uczelnie",
    emoji="💰",
    
    weights={
        Category.TRANSPORT.value: 0.25,       # Kluczowe dla najemców
        Category.SHOPS.value: 0.18,           # Dostęp do sklepów ważny
        Category.EDUCATION.value: 0.15,       # Studenci = potencjalni najemcy
        Category.FOOD.value: 0.12,            # Gastronomia przyciąga
        Category.HEALTH.value: 0.08,
        Category.FINANCE.value: 0.08,         # Banki, bankomaty
        Category.LEISURE.value: 0.06,
        Category.NATURE_PLACE.value: 0.04,
        Category.NATURE_BACKGROUND.value: 0.02,
        Category.NOISE.value: -0.02,          # Hałas mniej ważny dla inwestora
    },
    
    radius_m={
        Category.TRANSPORT.value: 800,        # Transport musi być blisko
        Category.SHOPS.value: 700,
        Category.EDUCATION.value: 1500,       # Uczelnie mogą być dalej
        Category.FOOD.value: 900,
        Category.HEALTH.value: 1500,
        Category.FINANCE.value: 800,
        Category.LEISURE.value: 1000,
        Category.NATURE_PLACE.value: 1200,
        Category.NATURE_BACKGROUND.value: 500,
    },
    
    thresholds=VerdictThresholds(recommended=60, conditional=40),  # Niższe progi - inwestor patrzy na ROI
    
    critical_caps=[
        (Category.TRANSPORT.value, CriticalCap(threshold=30, cap=65)),  # Transport krytyczny
    ],
)


# ==============================================================================
# REGISTRY
# ==============================================================================


PROFILE_REGISTRY: Dict[str, ProfileConfig] = {
    "urban": PROFILE_URBAN,
    "family": PROFILE_FAMILY,
    "quiet_green": PROFILE_QUIET_GREEN,
    "remote_work": PROFILE_REMOTE_WORK,
    "active_sport": PROFILE_ACTIVE_SPORT,
    "car_first": PROFILE_CAR_FIRST,
    "investor": PROFILE_INVESTOR,
}

DEFAULT_PROFILE_KEY = "family"


def get_profile(profile_key: str) -> ProfileConfig:
    """
    Pobiera profil na podstawie klucza.
    
    Args:
        profile_key: Klucz profilu (np. 'urban', 'family')
    
    Returns:
        ProfileConfig (domyślnie family jeśli nieznany)
    """
    return PROFILE_REGISTRY.get(profile_key.lower(), PROFILE_REGISTRY[DEFAULT_PROFILE_KEY])


def get_all_profiles() -> List[ProfileConfig]:
    """Zwraca listę wszystkich profili."""
    return list(PROFILE_REGISTRY.values())


def get_profile_choices() -> List[tuple]:
    """Zwraca choices dla Django/DRF ChoiceField."""
    return [
        (p.key, f"{p.emoji} {p.name}")
        for p in PROFILE_REGISTRY.values()
    ]


def get_profiles_summary() -> List[dict]:
    """Zwraca podsumowanie profili (dla API)."""
    return [
        {
            'key': p.key,
            'name': p.name,
            'description': p.description,
            'emoji': p.emoji,
        }
        for p in PROFILE_REGISTRY.values()
    ]
