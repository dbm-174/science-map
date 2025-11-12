#!/usr/bin/env python3
import json, time, sqlite3, os, sys, urllib.parse, requests
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
INTERIM = BASE / "backend" / "data" / "interim"
CACHE_DB = BASE / "backend" / "data" / "cache" / "geocode.sqlite"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
EMAIL = os.getenv("NOMINATIM_EMAIL", "you@example.org")
UA = "GEPRIS-Map-Prototype/0.1 (+{})".format(EMAIL)


def db():
    con = sqlite3.connect(CACHE_DB)
    con.execute(
        "CREATE TABLE IF NOT EXISTS geocode(address TEXT PRIMARY KEY, lon REAL, lat REAL, precision TEXT)"
    )
    return con


def cache_get(con, key):
    cur = con.execute("SELECT lon, lat, precision FROM geocode WHERE address=?", (key,))
    row = cur.fetchone()
    return (row[0], row[1], row[2]) if row else None


def cache_put(con, key, lon, lat, prec):
    con.execute(
        "INSERT OR REPLACE INTO geocode(address, lon, lat, precision) VALUES (?,?,?,?)",
        (key, lon, lat, prec),
    )
    con.commit()


def geocode(addr_text: str, city: str = "", country: str = ""):
    q = addr_text or ""
    if not q and city:
        q = city
    if country and country.lower() not in q.lower():
        q = f"{q}, {country}"
    params = {
        "q": q,
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 0,
        "email": EMAIL,
    }
    headers = {"User-Agent": UA}
    r = requests.get(NOMINATIM, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    js = r.json()
    if not js:
        return None
    item = js[0]
    return float(item["lon"]), float(item["lat"]), item.get("class", "place")


def main():
    in_path = INTERIM / "clean_people.json"
    out_path = INTERIM / "geocoded_people.json"
    with open(in_path, "r", encoding="utf-8") as f:
        people = json.load(f)

    con = db()
    out = []
    for i, p in enumerate(people, 1):
        addrj = p["address_norm"]["address_joined"]
        city = p["address_norm"]["city"]
        country = p["address_norm"]["country"]
        key = addrj or (city + (", " + country if country else ""))
        lon = lat = None
        prec = "unknown"
        if key:
            cached = cache_get(con, key)
            if cached:
                lon, lat, prec = cached
            else:
                try:
                    res = geocode(addrj, city, country)
                    if not res and city:
                        res = geocode(city, "", country)
                    if res:
                        lon, lat, prec = res
                        cache_put(con, key, lon, lat, prec)
                    time.sleep(1.1)  # Nominatim politeness
                except Exception as e:
                    time.sleep(1.1)
        p["lon"] = lon
        p["lat"] = lat
        p["geocode_precision"] = prec
        out.append(p)

        if i % 50 == 0:
            print(f"[02] {i}/{len(people)} geocoded...")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[02] Wrote {out_path} with {len(out)} records")


if __name__ == "__main__":
    main()
