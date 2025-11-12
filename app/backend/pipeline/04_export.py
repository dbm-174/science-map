#!/usr/bin/env python3
import json
from pathlib import Path
from collections import Counter

BASE = Path(__file__).resolve().parents[2]
INTERIM = BASE / "backend" / "data" / "interim"
PROCESSED = BASE / "backend" / "data" / "processed"


def main():
    with open(INTERIM / "topics_people.json", "r", encoding="utf-8") as f:
        people = json.load(f)

    features = []
    projects_total = 0
    for p in people:
        projects_total += int(p.get("projects_count", 0))
        lon, lat = p.get("lon"), p.get("lat")
        if lon is None or lat is None:
            continue
        props = {
            "person_number": p["person_number"],
            "person_name": p["person_name"],
            "address": p["address"],
            "projects_count": p["projects_count"],
            "projects": p.get("projects", []),
            "topic_id": p.get("topic_id"),
            "topic_label": p.get("topic_label"),
            "color": p.get("color"),
            "url": p.get("url"),
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            }
        )

    geo = {"type": "FeatureCollection", "features": features}
    PROCESSED.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED / "people.geojson", "w", encoding="utf-8") as f:
        json.dump(geo, f, ensure_ascii=False)
    with open(
        BASE / "backend" / "data" / "processed" / "stats.json", "w", encoding="utf-8"
    ) as f:
        stats = {
            "total_people": len(people),
            "total_people_geocoded": len(features),
            "total_projects": projects_total,
        }
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(
        f"[04] Wrote people.geojson ({len(features)} geocoded features) and stats.json"
    )


if __name__ == "__main__":
    main()
