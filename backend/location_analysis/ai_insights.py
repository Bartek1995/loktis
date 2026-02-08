"""
AI-powered decision insights generator for location reports.

Uses Gemini to generate human-readable consequence descriptions
following the decision-first philosophy.

IMPORTANT: AI receives ONLY the AnalysisFactSheet (single source of truth).
It never sees raw POI data or intermediate calculations.
"""
import os
import json
import logging
from typing import Optional
from dataclasses import dataclass, field

import google.generativeai as genai

from .analysis_factsheet import AnalysisFactSheet

logger = logging.getLogger(__name__)


@dataclass
class DecisionInsight:
    """AI-generated text output based on factsheet."""
    summary: str
    quick_facts: list[str]  # Uses ✅/⚠ emoji correctly
    verification_checklist: list[str]  # Actionable 5-15 min checks
    recommendation_line: str = ""  # "Rekomendacja: Obejrzyj, jeśli..."
    target_audience: str = ""  # "Dla kogo pasuje / nie pasuje"
    disclaimer: str = ""  # Shown when data_quality_flags present
    
    # Legacy alias for backwards compatibility
    @property
    def attention_points(self) -> list[str]:
        return self.quick_facts


# System prompt - STRICT CONTRACT
# AI receives ONLY structured facts, generates ONLY structured text
SYSTEM_PROMPT = """Jesteś ekspertem od lokalizacji nieruchomości. Generujesz opisy dla PŁATNEGO raportu.

ŚCISŁE ZASADY:
1. Używasz TYLKO faktów z przekazanego JSON — żadnych wynalezionych danych
2. Nie zgadujesz nazw miejsc, ulic, sklepów — używasz tylko kategorii i odległości
3. Jeśli jest primary_blocker — MUSISZ go wymienić w "why this score"
4. Checklista = KONKRETNE czynności do zrobienia w 5-15 minut na miejscu

ZAKAZANE:
- Wymyślanie faktów spoza danych
- Sugerowanie zmiany profilu/ustawień
- Słowa: "punkty", "algorytm", "optymalizacja"
- Ogólniki typu "sprawdź okolicę"
- Kategoryczne stwierdzenia przy brakach: NIE "nie ma dróg" → TAK "brak danych o dojeździe"

JĘZYK PRZY BRAKACH DANYCH:
- Zamiast "nie ma X" → "brak potwierdzenia X w danych"
- Zamiast "brak parkingów" → "nie znaleziono parkingów w promieniu analizy"
- Jeśli data_quality_flags niepuste → używaj słów: "ograniczone dane", "niepełna weryfikacja"

FORMAT WYJŚCIOWY (JSON):
{
  "quick_facts": [
    "✅ [plus z positive_drivers, np. 'Sklepy w 55m']",
    "✅ [plus z positive_drivers]",
    "⚠ [ryzyko z negative_drivers lub noise]"
  ],
  "summary": "2-3 zdania. Jeśli jest primary_blocker, wyjaśnij DLACZEGO wpływa na wynik.",
  "verification_checklist": [
    "Sprawdź X w godzinach Y",
    "Zweryfikuj Z na miejscu",
    "Użyj narzędzia W do sprawdzenia..."
  ],
  "recommendation_line": "Rekomendacja: [Obejrzyj / Obejrzyj jeśli... / Rozważ ostrożnie]",
  "target_audience": "Pasuje dla... / Ryzykowne dla...",
  "disclaimer": "[TYLKO jeśli są data_quality_flags] Dane niepełne: ..."
}

ZASADY quick_facts:
- ✅ = plus z positive_drivers (max 2)
- ⚠ = ryzyko z negative_drivers lub noise (min 1)
- Zawsze używaj odległości jeśli jest w danych (np. "55m" nie "blisko")

ZASADY verification_checklist:
- "Stań przy oknie 2 min w szczycie 16-18"
- "Włącz Google Maps → natężenie ruchu o 8:00"
- "Sprawdź stronę świata okien"
- NIE: "upewnij się", "rozważ", "weź pod uwagę"

ZASADY recommendation_line:
- verdict=recommended → "Rekomendacja: Obejrzyj."
- verdict=conditional → "Rekomendacja: Obejrzyj, jeśli [warunek z primary_blocker]."
- verdict=not_recommended → "Rekomendacja: Rozważ ostrożnie. [przyczyna z primary_blocker]."

ZASADY disclaimer:
- TYLKO jeśli data_quality_flags niepuste
- Wymień konkretne braki, np. "Dane cenowe wyglądają na błędne"
"""


