"""
AI-powered decision insights generator for location reports.

Uses configurable AI provider (Gemini / Ollama / Off) to generate
human-readable consequence descriptions following the decision-first philosophy.

IMPORTANT: AI receives ONLY the AnalysisFactSheet (single source of truth).
It never sees raw POI data or intermediate calculations.
"""
import os
import json
import hashlib
import logging
from typing import Optional, Dict
from dataclasses import dataclass, field

from .analysis_factsheet import AnalysisFactSheet
from .ai_client import AIClient, AIClientError, create_ai_client

logger = logging.getLogger(__name__)

# Prompt version — bump when changing SYSTEM_PROMPT
PROMPT_VERSION = "v2"


@dataclass
class DecisionInsight:
    """AI-generated text output based on factsheet."""
    summary: str
    # tldr_pros/tldr_cons removed - no longer displayed in frontend
    check_on_site: list[str] = field(default_factory=list)  # Exactly 3 actionable checks
    why_not_higher: str = ""  # Why score isn't higher (from primary_blocker)
    
    # Legacy fields for backwards compatibility
    recommendation_line: str = ""
    target_audience: str = ""
    disclaimer: str = ""
    
    @property
    def quick_facts(self) -> list[str]:
        """Legacy: Now returns empty list as pros/cons are removed."""
        return []
    
    @property
    def verification_checklist(self) -> list[str]:
        """Legacy alias."""
        return self.check_on_site
    
    # Legacy alias
    @property
    def attention_points(self) -> list[str]:
        return self.quick_facts
    
    def to_dict(self) -> dict:
        """Serialize to dict for API response. Includes computed properties."""
        return {
            'summary': self.summary,
            'check_on_site': self.check_on_site,
            'why_not_higher': self.why_not_higher,
            # Legacy fields for backwards compatibility with frontend
            'quick_facts': self.quick_facts,
            'verification_checklist': self.verification_checklist,
            'recommendation_line': self.recommendation_line,
            'target_audience': self.target_audience,
            'disclaimer': self.disclaimer,
        }


# System prompt - STRICT CONTRACT
# AI receives ONLY structured facts, generates ONLY structured text
SYSTEM_PROMPT = """Jesteś ekspertem od lokalizacji nieruchomości. Generujesz opisy dla PŁATNEGO raportu.

TWOJE JEDYNE ZADANIE: Opisz fakty z JSON. NIE WYMYŚLAJ niczego.

FORMAT WYJŚCIOWY (ścisły JSON):
{
  "summary": "1-2 zdania podsumowania",
  "check_on_site": ["...", "...", "..."],
  "why_not_higher": "Dlaczego ocena nie jest wyższa (z primary_blocker)"
}

ŚCISŁE WYMOGI:
- check_on_site: DOKŁADNIE 3 elementy, konkretne czynności 5-15 min
- Każdy element MUSI mieć podstawę w przekazanych danych

SKĄD BRAĆ TREŚĆ:
- why_not_higher → z verdict_reason lub primary_blocker_detail
- check_on_site → z kategorii które są słabe lub mają penalties

ZAKAZANE FRAZY (odrzucenie jeśli użyte):
- "porównaj cenę z podobnymi ofertami"
- "sprawdź koszty eksploatacji"
- "zweryfikuj dokumentację prawną"
- "sprawdź dokumentację"
- "obejrzyj z kimś"
- "porozmawiaj z sąsiadami"
- "weź pod uwagę"
- "upewnij się"

ZASADY HAŁASU:
- Jeśli noise.source ≠ "measurement" → NIE WOLNO "poziom hałasu jest...", "okolica jest spokojna"
- ZAMIAST → "Ryzyko podwyższonego hałasu (do weryfikacji)", "Spokój wymaga weryfikacji"

ZASADY DRÓG:
- NIE WOLNO "ruchliwe drogi" — brak danych o natężeniu
- ZAMIAST → "bliskość dróg i infrastruktury transportowej"

ZASADY check_on_site:
- KONKRETNE: "Stań przy oknie 2 min w szczycie 16-18"
- KONKRETNE: "Włącz Google Maps → natężenie ruchu o 8:00"
- KONKRETNE: "Sprawdź nasłonecznienie o 15:00"
- NIE: "sprawdź okolicę", "oceń atmosferę"

SPÓJNOŚĆ:
- Jeśli data_reason puste → NIE pisz "dane niepełne"
- Jeśli penalties.roads_penalty >= 6 → NIE pisz "spokojna/cicha okolica"
- Jeśli primary_blocker == "roads" → why_not_higher MUSI wspomnieć drogi

Zwróć TYLKO JSON, bez żadnych dodatkowych znaków, komentarzy ani markdown.
Jeśli nie potrafisz spełnić formatu, zwróć dokładnie: {}
"""


