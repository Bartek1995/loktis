"""
Test HybridPOIProvider na realnych danych.
Uruchom z root projektu: backend$ python manage.py shell < global_tests/test_hybrid_poi.py
"""
import os
import sys
import time
from pathlib import Path

# Setup Django if not running via manage.py shell (przydatne do devu)
import django
from django.conf import settings
if not settings.configured:
    # Wymaga odpalania przez python manage.py shell
    print("WARNING: This script should be run via 'python manage.py shell < global_tests/test_hybrid_poi.py'")

from location_analysis.geo.hybrid_poi_provider import HybridPOIProvider
from location_analysis.diagnostics import AnalysisTraceContext

def run_test():
    print("=== TEST HYBRID POI PROVIDER ===")
    provider = HybridPOIProvider()
    
    # Przykładowe koordynaty - Wrocław (Śródmieście)
    lat, lon = 51.1118, 17.0392
    
    # Konfiguracja promieni: Globalny max_radius to np 1000m, 
    # ale konktretne kategorie mają ucięte promienie (jak w profilach)
    max_radius_m = 1000
    radius_by_category = {
        'shops': 500,     # sklepy tylko do 500m
        'education': 800, # szkoły do 800m
        'food': 300,      # knajpy do 300m
        'health': 1000,   # zdrowie do 1000m
        'nature_place': 800,
        'leisure': 1000,
        'transport': 600,
    }
    
    ctx = AnalysisTraceContext()
    
    print(f"\nUruchamiam get_pois_hybrid dla Wrocławia: {lat}, {lon}")
    print(f"Max global radius (OSM): {max_radius_m}m")
    print(f"Radius by category (Google & final filters): {radius_by_category}")
    
    start_time = time.time()
    
    # Odpalamy pełną hybrydę!
    pois_by_category, metrics = provider.get_pois_hybrid(
        lat=lat,
        lon=lon,
        radius_m=max_radius_m,
        radius_by_category=radius_by_category,
        enable_enrichment=True,
        enable_fallback=True,
        trace_ctx=ctx
    )
    
    duration = time.time() - start_time
    
    print("\n=== WYNIKI ===")
    print(f"Czas egzekucji powiązany z IO: {duration:.2f} s")
    print("\nIlość POI po nałożeniu filtrów (category_radius):")
    total_pois = 0
    for cat, items in pois_by_category.items():
        if items:
            total_pois += len(items)
            
            # Wypisz max dystans jaki faktycznie wrócił
            max_returned_dist = max(p.distance_m for p in items) if items else 0
            
            # Policz źródła
            sources = {}
            for p in items:
                sources[p.source] = sources.get(p.source, 0) + 1
                
            sources_str = ", ".join(f"{k}: {v}" for k, v in sources.items())
            expected_radius = radius_by_category.get(cat, max_radius_m)
            
            print(f" - {cat}: {len(items)} items (Max allowed radius: {expected_radius}m -> max returned: {max_returned_dist:.0f}m)")
            print(f"   Sources: {sources_str}")
            
    print(f"\nTotal POIs kept: {total_pois}")
    print("\nDiagnostyka i metryki kontekstu:")
    print(ctx.summary.to_meta())

run_test()