class AIInsightGenerator:
    """Generates human-readable decision insights using Gemini."""
    
    def __init__(self):
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            logger.warning("GEMINI_API_KEY not set, AI insights will be unavailable")
            self.model = None
            return
            
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name='gemini-2.0-flash',
            generation_config={
                'temperature': 0.6,  # Lower for more consistent output
                'max_output_tokens': 800,
                'response_mime_type': 'application/json',
            },
            system_instruction=SYSTEM_PROMPT
        )
    
    def generate_from_factsheet(
        self,
        factsheet: AnalysisFactSheet,
    ) -> Optional[DecisionInsight]:
        """
        Generate AI insights from AnalysisFactSheet.
        
        This is the ONLY method that should be used.
        AI sees ONLY the factsheet, never raw data.
        """
        if not self.model:
            return None
        
        try:
            # Convert factsheet to AI-safe JSON
            prompt_data = factsheet.to_ai_prompt_json()
            
            prompt = f"""
Wygeneruj insights dla tego raportu lokalizacyjnego.

DANE (to jest JEDYNE źródło prawdy - nie wymyślaj innych faktów):
{json.dumps(prompt_data, ensure_ascii=False, indent=2)}
"""
            response = self.model.generate_content(prompt)
            
            # Parse JSON response
            data = json.loads(response.text)
            
            return DecisionInsight(
                summary=data.get('summary', ''),
                quick_facts=data.get('quick_facts', [])[:3],
                verification_checklist=data.get('verification_checklist', [])[:3],
                recommendation_line=data.get('recommendation_line', ''),
                target_audience=data.get('target_audience', ''),
                disclaimer=data.get('disclaimer', ''),
            )
            
        except Exception as e:
            logger.error(f"Failed to generate AI insights: {e}")
            return None
    
    # Legacy method for backwards compatibility
    def generate_insights(
        self,
        profile_name: str,
        final_score: int,
        verdict: str,
        strengths: list[str],
        limitations: list[str],
        noise_level: str = None,
    ) -> Optional[DecisionInsight]:
        """
        Legacy method - converts old-style params to factsheet.
        DEPRECATED: Use generate_from_factsheet() instead.
        """
        from .analysis_factsheet import CategoryDriver
        
        # Build minimal factsheet from legacy params
        factsheet = AnalysisFactSheet(
            profile_key='unknown',
            profile_name=profile_name,
            profile_emoji='👤',
            final_score=final_score,
            verdict=verdict,
            verdict_label={'recommended': 'Polecane', 'conditional': 'Polecane z kompromisem', 'not_recommended': 'Nie polecane'}.get(verdict, verdict),
            confidence=70,
            positive_drivers=[
                CategoryDriver(category=s.lower().replace(' ', '_'), category_name=s, grade='good', detail=s)
                for s in (strengths or [])[:3]
            ],
            negative_drivers=[
                CategoryDriver(category=l.lower().replace(' ', '_'), category_name=l, grade='poor', detail=l)
                for l in (limitations or [])[:2]
            ],
            noise_level=noise_level or 'unknown',
            noise_source='legacy',
        )
        
        # Determine primary blocker
        if noise_level in ('high', 'extreme'):
            factsheet.primary_blocker = 'noise'
            factsheet.primary_blocker_detail = f"Poziom hałasu: {noise_level}"
        elif factsheet.negative_drivers:
            factsheet.primary_blocker = factsheet.negative_drivers[0].category
            factsheet.primary_blocker_detail = factsheet.negative_drivers[0].detail
        
        return self.generate_from_factsheet(factsheet)


# Singleton instance
_generator: Optional[AIInsightGenerator] = None


def get_ai_insight_generator() -> AIInsightGenerator:
    """Get singleton instance of AI insight generator."""
    global _generator
    if _generator is None:
        _generator = AIInsightGenerator()
    return _generator


def generate_insights_from_factsheet(
    factsheet: AnalysisFactSheet,
) -> Optional[DecisionInsight]:
    """
    Generate AI insights from AnalysisFactSheet.
    This is the PREFERRED method.
    """
    generator = get_ai_insight_generator()
    return generator.generate_from_factsheet(factsheet)


def generate_decision_insights(
    profile_name: str,
    final_score: int,
    verdict: str,
    strengths: list[str],
    limitations: list[str],
    noise_level: str = None,
) -> Optional[DecisionInsight]:
    """
    Legacy convenience function.
    DEPRECATED: Use generate_insights_from_factsheet() instead.
    """
    generator = get_ai_insight_generator()
    return generator.generate_insights(
        profile_name=profile_name,
        final_score=final_score,
        verdict=verdict,
        strengths=strengths,
        limitations=limitations,
        noise_level=noise_level,
    )
