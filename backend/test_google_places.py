"""
Test script for Google Places API.
Run with: python test_google_places.py
"""
import os
import sys
import requests

# Load .env
from pathlib import Path
env_file = Path('.env')
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            key, val = line.split('=', 1)
            os.environ[key.strip()] = val.strip()

API_KEY = os.environ.get('GOOGLE_PLACES_API_KEY')
NEARBY_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

print(f"API Key configured: {bool(API_KEY)}")
print(f"API Key prefix: {API_KEY[:20] if API_KEY else None}...")

# Test real location: Olawa, Poland
lat, lon = 50.9461808, 17.2778681
print(f"\nTesting location: ({lat}, {lon}) - Olawa, Poland")

# Try single search type
params = {
    'location': f'{lat},{lon}',
    'radius': 500,
    'type': 'restaurant',
    'key': API_KEY,
}
print(f"\nRequest: restaurant search")
response = requests.get(NEARBY_SEARCH_URL, params=params, timeout=10)
data = response.json()
print(f"Status: {data.get('status')}")
print(f"Error: {data.get('error_message', 'none')}")
print(f"Results count: {len(data.get('results', []))}")

if data.get('results'):
    for r in data['results'][:5]:
        name = r.get('name', 'Unknown')
        vicinity = r.get('vicinity', 'no address')
        print(f"  - {name} ({vicinity})")
else:
    print("No results returned")

# Try other types
for ptype in ['supermarket', 'park', 'bank']:
    params['type'] = ptype
    response = requests.get(NEARBY_SEARCH_URL, params=params, timeout=10)
    data = response.json()
    print(f"\n{ptype}: {len(data.get('results', []))} results, status: {data.get('status')}")
