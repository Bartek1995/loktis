"""
Provider dla Otodom.pl
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


class OtodomProvider(BaseProvider):
    """Parser ogłoszeń z Otodom.pl"""
    
    name = "otodom"
    domains = ["otodom.pl", "www.otodom.pl"]
    
    def can_handle(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower().replace('www.', '') == 'otodom.pl'
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
            
            # Próba wyciągnięcia danych z JSON-LD (preferowana metoda)
            json_data = self._extract_json_ld(soup)
            if json_data:
                self._parse_json_ld(json_data, listing)

            # Próba wyciągnięcia danych z __NEXT_DATA__ (pełniejsze dane)
            next_data = self._extract_next_data(soup)
            if next_data:
                self._parse_next_data(next_data, listing)
            
            # Fallback: parsing HTML
            self._parse_html(soup, listing)
            
            # Próba wyciągnięcia koordynatów
            self._extract_coordinates(soup, response.text, listing)
            
        except Exception as e:
            logger.exception("Błąd parsowania Otodom")
            listing.errors.append(f"Błąd parsowania: {str(e)}")
        
        return listing
    
    def _extract_json_ld(self, soup: BeautifulSoup) -> Optional[dict]:
        """Wyciąga dane z JSON-LD schema."""
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    return data
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') in ['Product', 'RealEstateListing', 'Residence']:
                            return item
            except json.JSONDecodeError:
                continue
        return None
    
    def _parse_json_ld(self, data: dict, listing: ListingData) -> None:
        """Parsuje dane z JSON-LD."""
        listing.title = data.get('name', '')
        
        offers = data.get('offers', {})
        if offers:
            price_str = str(offers.get('price', ''))
            if price_str:
                listing.price = self._extract_price(price_str)
        
        if 'image' in data:
            images = data['image']
            if isinstance(images, str):
                listing.images = [images]
            elif isinstance(images, list):
                listing.images = images[:10]
    
    def _extract_next_data(self, soup: BeautifulSoup) -> Optional[dict]:
        """Wyciąga dane z __NEXT_DATA__ script."""
        script = soup.find('script', id='__NEXT_DATA__')
        if script:
            try:
                return json.loads(script.string)
            except (ValueError, TypeError):
                pass
        return None

    def _parse_next_data(self, data: dict, listing: ListingData) -> None:
        """Parsuje dane z __NEXT_DATA__."""
        try:
            ad = data.get('props', {}).get('pageProps', {}).get('ad', {})
            if not ad:
                return

            # Description (full content)
            if not listing.description:
                raw_desc = ad.get('description')
                if raw_desc:
                     # Clean HTML tags
                    listing.description = BeautifulSoup(raw_desc, 'html.parser').get_text(separator='\n', strip=True)

            # Basic info from target
            target = ad.get('target', {})
            characteristics = ad.get('characteristics', [])

            # Area
            if not listing.area_sqm:
                val = target.get('Area')
                if val:
                    try:
                        listing.area_sqm = float(val)
                    except (ValueError, TypeError):
                        pass

            # Rooms
            if not listing.rooms:
                val = target.get('Rooms_num')
                if isinstance(val, list) and val: val = val[0]
                if val:
                    try:
                        listing.rooms = int(val)
                    except (ValueError, TypeError):
                        pass

            # Floor
            if not listing.floor:
                val = target.get('Floor_no')
                if isinstance(val, list) and val: val = val[0]
                
                if val:
                    val = str(val)
                    if val.startswith('floor_'):
                        val = val.replace('floor_', '')
                    
                    if val == 'ground' or val == 'ground_floor':
                        val = '0'
                    elif val == 'cellar':
                        val = '-1'
                    elif val == 'garret':
                        val = 'p'
                    listing.floor = val

            # Price
            if not listing.price:
                val = target.get('Price')
                if val:
                    try:
                        listing.price = float(val)
                    except (ValueError, TypeError):
                        pass

            # Title
            if not listing.title:
                listing.title = ad.get('title')

            # Images
            if not listing.images:
                imgs = ad.get('images', [])
                if imgs and isinstance(imgs, list):
                    listing.images = [img.get('large') for img in imgs if isinstance(img, dict) and img.get('large')]

        except Exception as e:
            logger.error(f"Error parsing Next data: {e}")

    def _parse_html(self, soup: BeautifulSoup, listing: ListingData) -> None:
        """Fallback parsing z HTML."""
        
        # Tytuł
        if not listing.title:
            title_elem = soup.find('h1', {'data-cy': 'adPageAdTitle'}) or soup.find('h1')
            if title_elem:
                listing.title = title_elem.get_text(strip=True)
        
        # Cena
        if not listing.price:
            price_elem = soup.find('strong', {'data-cy': 'adPageHeaderPrice'})
            if price_elem:
                listing.price = self._extract_price(price_elem.get_text())
        
        # Parametry (metraż, pokoje, piętro)
        params_section = soup.find('div', {'data-testid': 'ad.top-information.table'})
        if params_section:
            self._parse_params_table(params_section, listing)
        
        # Alternatywne szukanie parametrów
        # Alternatywne szukanie parametrów - strict regex
        for item in soup.find_all('div', class_=re.compile(r'css-.*')):
            text = item.get_text(separator=' ', strip=True).lower()
            
            # Pokoje - szukamy konkretnej frazy "X pokoi" lub "pokoje: X"
            if not listing.rooms:
                rooms_match = re.search(r'(?:liczba\s+)?pokoi:?\s*(\d+)', text) or \
                              re.search(r'(\d+)\s*pokoi', text) or \
                              re.search(r'(\d+)\s*pokoje', text)
                if rooms_match:
                    try:
                        val = int(rooms_match.group(1))
                        # Sanity check - unlikely to have > 15 rooms in a typical listing unless mansion
                        if 0 < val < 20: 
                            listing.rooms = val
                    except ValueError:
                        pass
                        
            # Piętro
            if not listing.floor:
                # "piętro 4/4", "piętro: 3", "3 piętro"
                floor_match = re.search(r'piętro:?\s*(\d+|parter)', text) or \
                              re.search(r'(\d+|parter)\s*piętro', text) or \
                              re.search(r'piętro\s*(\d+)(?:/\d+)?', text)
                if floor_match:
                    listing.floor = floor_match.group(1)

            # Powierzchnia
            if not listing.area_sqm:
               area_match = re.search(r'powierzchnia:?\s*([\d,.]+)\s*(?:m|metr)', text) or \
                            re.search(r'([\d,.]+)\s*(?:m²|mkw)', text)
               if area_match:
                   try:
                       area_str = area_match.group(1).replace(',', '.')
                       listing.area_sqm = float(area_str)
                   except ValueError:
                       pass
        
        # Lokalizacja
        location_elem = soup.find('a', {'aria-label': re.compile(r'Adres', re.I)})
        if location_elem:
            listing.location = location_elem.get_text(strip=True)
        else:
            # Fallback - breadcrumbs
            breadcrumbs = soup.find_all('a', {'data-cy': re.compile(r'breadcrumb')})
            if breadcrumbs:
                listing.location = ' > '.join([b.get_text(strip=True) for b in breadcrumbs])
        
        # Opis
        if not listing.description:
            desc_elem = soup.find('div', {'data-cy': 'adPageAdDescription'})
            if desc_elem:
                listing.description = desc_elem.get_text(separator='\n', strip=True)
        
        # Zdjęcia (jeśli brak z JSON-LD)
        if not listing.images:
            img_elements = soup.find_all('img', {'src': re.compile(r'otodom.*\.(jpg|jpeg|png|webp)', re.I)})
            listing.images = [img['src'] for img in img_elements if img.get('src')][:10]
        
        # Cena za m²
        if listing.price and listing.area_sqm and listing.area_sqm > 0:
            listing.price_per_sqm = Decimal(str(round(float(listing.price) / listing.area_sqm, 2)))
    
    def _parse_params_table(self, section, listing: ListingData) -> None:
        """Parsuje tabelę z parametrami."""
        rows = section.find_all('div', recursive=False)
        for row in rows:
            text = row.get_text(strip=True).lower()
            if 'powierzchnia' in text:
                listing.area_sqm = self._extract_number(text)
            elif 'pokoi' in text or 'pokoje' in text:
                num = self._extract_number(text)
                if num:
                    listing.rooms = int(num)
            elif 'piętro' in text:
                floor_match = re.search(r'(\d+|parter)', text)
                if floor_match:
                    listing.floor = floor_match.group(1)
    
    def _extract_coordinates(self, soup: BeautifulSoup, html: str, listing: ListingData) -> None:
        """Próbuje wyciągnąć koordynaty z mapy."""
        # Szukaj w skryptach
        coord_patterns = [
            r'"coordinates":\s*\{\s*"latitude":\s*([\d.]+),\s*"longitude":\s*([\d.]+)',
            r'"latitude":\s*([\d.]+).*?"longitude":\s*([\d.]+)',
            r'lat["\']?\s*[:=]\s*([\d.]+).*?(?:lng|lon)["\']?\s*[:=]\s*([\d.]+)',
        ]
        
        for pattern in coord_patterns:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match:
                try:
                    lat = float(match.group(1))
                    lng = float(match.group(2))
                    # Walidacja - Polska mieści się w zakresie
                    if 49.0 <= lat <= 55.0 and 14.0 <= lng <= 24.5:
                        listing.latitude = lat
                        listing.longitude = lng
                        listing.has_precise_location = True
                        return
                except ValueError:
                    continue
        
        # Szukanie w meta tagach OpenGraph
        og_lat = soup.find('meta', property='place:location:latitude')
        og_lng = soup.find('meta', property='place:location:longitude')
        if og_lat and og_lng:
            try:
                listing.latitude = float(og_lat.get('content', ''))
                listing.longitude = float(og_lng.get('content', ''))
                listing.has_precise_location = True
            except ValueError:
                pass