class AIInsightGenerator:
    """Generates human-readable decision insights using configurable AI provider."""
    
    def __init__(self):
        from .app_config import get_config
        config = get_config()
        
        self.client: Optional[AIClient] = create_ai_client(
            provider=config.ai_provider,
            gemini_api_key=config.gemini_api_key,
            gemini_model=config.ai_model_gemini,
            gemini_temperature=config.ai_temperature_gemini,
            ollama_base_url=config.ollama_base_url,
            ollama_model=config.ai_model_ollama,
            ollama_temperature=config.ai_temperature_ollama,
        )
        
        # In-memory AI response cache: hash(prompt+model) -> DecisionInsight
        self._cache: Dict[str, DecisionInsight] = {}
    
    # Blacklist of generic phrases that indicate AI is confabulating
    BLACKLIST_PHRASES = [
        "porównaj cenę",
        "sprawdź koszty eksploatacji",
        "zweryfikuj dokumentację",
        "sprawdź dokumentację",
        "obejrzyj z kimś",
        "porozmawiaj z sąsiadami",
        "weź pod uwagę",
        "upewnij się",
        "sprawdź okolicę",
        "oceń atmosferę",
        "ruchliwe drogi",
        "ruchliwych dróg",
    ]
    
    def _cache_key(self, prompt_data: dict) -> str:
        """Generate cache key from prompt data + model name."""
        model_name = self.client.model_name if self.client else "off"
        content = json.dumps(prompt_data, sort_keys=True, ensure_ascii=False) + model_name + PROMPT_VERSION
        return hashlib.md5(content.encode()).hexdigest()
    
    def generate_from_factsheet(
        self,
        factsheet: AnalysisFactSheet,
        trace_ctx: 'AnalysisTraceContext | None' = None,
    ) -> Optional[DecisionInsight]:
        """
        Generate AI insights from AnalysisFactSheet with validation.
        
        Returns validated AI output or deterministic fallback.
        """
        from .diagnostics import get_diag_logger, AnalysisTraceContext
        ctx = trace_ctx or AnalysisTraceContext()
        slog = get_diag_logger(__name__, ctx)

        # Always have fallback ready
        fallback = self._generate_fallback_tldr(factsheet)
        
        if not self.client:
            slog.degraded(kind="DEGRADED_PROVIDER", provider="ai", reason="AI provider is OFF, using fallback", stage="ai")
            return fallback
        
        provider_name = self.client.provider_name
        model_name = self.client.model_name
        
        try:
            # Convert factsheet to AI-safe JSON
            prompt_data = factsheet.to_ai_prompt_json()
            
            # Check cache first
            cache_key = self._cache_key(prompt_data)
            if cache_key in self._cache:
                slog.info(
                    stage="ai", provider=provider_name, op="cache_hit",
                    meta={"model": model_name, "prompt_version": PROMPT_VERSION, "ai_cache_used": True}
                )
                return self._cache[cache_key]
            
            prompt = f"""
Wygeneruj insights dla tego raportu lokalizacyjnego.

DANE (to jest JEDYNE źródło prawdy - nie wymyślaj innych faktów):
{json.dumps(prompt_data, ensure_ascii=False, indent=2)}
"""
            token = slog.req_start(provider=provider_name, op="generate_json", stage="ai")
            data = self.client.generate_json(SYSTEM_PROMPT, prompt)
            slog.req_end(
                provider=provider_name, op="generate_json", stage="ai", status="ok",
                request_token=token,
                meta={"model": model_name, "prompt_version": PROMPT_VERSION, "ai_cache_used": False}
            )
            
            # Handle empty response from local model
            if not data:
                slog.warning(stage="ai", provider=provider_name, op="empty_response", message="AI returned empty JSON, using fallback")
                return fallback
            
            # POST-FILTER: Sanitize declarative noise/quiet claims
            if factsheet.noise_source != "measurement":
                data = self._sanitize_noise_claims(data)
            
            # VALIDATE AI output
            validation_errors = self._validate_ai_output(data, factsheet)
            if validation_errors:
                slog.warning(
                    stage="ai", provider=provider_name, op="validation", status="failed",
                    error_class="logic", message="Using fallback",
                    meta={"errors": validation_errors, "model": model_name}
                )
                return fallback
            
            result = DecisionInsight(
                summary=data.get('summary', fallback.summary),
                check_on_site=data.get('check_on_site', fallback.check_on_site)[:3],
                why_not_higher=data.get('why_not_higher', fallback.why_not_higher),
            )
            
            # Cache successful result
            self._cache[cache_key] = result
            
            return result
            
        except AIClientError as e:
            slog.error(
                stage="ai", provider=provider_name, op="generate_json",
                message=str(e), exc="AIClientError", error_class="runtime",
                hint=f"{provider_name} failed, using fallback"
            )
            return fallback
        except Exception as e:
            slog.error(
                stage="ai", provider=provider_name, op="generate_json",
                message=str(e), exc=type(e).__name__, error_class="runtime",
                hint=f"{provider_name} call failed, using deterministic fallback"
            )
            return fallback
    
    def _validate_ai_output(self, data: dict, factsheet: AnalysisFactSheet) -> list[str]:
        """
        Validate AI output against strict rules.
        Returns list of errors (empty = valid).
        """
        errors = []
        
        # 1. SHAPE VALIDATION - only check_on_site now
        check_on_site = data.get('check_on_site', [])
        
        if len(check_on_site) != 3:
            errors.append(f"check_on_site has {len(check_on_site)} elements, expected 3")
        
        # 2. LENGTH VALIDATION (max 120 chars per element)
        for i, item in enumerate(check_on_site):
            if isinstance(item, str) and len(item) > 120:
                errors.append(f"Element too long ({len(item)} chars): {item[:50]}...")
        
        # 3. BLACKLIST CHECK
        all_text = json.dumps(data, ensure_ascii=False).lower()
        for phrase in self.BLACKLIST_PHRASES:
            if phrase.lower() in all_text:
                errors.append(f"Blacklisted phrase found: '{phrase}'")
        
        # 4. CONSISTENCY CHECKS
        # If data_reason is empty, should not mention "dane niepełne"
        if not factsheet.data_reason and "dane niepełne" in all_text:
            errors.append("Mentioned 'dane niepełne' but data_reason is empty")
        
        # If roads_penalty >= 6, should not say "spokojna" or "cicha"
        roads_penalty = factsheet.penalties.get('roads_penalty', 0) if factsheet.penalties else 0
        if roads_penalty >= 6:
            if "spokojna" in all_text or "cicha" in all_text:
                errors.append("Said 'spokojna/cicha' but roads_penalty >= 6")
        
        # If primary_blocker == "roads", why_not_higher must mention roads
        why_not_higher = data.get('why_not_higher', '').lower()
        if factsheet.primary_blocker == "roads":
            road_words = ['drog', 'drogi', 'dróg', 'transport', 'kolej', 'szyn', 'tory']
            if not any(word in why_not_higher for word in road_words):
                errors.append("primary_blocker is 'roads' but why_not_higher doesn't mention roads")
        
        return errors
    
    def _generate_fallback_tldr(self, factsheet: AnalysisFactSheet) -> DecisionInsight:
        """
        Generate deterministic fallback from factsheet data.
        Used when AI fails or is unavailable.
        """
        # Summary
        summary = f"{factsheet.verdict_label}."
        if factsheet.verdict_reason:
            summary += f" {factsheet.verdict_reason}"
        
        # Why not higher
        why_not_higher = factsheet.primary_blocker_detail or factsheet.verdict_reason or ""
        
        # Check on site - data-driven, actionable
        check_on_site = [
            "Stań przy oknie na 2 minuty w szczycie komunikacyjnym (16-18)",
            "Sprawdź nasłonecznienie mieszkania o różnych porach dnia",
            "Włącz Google Maps i sprawdź natężenie ruchu o 8:00 i 17:00",
        ]
        
        return DecisionInsight(
            summary=summary,
            check_on_site=check_on_site,
            why_not_higher=why_not_higher,
        )
    
    def _sanitize_noise_claims(self, data: dict) -> dict:
        """
        Post-filter to replace declarative noise/quiet statements with conditional forms.
        Backup for when AI ignores prompt rules.
        """
        import re
        
        # Patterns to replace (case insensitive)
        replacements = [
            # Noise level declaratives
            (r'[Pp]oziom hałasu jest\s+(niski|umiarkowany|wysoki|bardzo niski)',
             'Ryzyko podwyższonego hałasu (wymagana weryfikacja na miejscu)'),
            (r'[Hh]ałas\s+jest\s+(niski|umiarkowany|wysoki)',
             'Poziom hałasu wymaga weryfikacji na miejscu'),
            # Quiet/calm declaratives  
            (r'[Oo]kolica jest\s+(spokojna|cicha|bardzo cicha)',
             'Spokój wymaga weryfikacji na miejscu'),
            (r'[Cc]icha,?\s*(zielona\s+)?okolica',
             'Spokój i zieleń wymagają weryfikacji'),
            # Busy roads (no traffic data)
            (r'[Rr]uchliw(ych|e|ego|ą)\s+dró(g|ż)',
             'dróg i infrastruktury transportowej'),
            (r'[Bb]liskość ruchliwych',
             'Bliskość'),
        ]
        
        def replace_in_text(text: str) -> str:
            if not isinstance(text, str):
                return text
            for pattern, replacement in replacements:
                text = re.sub(pattern, replacement, text)
            return text
        
        # Apply to all text fields
        if 'summary' in data:
            data['summary'] = replace_in_text(data['summary'])
        
        if 'quick_facts' in data:
            data['quick_facts'] = [replace_in_text(f) for f in data['quick_facts']]
        
        if 'recommendation_line' in data:
            data['recommendation_line'] = replace_in_text(data['recommendation_line'])
        
        if 'target_audience' in data:
            data['target_audience'] = replace_in_text(data['target_audience'])
        
        if 'disclaimer' in data:
            data['disclaimer'] = replace_in_text(data['disclaimer'])
        
        return data
    
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
