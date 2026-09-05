from flask import Flask, render_template, request, send_file
from markupsafe import escape
import requests
import math
import time
import os
import json
import subprocess

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DATA_PATH = os.path.join(BASE_DIR, "report_data.json")
REPORT_PDF_PATH = os.path.join(BASE_DIR, "report.pdf")

TAG_MAP = {
    "cafe": ("amenity", "cafe"),
    "restaurant": ("amenity", "restaurant"),
    "hotel": ("tourism", "hotel"),
}

RADIUS_METERS = 1000

def assess_competition(count, closest_distance):
    if count <= 1:
        tier = "Lower observed direct competition"
    elif count <= 4:
        tier = "Moderate observed direct competition"
    else:
        tier = "Higher observed direct competition"

    venue_word = "venue" if count == 1 else "venues"
    count_sentence = f"{tier}: {count} matching {venue_word} found within the search radius."

    if closest_distance is not None:
        distance_sentence = f"The closest matching venue is {closest_distance} m away."
    else:
        distance_sentence = "No matching venues were found nearby to measure a closest distance."

    recommendation_sentence = (
        "Validate these findings with local field research before making any real business decision."
    )

    level = f"{count_sentence} {distance_sentence} {recommendation_sentence}"

    nearby_note = None
    if closest_distance is not None and closest_distance < 250:
        nearby_note = "A direct competitor is very nearby (under 250 m)."

    return {"level": level, "nearby_note": nearby_note}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return round(2 * R * math.asin(math.sqrt(a)))

def geocode(address):
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": address, "format": "json", "limit": 1},
        headers={"User-Agent": "HorecaLens/1.0 (gamalalsa2021@gmail.com)"},
        timeout=10,
    )
    data = resp.json()
    if not data:
        return None, None
    return float(data[0]["lat"]), float(data[0]["lon"])

class OverpassError(Exception):
    pass

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
RETRYABLE_STATUSES = (429, 502, 503, 504)
RETRY_DELAYS = (2, 4, 8)

_overpass_cache = {}

def _request_overpass(url, query):
    resp = requests.post(
        url,
        data={"data": query},
        headers={"User-Agent": "HorecaLens/1.0 (gamalalsa2021@gmail.com)"},
        timeout=30,
    )
    print(f"Overpass response from {url}: status={resp.status_code}")

    if resp.status_code in RETRYABLE_STATUSES:
        print(f"body={resp.text[:200]!r}")
        return None

    if resp.status_code != 200:
        print(f"body={resp.text[:200]!r}")
        raise OverpassError(f"Overpass API returned status {resp.status_code}")

    try:
        return resp.json().get("elements", [])
    except ValueError:
        print(f"body={resp.text[:200]!r}")
        raise OverpassError("Overpass API returned a non-JSON response")

def query_overpass(lat, lon, tag_key, tag_val, category):
    cache_key = (lat, lon, category)
    if cache_key in _overpass_cache:
        return _overpass_cache[cache_key]

    query = f"""
[out:json][timeout:25];
nwr["{tag_key}"="{tag_val}"](around:{RADIUS_METERS},{lat},{lon});
out center;
"""
    for url in OVERPASS_URLS:
        for attempt in range(len(RETRY_DELAYS) + 1):
            elements = _request_overpass(url, query)
            if elements is not None:
                _overpass_cache[cache_key] = elements
                return elements
            if attempt < len(RETRY_DELAYS):
                time.sleep(RETRY_DELAYS[attempt])

    raise OverpassError("Overpass API is unavailable")

@app.route("/", methods=["GET", "POST"])
def index():
    results = None
    error = None
    address = ""
    category = "cafe"
    fewer_than_5 = False
    total_count = None
    closest_distance = None
    competition = None
    report_payload = None

    if request.method == "POST":
        address = request.form.get("address", "").strip()
        category = request.form.get("category", "cafe")

        lat, lon = geocode(address)
        if lat is None:
            error = "Address not found. Please try a more specific address."
        else:
            tag_key, tag_val = TAG_MAP[category]
            try:
                elements = query_overpass(lat, lon, tag_key, tag_val, category)
            except OverpassError:
                error = "Venue lookup failed. Please try again."
            else:
                venues = []
                for el in elements:
                    center = el.get("center") or {}
                    elat = el.get("lat") or center.get("lat")
                    elon = el.get("lon") or center.get("lon")
                    if elat is None or elon is None:
                        continue
                    tags = el.get("tags", {})
                    name = tags.get("name", "Unnamed")
                    website = tags.get("website") or tags.get("contact:website") or ""
                    dist = haversine(lat, lon, float(elat), float(elon))
                    venues.append({"name": name, "type": category, "website": website, "distance": dist})

                venues.sort(key=lambda x: x["distance"])
                total_count = len(venues)
                closest_distance = venues[0]["distance"] if venues else None
                competition = assess_competition(total_count, closest_distance)
                if len(venues) < 5:
                    fewer_than_5 = True
                results = venues[:5]

                report_payload = {
                    "address": address,
                    "category": category,
                    "radius": RADIUS_METERS,
                    "total_count": total_count,
                    "closest_distance": closest_distance,
                    "competition": competition,
                    "results": results,
                }

    return render_template(
        "index.html",
        results=results,
        error=error,
        address=address,
        category=category,
        fewer_than_5=fewer_than_5,
        radius=RADIUS_METERS,
        total_count=total_count,
        closest_distance=closest_distance,
        competition=competition,
        report_payload=report_payload,
    )

@app.route("/report", methods=["POST"])
def generate_report():
    raw_payload = request.form.get("report_data")
    if not raw_payload:
        return "No report data submitted.", 400

    try:
        data = json.loads(raw_payload)
    except ValueError:
        return "Invalid report data submitted.", 400

    with open(REPORT_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)

    if not os.path.exists(REPORT_DATA_PATH):
        return "Failed to write report_data.json.", 500

    result = subprocess.run(
        "quarto render report.qmd",
        cwd=BASE_DIR,
        shell=True,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        return f"<h1>Report generation failed</h1><pre>{escape(output)}</pre>", 500

    return send_file(REPORT_PDF_PATH, as_attachment=True, download_name="horeca_report.pdf")

if __name__ == "__main__":
    app.run(debug=True)
