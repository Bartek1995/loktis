"""
Full Profile Test Runner — testuje WSZYSTKIE profile na jednej lokalizacji.

Uruchomienie:
    python global_tests/test_all_profiles_full.py
    python global_tests/test_all_profiles_full.py --lat 51.1 --lon 17.04 --address "Rynek, Wroclaw"
    python global_tests/test_all_profiles_full.py --profiles car_first,urban --no-cache
    python global_tests/test_all_profiles_full.py --runs 3  # stability test

Wymaga działającego serwera: python manage.py runserver

Wynik:
    - Pełny log w konsoli
    - Szczegółowy raport JSON + TXT w katalogu global_tests/test_logs/
    - Nazwa pliku z datą i godziną
    - Automatyczne wykrywanie anomalii
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from statistics import mean, stdev

import requests

# ============================================================================
# CONFIG
# ============================================================================

DEFAULT_API_URL = "http://localhost:8000/api/analyze-location/"
CONNECT_TIMEOUT = 10   # seconds to establish connection
READ_TIMEOUT = 180     # seconds per socket read (Overpass bywa wolny)
HARD_TIMEOUT = 300     # absolute max per profile (safety net)
LOG_DIR = Path(__file__).parent / "test_logs"

ALL_PROFILES = [
    "urban", "family", "quiet_green", "remote_work",
    "active_sport", "car_first", "investor", "custom",
]

# Domyślna lokalizacja testowa
DEFAULT_LAT = 51.277
DEFAULT_LON = 17.235
DEFAULT_ADDRESS = "1 Maja 11, Wiazow"


# ============================================================================
# HELPERS
# ============================================================================

class DualWriter:
    """Pisze jednocześnie do konsoli i do pliku."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.file = open(filepath, "w", encoding="utf-8")
        self.stdout = sys.stdout

    def write(self, text: str):
        self.stdout.write(text)
        self.file.write(text)

    def flush(self):
        self.stdout.flush()
        self.file.flush()

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ============================================================================
# ANOMALY DETECTION
# ============================================================================

def detect_anomalies(result: dict) -> list[str]:
    """Wykrywa anomalie logiczne w wynikach."""
    anomalies = []
    if result.get("status") != "OK":
        return anomalies

    cat_scores = result.get("category_scores", {})
    roads_debug = result.get("roads_debug", {})
    empty_cats = result.get("empty_categories", [])
    confidence = result.get("confidence")
    critical_caps = result.get("critical_caps", [])
    profile = result.get("profile", "")

    # car_access=0 mimo obecności dróg
    road_count = roads_debug.get("count", 0) if roads_debug else 0
    car_score = cat_scores.get("car_access")
    if road_count > 0 and car_score is not None and car_score == 0:
        anomalies.append(
            f"car_access=0 mimo {road_count} dróg — brak query Overpass lub brak POI?"
        )

    # confidence=100 mimo pustych kategorii
    if confidence == 100 and empty_cats:
        anomalies.append(
            f"confidence=100% mimo pustych: {', '.join(empty_cats)} — data_quality nie reaguje?"
        )

    # pusta kategoria krytyczna dla profilu
    # (profile-specific: car_access dla car_first, transport dla urban, etc.)
    critical_map = {
        "car_first": ["car_access"],
        "urban": ["transport", "food"],
        "family": ["education", "health"],
        "quiet_green": ["nature_place"],
        "active_sport": ["leisure"],
    }
    for crit_cat in critical_map.get(profile, []):
        if crit_cat in empty_cats:
            anomalies.append(
                f"Kategoria krytyczna '{crit_cat}' jest pusta dla profilu '{profile}'"
            )

    # critical cap aktywny = potencjalny problem z danymi
    if critical_caps:
        anomalies.append(
            f"Critical caps aktywne: {', '.join(critical_caps)}"
        )

    return anomalies


# ============================================================================
# PROFILE RUNNER
# ============================================================================

