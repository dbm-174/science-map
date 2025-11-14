#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, argparse, hashlib
from collections import defaultdict, Counter
from pathlib import Path


def load_json(path: Path, default=None):
    if path and path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return default


def stable_id_from_title(title: str) -> str:
    h = hashlib.md5(title.strip().lower().encode("utf-8")).hexdigest()
    return f"PRJ_{h[:10]}"


def pseudo_years(title: str):
    h = int(hashlib.sha1(title.encode("utf-8")).hexdigest(), 16)
    start = 2001 + (h % 20)  # 2001..2020
    dur = 1 + (h // 101) % 5  # 1..5
    end = min(start + dur, 2025)
    return start, end


def main():
    ap = argparse.ArgumentParser(
        description="Erzeuge projects.json aus people.geojson."
    )
    ap.add_argument("--people", default="people.geojson", help="Pfad zu people.geojson")
    ap.add_argument(
        "--topics", default="topics.json", help="Pfad zu topics.json (optional)"
    )
    ap.add_argument(
        "--in-projects",
        default="projects.json",
        help="Vorhandene projects.json (optional, für Merge)",
    )
    ap.add_argument(
        "--out-projects", default="projects.json", help="Ziel projects.json"
    )
    ap.add_argument("--out-stats", default="stats.json", help="Ziel stats.json")
    args = ap.parse_args()

    people_path = Path(args.people)
    topics_path = Path(args.topics)
    in_projects_path = Path(args.in_projects) if args.in_projects else None
    out_projects_path = Path(args.out_projects)
    out_stats_path = Path(args.out_stats)

    # Laden
    people = load_json(people_path)
    if not people or "features" not in people:
        raise SystemExit(
            f"Fehler: '{people_path}' nicht gefunden oder kein FeatureCollection."
        )
    topics_list = load_json(topics_path, default=[])
    # topics.json kann Liste von {id,label,color,...} sein
    topics_by_id = {
        str(t.get("id")): t for t in topics_list if isinstance(t, dict) and "id" in t
    }

    existing_projects = (
        load_json(in_projects_path, default=[]) if in_projects_path else []
    )
    # Map: Titel -> vorhandene Daten
    by_title_existing = {}
    for p in existing_projects:
        title = (p.get("title") or "").strip()
        if not title:
            continue
        by_title_existing[title.lower()] = p

    # Sammeln: Titel -> Aggregat
    buckets = defaultdict(
        lambda: {
            "people": set(),
            "topic_ids": Counter(),
            "topic_labels": Counter(),
            "urls": Counter(),
        }
    )

    for feat in people.get("features", []):
        props = feat.get("properties", {}) or {}
        pid = str(
            props.get("person_number")
            or props.get("person_id")
            or props.get("id")
            or ""
        ).strip()
        if not pid:
            continue
        topic_id = props.get("topic_id")
        topic_label = props.get("topic_label")
        url = props.get("url")
        titles = props.get("projects") or []
        for t in titles:
            if not t or not isinstance(t, str):
                continue
            title = t.strip()
            b = buckets[title]
            b["people"].add(pid)
            if topic_id is not None:
                b["topic_ids"][str(topic_id)] += 1
            if topic_label:
                b["topic_labels"][str(topic_label)] += 1
            if url:
                b["urls"][url] += 1

    # Projekte bauen
    projects_out = []
    for title, agg in buckets.items():
        # vorhandenes Projekt zu diesem Titel?
        p_exist = by_title_existing.get(title.lower())

        # ID
        pid = p_exist.get("id") if p_exist else stable_id_from_title(title)

        # Topic bestimmen
        topic_id_str = None
        topic_label = None
        if p_exist and p_exist.get("topic_id") is not None:
            topic_id_str = str(p_exist["topic_id"])
        elif agg["topic_ids"]:
            topic_id_str = agg["topic_ids"].most_common(1)[0][0]

        # Label/Farbe ggf. aus topics.json spiegeln
        if topic_id_str and topic_id_str in topics_by_id:
            t = topics_by_id[topic_id_str]
            topic_label = t.get("label", topic_label)
        else:
            # Fallback: häufigstes Label aus people.geojson
            if agg["topic_labels"]:
                topic_label = agg["topic_labels"].most_common(1)[0][0]

        # Jahre/URL
        url = (p_exist.get("url") if p_exist else None) or (
            agg["urls"].most_common(1)[0][0] if agg["urls"] else ""
        )
        start_year = p_exist.get("start_year") if p_exist else None
        end_year = p_exist.get("end_year") if p_exist else None
        if start_year is None or end_year is None:
            sy, ey = pseudo_years(title)
            start_year = start_year if start_year is not None else sy
            end_year = end_year if end_year is not None else ey

        projects_out.append(
            {
                "id": str(pid),
                "title": title,
                "topic_id": int(topic_id_str)
                if (topic_id_str and topic_id_str.isdigit())
                else topic_id_str,
                "topic_label": topic_label,
                "start_year": int(start_year) if start_year is not None else None,
                "end_year": int(end_year) if end_year is not None else None,
                "url": url or "",
                "people": sorted(list(agg["people"])),
            }
        )

    # Schreiben projects.json
    projects_out.sort(key=lambda p: (p["start_year"] or 0, p["title"]))
    out_projects_path.write_text(
        json.dumps(projects_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # stats.json aktualisieren/erzeugen
    stats = load_json(out_stats_path, default={}) or {}
    stats["total_people"] = len(people.get("features", []))
    stats["total_people_geocoded"] = sum(
        1
        for f in people.get("features", [])
        if f.get("geometry", {}).get("type") == "Point"
    )
    stats["total_projects"] = len(projects_out)
    out_stats_path.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Report
    with_people = sum(1 for p in projects_out if p["people"])
    with_years = sum(1 for p in projects_out if p["start_year"] is not None)
    print(
        f"[OK] projects.json: {len(projects_out)} Projekte (davon {with_people} mit Personen, {with_years} mit Jahresangaben)"
    )
    print(
        f"[OK] stats.json: total_people={stats['total_people']}, geocoded={stats['total_people_geocoded']}, total_projects={stats['total_projects']}"
    )


if __name__ == "__main__":
    main()
