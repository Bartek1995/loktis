"""
AI Client - abstrakcja providera AI (Gemini / Ollama / Off).

Interfejs: AIClient.generate_json(system_prompt, user_prompt) -> dict
Dwie implementacje: GeminiClient, OllamaClient.
"""
import json
import re
import logging
import requests
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class AIClient(ABC):
    """Interface for AI providers."""
    
    @abstractmethod
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        """
        Generate a JSON response from system + user prompts.
        
        Returns:
            dict: Parsed JSON response
            
        Raises:
            AIClientError: If generation fails after retries
        """
        ...
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier: 'gemini', 'ollama'."""
        ...
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model name used for generation."""
        ...


class AIClientError(Exception):
    """Raised when AI client fails to generate valid response."""
    pass


class GeminiClient(AIClient):
    """
    Google Gemini client.
    Uses google.generativeai with response_mime_type='application/json'.
    """
    
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash", temperature: float = 0.6):
        import google.generativeai as genai
        
        self._model_name = model_name
        self._temperature = temperature
        
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                'temperature': temperature,
                'max_output_tokens': 800,
                'response_mime_type': 'application/json',
            },
        )
    
    @property
    def provider_name(self) -> str:
        return "gemini"
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Generate JSON using Gemini with native JSON mode."""
        # Gemini uses system_instruction at model level, but we pass it inline
        # for flexibility (different prompts per call)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        response = self._model.generate_content(full_prompt)
        return json.loads(response.text)


class OllamaClient(AIClient):
    """
    Local Ollama client.
    Uses POST /api/chat with JSON extraction and retry logic.
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model_name: str = "qwen2.5:7b-instruct",
        temperature: float = 0.3,
        timeout: int = 120,
    ):
        self._base_url = base_url.rstrip('/')
        self._model_name = model_name
        self._temperature = temperature
        self._timeout = timeout
    
    @property
    def provider_name(self) -> str:
        return "ollama"
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict:
        """
        Generate JSON using local Ollama.
        
        Strategy:
        1. Send system + user prompt via /api/chat
        2. Try json.loads() on raw response
        3. If fail: extract first {...} block with regex
        4. If still fail: retry 1x with "ZWRÓĆ TYLKO JSON" appended
        """
        # Append strict JSON instruction for local models
        enhanced_system = (
            system_prompt + 
            "\n\nZwróć TYLKO JSON, bez żadnych dodatkowych znaków, komentarzy ani markdown."
            "\nJeśli nie potrafisz spełnić formatu, zwróć dokładnie: {}"
        )
        
        # Attempt 1
        raw_text = self._call_ollama(enhanced_system, user_prompt)
        result = self._extract_json(raw_text)
        if result is not None:
            return result
        
        # Attempt 2: retry with explicit JSON demand
        logger.warning("Ollama: first attempt failed JSON parse, retrying with strict prompt")
        retry_prompt = user_prompt + "\n\nUWAGA: ZWRÓĆ TYLKO CZYSTY JSON. Żadnego markdown, żadnych komentarzy."
        raw_text = self._call_ollama(enhanced_system, retry_prompt)
        result = self._extract_json(raw_text)
        if result is not None:
            return result
        
        raise AIClientError(f"Ollama failed to produce valid JSON after 2 attempts. Last response: {raw_text[:200]}")
    
    def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Send chat request to Ollama API."""
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": self._temperature,
                "num_predict": 1024,
            },
            "format": "json",  # Request JSON format from Ollama
        }
        
        try:
            response = requests.post(url, json=payload, timeout=self._timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "")
        except requests.exceptions.ConnectionError:
            raise AIClientError(f"Cannot connect to Ollama at {self._base_url}. Is it running?")
        except requests.exceptions.Timeout:
            raise AIClientError(f"Ollama request timed out after {self._timeout}s")
        except requests.exceptions.HTTPError as e:
            raise AIClientError(f"Ollama HTTP error: {e}")
    
    def _extract_json(self, text: str) -> Optional[dict]:
        """
        Try to extract JSON from text response.
        
        1. Direct json.loads()
        2. Extract first {...} block
        3. Return None if both fail
        """
        if not text or not text.strip():
            return {}
        
        text = text.strip()
        
        # Strategy 1: direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: extract first JSON object
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        
        return None


def create_ai_client(
    provider: str = "off",
    gemini_api_key: str = "",
    gemini_model: str = "gemini-2.0-flash",
    gemini_temperature: float = 0.6,
    ollama_base_url: str = "http://localhost:11434",
    ollama_model: str = "qwen2.5:7b-instruct",
    ollama_temperature: float = 0.3,
) -> Optional[AIClient]:
    """
    Factory: create AI client based on provider setting.
    
    Returns None if provider is 'off'.
    """
    if provider == "off":
        logger.info("AI provider is OFF, insights will use deterministic fallback")
        return None
    
    if provider == "gemini":
        if not gemini_api_key:
            logger.warning("AI_PROVIDER=gemini but GEMINI_API_KEY not set, falling back to off")
            return None
        logger.info("AI provider: Gemini (%s)", gemini_model)
        return GeminiClient(
            api_key=gemini_api_key,
            model_name=gemini_model,
            temperature=gemini_temperature,
        )
    
    if provider == "ollama":
        logger.info("AI provider: Ollama (%s @ %s)", ollama_model, ollama_base_url)
        return OllamaClient(
            base_url=ollama_base_url,
            model_name=ollama_model,
            temperature=ollama_temperature,
        )
    
    logger.warning("Unknown AI_PROVIDER='%s', defaulting to off", provider)
    return None
