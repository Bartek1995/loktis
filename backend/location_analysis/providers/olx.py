"""
Provider dla OLX.pl
"""
import re
import json
import logging
from typing import Optional
from decimal import Decimal
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import BaseProvider, ListingData

logger = logging.getLogger(__name__)


class OlxProvider(BaseProvider):
    """Parser ogłoszeń z OLX.pl"""
    
    name = "olx"
    domains = ["olx.pl", "www.olx.pl"]
    
    def can_handle(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace('www.', '')
            # OLX dla nieruchomości
            return domain == 'olx.pl' and '/nieruchomosci/' in url.lower()
        except:
            return False
    
    def parse(self, url: str) -> ListingData:
        listing = ListingData(url=url)
        listing.source = "fetched"  # Mark as fetched from URL
        
        try:
            response = requests.get(
                url,
                headers=self.get_headers(),
                timeout=self.REQUEST_TIMEOUT,
                allow_redirects=True
            )
            response.raise_for_status()
        except requests.RequestException as e:
            listing.errors.append(f"Błąd pobierania strony: {str(e)}")
            return listing
        
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # OLX często ma dane w JSON w skrypcie
            self._extract_from_script(response.text, listing)
            
            # Fallback: parsing HTML
            self._parse_html(soup, listing)
            
            # Koordynaty
            self._extract_coordinates(soup, response.text, listing)
            
        except Exception as e:
            logger.exception("Błąd parsowania OLX")
            listing.errors.append(f"Błąd parsowania: {str(e)}")
        
        return listing
    
    def _extract_from_script(self, html: str, listing: ListingData) -> None:
        """Wyciąga dane z zagnieżdżonego JSON w skrypcie."""
        # OLX wstawia dane w window.__PRERENDERED_STATE__
        patterns = [
            r'window\.__PRERENDERED_STATE__\s*=\s*"(.+?)";',
            r'window\.__INIT_STATE__\s*=\s*({.+?});',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    # Może być URL-encoded
                    raw = match.group(1)
                    from urllib.parse import unquote
                    decoded = unquote(raw)
                    data = json.loads(decoded)
                    self._parse_olx_json(data, listing)
                    return
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
    
    def _parse_olx_json(self, data: dict, listing: ListingData) -> None:
        """Parsuje JSON ze struktury OLX."""
        # Struktura może się różnić, próbujemy kilka ścieżek
        ad_data = data.get('ad', {}).get('ad', {}) or data.get('ad', {})
        
        if not ad_data:
            return
        
        listing.title = ad_data.get('title', '')
        
        # Cena
        price_data = ad_data.get('price', {})
        if price_data:
            value = price_data.get('regularPrice', {}).get('value')
            if value:
                listing.price = Decimal(str(value))
        
        # Parametry
        params = ad_data.get('params', [])
        for param in params:
            key = param.get('key', '').lower()
            value = param.get('normalizedValue') or param.get('value', '')
            
            if key == 'm' or 'powierzchnia' in key:
                listing.area_sqm = self._extract_number(str(value))
            elif key == 'rooms' or 'pokoi' in key:
                listing.rooms = int(self._extract_number(str(value)) or 0) or None
            elif key == 'floor' or 'piętro' in key:
                listing.floor = str(value)
        
        # Lokalizacja
        location = ad_data.get('location', {})
        if location:
            city = location.get('city', {}).get('name', '')
            district = location.get('district', {}).get('name', '')
            listing.location = f"{city}, {district}".strip(', ')
        
        # Opis
        listing.description = ad_data.get('description', '')
        
        # Zdjęcia
        photos = ad_data.get('photos', [])
        listing.images = [p.get('link', '') for p in photos if p.get('link')][:10]
    
    def _parse_html(self, soup: BeautifulSoup, listing: ListingData) -> None:
        """Fallback parsing z HTML."""
        
        # Tytuł
        if not listing.title:
            title_elem = soup.find('h1', {'data-cy': 'ad_title'}) or soup.find('h1')
            if title_elem:
                listing.title = title_elem.get_text(strip=True)
        
        # Cena
        if not listing.price:
            price_elem = soup.find('div', {'data-testid': 'ad-price-container'})
            if price_elem:
                listing.price = self._extract_price(price_elem.get_text())
        
        # Parametry
        params_section = soup.find('ul', {'data-testid': 'parameters'})
        if params_section:
            for li in params_section.find_all('li'):
                text = li.get_text(strip=True).lower()
                if 'powierzchnia' in text or 'm²' in text:
                    if not listing.area_sqm:
                        listing.area_sqm = self._extract_number(text)
                elif 'pokoi' in text or 'pokoje' in text:
                    if not listing.rooms:
                        num = self._extract_number(text)
                        listing.rooms = int(num) if num else None
                elif 'piętro' in text:
                    if not listing.floor:
                        floor_match = re.search(r'(\d+|parter)', text)
                        listing.floor = floor_match.group(1) if floor_match else ''
        
        # Lokalizacja
        if not listing.location:
            location_elem = soup.find('p', {'data-testid': 'location-date'})
            if location_elem:
                listing.location = location_elem.get_text(strip=True).split('-')[0].strip()
        
        # Opis
        if not listing.description:
            desc_elem = soup.find('div', {'data-cy': 'ad_description'})
            if desc_elem:
                listing.description = desc_elem.get_text(separator='\n', strip=True)
        
        # Cena za m²
        if listing.price and listing.area_sqm and listing.area_sqm > 0:
            listing.price_per_sqm = Decimal(str(round(float(listing.price) / listing.area_sqm, 2)))
    
    def _extract_coordinates(self, soup: BeautifulSoup, html: str, listing: ListingData) -> None:
        """Próbuje wyciągnąć koordynaty."""
        # OLX zazwyczaj nie pokazuje dokładnych koordynatów
        # Próbujemy znaleźć w danych mapy
        patterns = [
            r'"lat":\s*([\d.]+),\s*"lon":\s*([\d.]+)',
            r'"latitude":\s*([\d.]+),\s*"longitude":\s*([\d.]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                try:
                    lat = float(match.group(1))
                    lng = float(match.group(2))
                    if 49.0 <= lat <= 55.0 and 14.0 <= lng <= 24.5:
                        listing.latitude = lat
                        listing.longitude = lng
                        listing.has_precise_location = True
                        return
                except ValueError:
                    continue
