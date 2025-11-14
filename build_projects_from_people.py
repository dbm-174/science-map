#!/usr/bin/env python3
import json, sys, hashlib, math
from collections import defaultdict, Counter
from pathlib import Path


def stable_id_from_title(title: str) -> str:
    h = hashlib.md5(title.strip().lower().encode("utf-8")).hexdigest()
    return f"PRJ_{h[:10]}"  # stabil, lesbar


def pseudo_years(title: str):
    # deterministische Pseudo-Jahre für Demo/Filter (2001–2024)
    h = int(hashlib.sha1(title.encode("utf-8")).hexdigest(), 16)
    start = 2001 + (h % 20)  # 2001..2020
    dur = 1 + (h // 101) % 5  # 1..5 Jahre
    end = min(start + dur, 2025)
    return start, end


def load_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def main(
    people_path="people.geojson",
    topics_path="topics.json",
    out_projects="projects.json",
    out_stats="stats.json",
):
    people = load_json(people_path)
    topics = {str(t.get("id")): t for t in load_json(topics_path)}

    # Sammeln: title -> {people:set, topic_ids:Counter, labels:Counter}
    by_title = defaultdict(
        lambda: {"people": set(), "topic_ids": Counter(), "labels": Counter()}
    )

    feat_list = people.get("features", [])
    for f in feat_list:
        props = f.get("properties", {})
        pid = str(props.get("person_number") or props.get("person_id") or "")
        if not pid:
            continue
        topic_id = (
            str(props.get("topic_id")) if props.get("topic_id") is not None else None
        )
        topic_label = props.get("topic_label")
        for title in props.get("projects") or []:
            if not title or not isinstance(title, str):
                continue
            bucket = by_title[title.strip()]
            bucket["people"].add(pid)
            if topic_id is not None:
                bucket["topic_ids"][topic_id] += 1
            if topic_label:
                bucket["labels"][topic_label] += 1

    projects = []
    for title, agg in by_title.items():
        pid_list = sorted(list(agg["people"]))
        if not pid_list:
            continue
        # Mehrheits-Topic aus Personen ableiten
        topic_id = None
        topic_label = None
        if agg["topic_ids"]:
            topic_id = agg["topic_ids"].most_common(1)[0][0]
            topic_label = topics.get(str(topic_id), {}).get("label")
        if not topic_label:
            # Fallback: häufigstes Label aus Personen
            if agg["labels"]:
                topic_label = agg["labels"].most_common(1)[0][0]
        if topic_id is None:
            # letzter Fallback: 2 (mathematik) existiert praktisch immer in deinem topics.json
            topic_id = "2"
            topic_label = topics.get("2", {}).get("label", "mathematik")

        start_year, end_year = pseudo_years(title)
        proj = {
            "id": stable_id_from_title(title),
            "title": title,
            "topic_id": int(topic_id) if str(topic_id).isdigit() else topic_id,
            "topic_label": topic_label,
            "start_year": int(start_year),
            "end_year": int(end_year),
            "url": "",  # unbekannt -> leer (kannst du später auffüllen)
            "people": pid_list,  # genau die person_number aus people.geojson
        }
        projects.append(proj)

    # Optional: sortieren für stabile Diffs
    projects.sort(key=lambda p: (str(p["topic_id"]), p["title"].lower()))

    # stats.json aktualisieren (nur Felder, die wir sicher wissen)
    stats = {
        "total_people": len(
            {
                str(f.get("properties", {}).get("person_number"))
                for f in feat_list
                if f.get("properties")
            }
        ),
        "total_people_geocoded": sum(
            1 for f in feat_list if f.get("geometry", {}).get("type") == "Point"
        ),
        "total_projects": len(projects),
    }

    # Schreiben
    Path(out_projects).write_text(
        json.dumps(projects, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    Path(out_stats).write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Wrote {out_projects} with {len(projects)} projects; {out_stats} updated.")


if __name__ == "__main__":
    # Aufruf: python build_projects_from_people.py people.geojson topics.json data/projects.json data/stats.json
    args = sys.argv[1:]
    main(*(args + [None] * (4 - len(args))))
