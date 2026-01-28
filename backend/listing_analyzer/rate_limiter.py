"""
Rate limiting dla endpointów.
"""
import time
import threading
from typing import Dict, Tuple
from functools import wraps

from rest_framework.response import Response
from rest_framework import status


class RateLimiter:
    """
    Prosty rate limiter oparty na sliding window.
    Identyfikuje klientów po IP.
    """
    
    def __init__(
        self,
        requests_per_minute: int = 10,
        requests_per_hour: int = 60,
        cleanup_interval: int = 300
    ):
        """
        Args:
            requests_per_minute: Limit requestów na minutę
            requests_per_hour: Limit requestów na godzinę
            cleanup_interval: Jak często czyścić stare dane (sekundy)
        """
        self._minute_limit = requests_per_minute
        self._hour_limit = requests_per_hour
        self._cleanup_interval = cleanup_interval
        
        # {ip: [timestamp1, timestamp2, ...]}
        self._requests: Dict[str, list] = {}
        self._lock = threading.RLock()
        self._last_cleanup = time.time()
    
    def is_allowed(self, client_id: str) -> Tuple[bool, str]:
        """
        Sprawdza czy request jest dozwolony.
        
        Args:
            client_id: Identyfikator klienta (np. IP)
        
        Returns:
            (is_allowed, error_message)
        """
        now = time.time()
        
        with self._lock:
            # Cleanup jeśli trzeba
            if now - self._last_cleanup > self._cleanup_interval:
                self._cleanup(now)
                self._last_cleanup = now
            
            # Pobierz historię requestów klienta
            if client_id not in self._requests:
                self._requests[client_id] = []
            
            timestamps = self._requests[client_id]
            
            # Usuń stare requesty (starsze niż 1h)
            hour_ago = now - 3600
            timestamps[:] = [t for t in timestamps if t > hour_ago]
            
            # Sprawdź limity
            minute_ago = now - 60
            requests_last_minute = sum(1 for t in timestamps if t > minute_ago)
            requests_last_hour = len(timestamps)
            
            if requests_last_minute >= self._minute_limit:
                return False, f"Zbyt wiele requestów. Limit: {self._minute_limit}/minutę. Poczekaj chwilę."
            
            if requests_last_hour >= self._hour_limit:
                return False, f"Przekroczono limit godzinowy ({self._hour_limit} analiz/godzinę)."
            
            # Zapisz nowy request
            timestamps.append(now)
            
            return True, ""
    
    def _cleanup(self, now: float) -> None:
        """Usuwa stare dane."""
        hour_ago = now - 3600
        
        empty_clients = []
        for client_id, timestamps in self._requests.items():
            timestamps[:] = [t for t in timestamps if t > hour_ago]
            if not timestamps:
                empty_clients.append(client_id)
        
        for client_id in empty_clients:
            del self._requests[client_id]
    
    def get_client_ip(self, request) -> str:
        """Wyciąga IP klienta z requesta Django."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')


# Globalna instancja
rate_limiter = RateLimiter(
    requests_per_minute=5,
    requests_per_hour=30
)


def rate_limit(limiter: RateLimiter = None):
    """
    Dekorator do rate-limitowania widoków DRF.
    
    Usage:
        @rate_limit()
        def my_view(request):
            ...
    """
    limiter = limiter or rate_limiter
    
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(self, request, *args, **kwargs):
            client_ip = limiter.get_client_ip(request)
            is_allowed, error_message = limiter.is_allowed(client_ip)
            
            if not is_allowed:
                return Response(
                    {'error': error_message},
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )
            
            return view_func(self, request, *args, **kwargs)
        
        return wrapped
    
    return decorator