def run_profile(
    session: requests.Session,
    profile_key: str,
    lat: float,
    lon: float,
    address: str,
    api_url: str,
    use_cache: bool,
    out,
) -> dict:
    """Uruchamia analizę dla jednego profilu. Zwraca raport lub None."""
    body = {
        "latitude": lat,
        "longitude": lon,
        "price": None,
        "area_sqm": None,
        "address": address,
        "radius": 500,
        "profile_key": profile_key,
        "poi_provider": "hybrid",
    }
    if not use_cache:
        body["use_cache"] = False

    out.write(f"\n{'='*80}\n")
    out.write(f"  PROFIL: {profile_key.upper()}\n")
    out.write(f"{'='*80}\n")
    out.flush()

    t0 = time.time()
    max_retries = 3

    try:
        # Retry loop for 429 / 5xx
        resp = None
        for attempt in range(max_retries + 1):
            resp = session.post(
                api_url,
                json=body,
                headers={"X-Test-Run": "1"},
                stream=True,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = 2 * (2 ** attempt)  # 2s, 4s, 8s
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = max(wait, int(retry_after))
                    except ValueError:
                        pass
                out.write(f"  ⚠ {resp.status_code} — retry {attempt+1}/{max_retries} (wait {wait}s)\n")
                out.flush()
                if attempt < max_retries:
                    time.sleep(wait)
                    continue
            break

        resp.raise_for_status()

        report = None
        raw_lines = []
        for raw_line in resp.iter_lines():
            elapsed_so_far = time.time() - t0
            if elapsed_so_far > HARD_TIMEOUT:
                out.write(f"  ❌ HARD TIMEOUT ({HARD_TIMEOUT}s) — przerwanie\n")
                break

            if not raw_line:
                continue

            # Dekoduj bezpiecznie
            if isinstance(raw_line, bytes):
                line_str = raw_line.decode("utf-8", "ignore").strip()
            else:
                line_str = str(raw_line).strip()

            raw_lines.append(line_str)

            # Obsłuż SSE prefix
            if line_str.startswith("data:"):
                line_str = line_str[5:].strip()

            # Pomiń linie nie-JSON
            if not line_str.startswith("{"):
                out.write(f"  [raw] {line_str[:100]}\n")
                continue

            try:
                event = json.loads(line_str)
            except JSONDecodeError:
                out.write(f"  [decode-error] {line_str[:100]}\n")
                continue

            status = event.get("status", "")
            message = event.get("message", "")

            if status == "complete":
                report = event.get("result")
            elif status == "error":
                out.write(f"  ❌ ERROR: {event.get('error')}\n")
            else:
                out.write(f"  [{status}] {message}\n")
                out.flush()

        elapsed = time.time() - t0

        if not report:
            out.write(f"  ❌ BRAK RAPORTU (elapsed: {elapsed:.1f}s)\n")
            return {"profile": profile_key, "status": "FAILED", "elapsed_s": round(elapsed, 1)}

        # ── Wyciągnij dane ──
        verdict = report.get("verdict", {})
        scoring = report.get("scoring", {})
        gen_params = report.get("generation_params", {})
        data_quality = gen_params.get("data_quality", {})
        ai_insights = report.get("ai_insights", {})
        profile_info = report.get("profile", {})

        # ── Header ──
        out.write(f"\n  ⏱ Czas: {elapsed:.1f}s\n")
        out.write(f"  📊 Score: {verdict.get('score')}/100  |  Verdict: {verdict.get('level')}\n")
        out.write(f"  📝 {verdict.get('explanation', '')}\n")

        # ── Scoring breakdown ──
        out.write(f"\n  ── SCORING ──\n")
        out.write(f"  Total:       {scoring.get('total_score')}\n")
        out.write(f"  Base:        {scoring.get('base_score')}\n")
        out.write(f"  Noise pen:   {scoring.get('noise_penalty')}\n")
        out.write(f"  Roads pen:   {scoring.get('roads_penalty')}\n")
        out.write(f"  Quiet score: {scoring.get('quiet_score')}\n")
        out.write(f"  Caps:        {scoring.get('critical_caps_applied')}\n")

        # ── Data Quality ──
        out.write(f"\n  ── DATA QUALITY ──\n")
        out.write(f"  Confidence:  {data_quality.get('confidence_pct')}%\n")
        out.write(f"  Reasons:     {data_quality.get('reasons')}\n")
        out.write(f"  Empty cats:  {data_quality.get('empty_categories')}\n")
        out.write(f"  Error cats:  {data_quality.get('error_categories')}\n")
        out.write(f"  Overpass:    {data_quality.get('overpass_status')}\n")
        out.write(f"  Cache used:  {data_quality.get('cache_used')}\n")

        # ── Strengths / Weaknesses / Warnings ──
        out.write(f"\n  ── HIGHLIGHTS ──\n")
        for s in scoring.get("strengths", []):
            out.write(f"  ✅ {s}\n")
        for w in scoring.get("weaknesses", []):
            out.write(f"  ⚠️  {w}\n")
        for w in scoring.get("warnings", []):
            out.write(f"  🚨 {w}\n")

        # ── Category scores ──
        cats = scoring.get("category_scores", {})
        out.write(f"\n  ── KATEGORIE ({len(cats)}) ──\n")
        for cat, data in sorted(cats.items(), key=lambda x: x[1].get("score", 0), reverse=True):
            weight = profile_info.get("weights", {}).get(cat, 0)
            critical = " 🔴CRITICAL" if data.get("is_critical") else ""
            out.write(
                f"  {cat:20s}  score={data.get('score'):5.1f}  "
                f"pois={data.get('poi_count'):2d}  "
                f"nearest={str(data.get('nearest_distance_m', '-')):>5s}m  "
                f"weight={weight:+.2f}  "
                f"radius={data.get('radius_used')}m"
                f"{critical}\n"
            )
            for poi in data.get("top_pois", [])[:3]:
                out.write(
                    f"    → {poi.get('name', '?'):30s}  "
                    f"{poi.get('distance_m', '?')}m  "
                    f"score={poi.get('score', '?')}\n"
                )

        # ── Roads debug ──
        roads_debug = scoring.get("roads_debug", {})
        if roads_debug:
            out.write(f"\n  ── ROADS DEBUG ──\n")
            out.write(f"  Count:     {roads_debug.get('count')}\n")
            out.write(f"  Heavy:     {roads_debug.get('nearest_heavy_m')}m\n")
            out.write(f"  Primary:   {roads_debug.get('nearest_primary_m')}m\n")
            out.write(f"  Secondary: {roads_debug.get('nearest_secondary_m')}m\n")
            out.write(f"  Rails:     {roads_debug.get('nearest_rails_m')}m\n")
            out.write(f"  Scale:     {roads_debug.get('scale')}\n")

        # ── AI Insights (preview) ──
        if ai_insights:
            out.write(f"\n  ── AI INSIGHTS ──\n")
            summary = ai_insights.get("summary", "")
            if summary:
                out.write(f"  Summary: {summary[:200]}{'...' if len(summary) > 200 else ''}\n")
            for pt in ai_insights.get("attention_points", [])[:3]:
                out.write(f"  ⚠  {pt}\n")

        # ── POI raw counts ──
        poi_cats = report.get("poi_categories", {})
        if poi_cats:
            out.write(f"\n  ── POI RAW COUNTS ──\n")
            for cat, stats in sorted(poi_cats.items()):
                out.write(f"  {cat:20s}  count={stats.get('count'):2d}  nearest={stats.get('nearest')}m\n")

        out.write(f"\n  ── GENERATION PARAMS ──\n")
        out.write(f"  Fetch radius: {gen_params.get('fetch_radius')}m\n")
        out.write(f"  POI provider: {gen_params.get('poi_provider')}\n")
        out.write(f"  Radii: {json.dumps(gen_params.get('radii', {}), indent=None)}\n")

        result = {
            "profile": profile_key,
            "status": "OK",
            "elapsed_s": round(elapsed, 1),
            "score": verdict.get("score"),
            "verdict": verdict.get("level"),
            "confidence": data_quality.get("confidence_pct"),
            "empty_categories": data_quality.get("empty_categories", []),
            "critical_caps": scoring.get("critical_caps_applied", []),
            "roads_debug": roads_debug,
            "category_scores": {
                cat: data.get("score") for cat, data in cats.items()
            },
        }

        # ── Anomaly detection ──
        anomalies = detect_anomalies(result)
        result["anomalies"] = anomalies
        if anomalies:
            out.write(f"\n  ── 🔴 ANOMALIE ({len(anomalies)}) ──\n")
            for a in anomalies:
                out.write(f"  🔴 {a}\n")

        out.flush()
        return result

    except requests.exceptions.ConnectionError:
        out.write(f"  ❌ CONNECTION ERROR — czy serwer działa? (python manage.py runserver)\n")
        return {"profile": profile_key, "status": "CONNECTION_ERROR", "anomalies": []}
    except requests.exceptions.Timeout:
        out.write(f"  ❌ TIMEOUT (connect={CONNECT_TIMEOUT}s, read={READ_TIMEOUT}s)\n")
        return {"profile": profile_key, "status": "TIMEOUT", "anomalies": []}
    except Exception as e:
        out.write(f"  ❌ EXCEPTION: {e}\n")
        return {"profile": profile_key, "status": "ERROR", "error": str(e), "anomalies": []}


# ============================================================================
# SUMMARY TABLE
# ============================================================================

def print_summary(results: list, out):
    """Tabela podsumowująca wszystkie profile."""
    out.write(f"\n\n{'='*100}\n")
    out.write(f"  PODSUMOWANIE\n")
    out.write(f"{'='*100}\n\n")

    # Header
    out.write(
        f"  {'Profil':15s} {'Status':8s} {'Score':>6s} {'Verdict':15s} "
        f"{'Conf%':>5s} {'Czas':>6s} {'Empty':20s} {'Caps':s}\n"
    )
    out.write(f"  {'-'*95}\n")

    for r in results:
        if r["status"] != "OK":
            out.write(f"  {r['profile']:15s} {r['status']:8s}\n")
            continue

        empty = ", ".join(r.get("empty_categories", [])) or "—"
        caps = ", ".join(r.get("critical_caps", [])) or "—"

        score_str = str(r.get("score", "?"))
        conf_str = str(r.get("confidence", "?"))
        elapsed = r.get("elapsed_s", 0)
        elapsed_str = f"{elapsed:>5.1f}s" if isinstance(elapsed, (int, float)) else f"{'?':>5s}s"

        out.write(
            f"  {r['profile']:15s} {'OK':8s} {score_str:>6s} "
            f"{r.get('verdict', '?'):15s} {conf_str:>5s} "
            f"{elapsed_str} {empty:20s} {caps}\n"
        )

    # ── Category comparison across profiles ──
    out.write(f"\n\n  ── PORÓWNANIE KATEGORII ──\n\n")

    all_cats = set()
    for r in results:
        if r["status"] == "OK":
            all_cats.update(r.get("category_scores", {}).keys())

    cats_sorted = sorted(all_cats)
    ok_results = [r for r in results if r["status"] == "OK"]
    profile_names = [r["profile"] for r in ok_results]

    out.write(f"  {'Kategoria':20s}")
    for name in profile_names:
        out.write(f"  {name:>12s}")
    out.write("\n")
    out.write(f"  {'-'*20}")
    for _ in profile_names:
        out.write(f"  {'-'*12}")
    out.write("\n")

    for cat in cats_sorted:
        out.write(f"  {cat:20s}")
        for r in ok_results:
            score = r.get("category_scores", {}).get(cat)
            if score is not None:
                out.write(f"  {score:>12.1f}")
            else:
                out.write(f"  {'—':>12s}")
        out.write("\n")

    # ── All anomalies ──
    all_anomalies = []
    for r in results:
        for a in r.get("anomalies", []):
            all_anomalies.append(f"[{r['profile']}] {a}")

    if all_anomalies:
        out.write(f"\n\n  ── 🔴 WSZYSTKIE ANOMALIE ({len(all_anomalies)}) ──\n")
        for a in all_anomalies:
            out.write(f"  🔴 {a}\n")
    else:
        out.write(f"\n\n  ✅ Brak wykrytych anomalii\n")

    out.flush()


def print_stability_report(all_runs: list[list[dict]], out):
    """Porównuje wyniki wielu przebiegów tego samego testu."""
    out.write(f"\n\n{'='*100}\n")
    out.write(f"  RAPORT STABILNOŚCI ({len(all_runs)} przebiegów)\n")
    out.write(f"{'='*100}\n\n")

    # Zbierz score per profil per run
    profiles_seen = set()
    for run in all_runs:
        for r in run:
            if r["status"] == "OK":
                profiles_seen.add(r["profile"])

    out.write(f"  {'Profil':15s} {'Mean':>8s} {'StdDev':>8s} {'Min':>8s} {'Max':>8s}  {'Stabilny?':s}\n")
    out.write(f"  {'-'*65}\n")

    for profile in sorted(profiles_seen):
        scores = []
        for run in all_runs:
            for r in run:
                if r["profile"] == profile and r["status"] == "OK" and r.get("score") is not None:
                    score = r["score"]
                    if isinstance(score, (int, float)):
                        scores.append(float(score))

        if len(scores) < 2:
            out.write(f"  {profile:15s} {'—':>8s} {'—':>8s} (za mało danych)\n")
            continue

        avg = mean(scores)
        sd = stdev(scores)
        stable = "✅" if sd < 2.0 else ("⚠️" if sd < 5.0 else "❌")
        out.write(
            f"  {profile:15s} {avg:>8.1f} {sd:>8.2f} {min(scores):>8.1f} {max(scores):>8.1f}  {stable}\n"
        )

    out.flush()


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Test all profiles for a location")
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT, help="Latitude")
    parser.add_argument("--lon", type=float, default=DEFAULT_LON, help="Longitude")
    parser.add_argument("--address", type=str, default=DEFAULT_ADDRESS, help="Address label")
    parser.add_argument("--profiles", type=str, default=None,
                        help="Comma-separated profiles to test (default: all)")
    parser.add_argument("--api-url", type=str, default=DEFAULT_API_URL, help="API URL")
    parser.add_argument("--no-cache", action="store_true", help="Bypass POI cache (cold run)")
    parser.add_argument("--runs", type=int, default=1, help="Number of runs for stability test")
    args = parser.parse_args()

    profiles = [p.strip() for p in args.profiles.split(",")] if args.profiles else ALL_PROFILES
    use_cache = not args.no_cache

    # Przygotuj katalog logów
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_txt = LOG_DIR / f"profiles_{timestamp}.txt"
    log_json = LOG_DIR / f"profiles_{timestamp}.json"

    with DualWriter(str(log_txt)) as out:
        out.write(f"╔{'═'*78}╗\n")
        out.write(f"║  NEST SCORE — Full Profile Test Runner{' '*39}║\n")
        out.write(f"║  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{' '*55}║\n")
        out.write(f"╠{'═'*78}╣\n")
        out.write(f"║  Location: {args.address[:66]:66s}║\n")
        coords_str = f"{args.lat}, {args.lon}"
        out.write(f"║  Coords:   {coords_str:66s}║\n")
        out.write(f"║  Profiles: {', '.join(profiles)[:66]:66s}║\n")
        out.write(f"║  API:      {args.api_url[:66]:66s}║\n")
        out.write(f"║  Cache:    {'ON' if use_cache else 'OFF (cold run)':66s}║\n")
        out.write(f"║  Runs:     {str(args.runs):66s}║\n")
        out.write(f"╚{'═'*78}╝\n")
        out.flush()

        session = requests.Session()
        all_runs = []
        total_start = time.time()

        for run_num in range(1, args.runs + 1):
            if args.runs > 1:
                out.write(f"\n\n{'#'*80}\n")
                out.write(f"  RUN {run_num}/{args.runs}\n")
                out.write(f"{'#'*80}\n")

            results = []
            for i, profile_key in enumerate(profiles, 1):
                out.write(f"\n[{i}/{len(profiles)}] ")
                result = run_profile(
                    session=session,
                    profile_key=profile_key,
                    lat=args.lat,
                    lon=args.lon,
                    address=args.address,
                    api_url=args.api_url,
                    use_cache=use_cache,
                    out=out,
                )
                results.append(result)

            all_runs.append(results)
            print_summary(results, out)

        # Stability report
        if args.runs > 1:
            print_stability_report(all_runs, out)

        total_elapsed = time.time() - total_start
        out.write(f"\n  Total time: {total_elapsed:.1f}s\n")
        out.write(f"  Log saved:  {log_txt}\n")
        out.write(f"  JSON saved: {log_json}\n")

        # Save JSON
        json_data = {
            "timestamp": timestamp,
            "location": {"lat": args.lat, "lon": args.lon, "address": args.address},
            "cache_used": use_cache,
            "runs": args.runs,
            "total_elapsed_s": round(total_elapsed, 1),
            "all_runs": all_runs,
        }
        with open(log_json, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        # Exit code
        last_run = all_runs[-1]
        failed = [r for r in last_run if r["status"] != "OK"]
        anomaly_count = sum(len(r.get("anomalies", [])) for r in last_run)

        if failed:
            out.write(f"\n  ⚠ {len(failed)} profile(s) FAILED\n")
            sys.exit(1)
        elif anomaly_count > 0:
            out.write(f"\n  ⚠ {anomaly_count} anomaly(s) detected — see log\n")
            sys.exit(0)  # not a failure, but worth checking
        else:
            out.write(f"\n  ✅ All {len(profiles)} profiles OK, no anomalies\n")


if __name__ == "__main__":
    main()
