"""
Full test of GooglePlacesClient through Django.
Run with: python manage.py shell < test_google_full.py
"""
import os
from pathlib import Path

# Load .env
env_file = Path('.env')
for line in env_file.read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        key, val = line.split('=', 1)
        os.environ[key.strip()] = val.strip()

from location_analysis.geo.google_places_client import GooglePlacesClient

client = GooglePlacesClient()
print(f'API Key configured: {bool(client.api_key)}')
print(f'API Key prefix: {client.api_key[:20] if client.api_key else "MISSING"}...')

# Full test
lat, lon = 50.9461808, 17.2778681
print(f'\nTesting get_pois_around({lat}, {lon}, 500)...')
pois, metrics = client.get_pois_around(lat, lon, 500)

total = sum(len(v) for v in pois.values())
print(f'\nTotal POIs found: {total}')
for cat, items in pois.items():
    if items:
        print(f'  {cat}: {len(items)} items')
        for poi in items[:3]:
            print(f'    - {poi.name} ({poi.subcategory}) @ {poi.distance_m:.0f}m')

print(f'\nNature metrics: {metrics}')
