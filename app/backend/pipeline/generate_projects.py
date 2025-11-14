#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Erzeugt Demo-Dateien für die rein statische App:
- data/projects.json   (id, title, topic_id, start_year, end_year, url, people[])
- data/topics.json     (id, label, color)
- optional: data/people_projects.json {person_number: [project_id,...]}

Eingaben:
- gepris_projekte.json  (dein Rohdump)
- optional: data/people.geojson       (für Person-Verknüpfung)
- optional: tools/people_aliases.json (Namensalias -> person_number Mapping)

Aufruf:
  python tools/generate_projects.py --in gepris_projekte.json --out data

Stand: 2025-11-13
"""

from __future__ import annotations
import json, re, math, argparse, sys, pathlib, itertools, unicodedata
from collections import defaultdict

# ---- Utilities ----

THIS_YEAR = 2025  # Für "seit XXXX" -> [XXXX, THIS_YEAR]


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return s


def first_topic_label(field: str) -> str:
    """
    Reduziert das lange DFG-Feld auf einen kompakten Topic-Label.
    Heuristik:
      - trenne an ' - ' oder ','; nimm das erste Segment
      - trimme Mehrfach-Leerzeichen
    """
    if not field:
        return "Sonstiges"
    # häufiges Muster: "Anorganische Molekülchemie - Synthese, Charakterisierung"
    seg = re.split(r"\s*-\s*|,", field.strip(), maxsplit=1)[0]
    seg = re.sub(r"\s+", " ", seg).strip()
    return seg or "Sonstiges"


def parse_years(funding: str) -> tuple[int | None, int | None]:
    """
    Erkennt typische DFG-Formulierungen:
      - 'Förderung seit 2018'            -> (2018, THIS_YEAR)
      - 'Förderung von 2018 bis 2022'    -> (2018, 2022)
      - '1999 bis 2002'                  -> (1999, 2002)
      - 'Förderung von 2004 bis 2005'    -> (2004, 2005)
      - 'Förderung von 2019 bis 2020, ...'
      - 'bis 3/2022' -> extrahiere 2022
    Fallback: min/max aller 4-stelligen Jahreszahlen im Text.
    """
    if not funding:
        return (None, None)
    txt = funding.strip()

    # seit YYYY
    m = re.search(r"seit\s+(\d{4})", txt)
    if m:
        y0 = int(m.group(1))
        return (y0, THIS_YEAR)

    # von YYYY bis YYYY
    m = re.search(r"von\s+(\d{4})\s+bis\s+(\d{4})", txt)
    if m:
        return (int(m.group(1)), int(m.group(2)))

    # YYYY bis YYYY (ohne "von")
    m = re.search(r"(\d{4})\s*[-–]?\s*bis\s*(\d{4})", txt)
    if m:
        return (int(m.group(1)), int(m.group(2)))

    # catch-all: alle Jahreszahlen
    years = [int(y) for y in re.findall(r"(19|20)\d{2}", txt)]
    # Achtung: obiges findet nur '19'/'20'. Besser:
    years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", txt)]
    if years:
        return (min(years), max(years))
    return (None, None)


def distinct_colors(n: int) -> list[str]:
    """
    Erzeuge n gut unterscheidbare HSL-Farben als Hex.
    """

    def hsl_to_hex(h, s, l):
        # h: 0..360, s/l: 0..1
        c = (1 - abs(2 * l - 1)) * s
        x = c * (1 - abs(((h / 60) % 2) - 1))
        m = l - c / 2
        r_, g_, b_ = (0, 0, 0)
        if 0 <= h < 60:
            r_, g_, b_ = c, x, 0
        elif 60 <= h < 120:
            r_, g_, b_ = x, c, 0
        elif 120 <= h < 180:
            r_, g_, b_ = 0, c, x
        elif 180 <= h < 240:
            r_, g_, b_ = 0, x, c
        elif 240 <= h < 300:
            r_, g_, b_ = x, 0, c
        else:
            r_, g_, b_ = c, 0, x
        r = round((r_ + m) * 255)
        g = round((g_ + m) * 255)
        b = round((b_ + m) * 255)
        return f"#{r:02x}{g:02x}{b:02x}"

    colors = []
    for i in range(n):
        h = (i * 360 / max(1, n)) % 360
        colors.append(hsl_to_hex(h, 0.6, 0.55))
    return colors


TITLE_PREFIXES = [
    r"Professor(?:in)?(?:\s+Dr\.?-?(?:Ing\.?)?)?",
    r"Privatdozent(?:in)?(?:\s+Dr\.?)?",
    r"Dr\.?(?:-Ing\.)?",
    r"Ph\.?D\.?",
    r"Professor(?:in)?",
]


def normalize_person_name(name: str) -> str:
    """
    Entfernt Titel/Grade und trimmt; 'in Professorin' aus DFG-Formulierungen ebenso.
    Trennt Mehrfachnennungen nicht – dafür benutze split_applicants().
    """
    n = name.strip()
    # Entferne irritierende Präfixe wie "innen / Antragsteller"
    n = re.sub(r"\b(innen\s*/\s*)?Antragsteller(?:innen)?\b", "", n, flags=re.I)
    # Entferne Titel
    rx = r"(?i)\b(?:" + "|".join(TITLE_PREFIXES) + r")\b\.?"
    n = re.sub(rx, "", n)
    # Mehrfach-Leerzeichen
    n = re.sub(r"\s+", " ", n).strip(" ;,")
    return n


def split_applicants(raw: str) -> list[str]:
    """
    Zerlegt das Applicants-Feld an ';' oder ' ; ' und ' , seit ...' und entfernt Doppelungen.
    """
    if not raw:
        return []
    # Zerlegen primär an ';'
    parts = re.split(r"\s*;\s*", raw.strip())
    # Entferne Zusätze wie ", seit 10/2012"
    parts = [
        re.sub(r",\s*seit\s*\d{1,2}/\d{4}.*$", "", p, flags=re.I).strip() for p in parts
    ]
    # Normalize
    parts = [normalize_person_name(p) for p in parts if p]
    # Duplikate raus
    seen, out = set(), []
    for p in parts:
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out


# ---- Personen-Verknüpfung (optional) ----


def load_people_index(people_geojson_path: pathlib.Path) -> dict[str, dict]:
    with people_geojson_path.open("r", encoding="utf-8") as f:
        gj = json.load(f)
    idx = {}
    for feat in gj.get("features", []):
        props = feat.get("properties", {})
        name = props.get("person_name") or ""
        key = normalize_person_name(name).lower()
        if key:
            idx[key] = {"person_number": props.get("person_number"), "name": name}
    return idx


def link_applicants_to_people(
    applicants: list[str], idx: dict[str, dict], alias_map: dict[str, str] | None = None
) -> list[str]:
    """
    Versucht exakte Namens-Matches; optional Aliase. Für robustere Zuordnung kann
    man rapidfuzz (partial_ratio > 90) einsetzen.
    """
    people_ids = []
    for a in applicants:
        key = normalize_person_name(a).lower()
        # Alias zuerst
        if alias_map and key in alias_map:
            people_ids.append(alias_map[key])
            continue
        if key in idx and idx[key].get("person_number"):
            people_ids.append(idx[key]["person_number"])
    # eindeutige
    out = []
    seen = set()
    for pid in people_ids:
        if pid and pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out


# ---- Hauptgenerator ----


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--in", dest="inp", required=True, help="Pfad zu gepris_projekte.json"
    )
    ap.add_argument(
        "--out", dest="outdir", default="data", help="Zielordner (Default: data)"
    )
    ap.add_argument(
        "--people",
        dest="people",
        default="data/people.geojson",
        help="optional: people.geojson für Verknüpfung",
    )
    ap.add_argument(
        "--aliases",
        dest="aliases",
        default="tools/people_aliases.json",
        help="optional: Alias-Mapping (name->person_number)",
    )
    ap.add_argument(
        "--overwrite-topics",
        action="store_true",
        help="bestehendes data/topics.json ignorieren und neu erzeugen",
    )
    args = ap.parse_args()

    inp = pathlib.Path(args.inp)
    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    with inp.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    # 1) Topic-Labels aus 'field' extrahieren
    topic_labels = []
    for row in raw:
        topic_labels.append(first_topic_label(row.get("field", "") or "Sonstiges"))
    # stabile Reihenfolge
    unique_labels = []
    seen = set()
    for lbl in topic_labels:
        if lbl not in seen:
            seen.add(lbl)
            unique_labels.append(lbl)

    # Falls bereits topics.json existiert und nicht überschrieben werden soll, benutze es
    topics_path = outdir / "topics.json"
    topics = []
    label_to_id = {}
    if topics_path.exists() and not args.overwrite_topics:
        with topics_path.open("r", encoding="utf-8") as f:
            topics = json.load(f)
        label_to_id = {t["label"]: t["id"] for t in topics}
        # Ergänze fehlende Labels, falls neue auftauchen
        missing = [lbl for lbl in unique_labels if lbl not in label_to_id]
        if missing:
            start_id = max((t["id"] for t in topics), default=0) + 1
            colors = distinct_colors(len(missing))
            for i, lbl in enumerate(missing):
                tid = start_id + i
                topics.append({"id": tid, "label": lbl, "color": colors[i]})
                label_to_id[lbl] = tid
    else:
        colors = distinct_colors(len(unique_labels))
        topics = [
            {"id": i + 1, "label": lbl, "color": colors[i]}
            for i, lbl in enumerate(unique_labels)
        ]
        label_to_id = {t["label"]: t["id"] for t in topics}

    # 2) Optional: Personenindex laden
    people_idx = {}
    alias_map = {}
    people_path = pathlib.Path(args.people)
    aliases_path = pathlib.Path(args.aliases)
    if people_path.exists():
        try:
            people_idx = load_people_index(people_path)
        except Exception as e:
            print(f"[WARN] Konnte people.geojson nicht laden: {e}", file=sys.stderr)
    if aliases_path.exists():
        try:
            with aliases_path.open("r", encoding="utf-8") as f:
                alias_map = {
                    normalize_person_name(k).lower(): v for k, v in json.load(f).items()
                }
        except Exception as e:
            print(
                f"[WARN] Konnte people_aliases.json nicht laden: {e}", file=sys.stderr
            )

    # 3) Projekte bauen
    projects = []
    ppl_links = defaultdict(list)  # person_number -> [project_id]
    for row in raw:
        pid = str(row.get("project_number") or "").strip()
        if not pid:
            # Fallback: slug(title)
            pid = slug(row.get("title", "")) or f"prj_{len(projects) + 1}"

        title = (row.get("title") or "").strip()
        url = (row.get("url") or "").strip()

        topic_label = first_topic_label(row.get("field", "") or "Sonstiges")
        topic_id = label_to_id.get(topic_label)

        y0, y1 = parse_years(row.get("funding", "") or "")
        # Falls gar nichts erkannt: None lassen; Frontend filtert dann einfach nicht nach Zeit
        if y0 is None and y1 is None:
            # häufig hilft: letzte vierstellige Zahl = Start oder Endjahr?
            pass

        applicants = split_applicants(row.get("applicants", "") or "")
        people = []
        if people_idx:
            people = link_applicants_to_people(applicants, people_idx, alias_map)
            for pn in people:
                ppl_links[pn].append(pid)

        projects.append(
            {
                "id": pid,
                "title": title,
                "topic_id": topic_id,
                "topic_label": topic_label,
                "start_year": y0,
                "end_year": y1,
                "url": url,
                "people": people,
            }
        )

    # 4) Schreiben
    with (outdir / "projects.json").open("w", encoding="utf-8") as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)
    with (outdir / "topics.json").open("w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)

    if ppl_links:
        with (outdir / "people_projects.json").open("w", encoding="utf-8") as f:
            json.dump(ppl_links, f, ensure_ascii=False, indent=2)

    # 5) Kurzer Report
    total = len(projects)
    with_years = sum(1 for p in projects if p["start_year"] is not None)
    with_people = sum(1 for p in projects if p["people"])
    print(
        f"[OK] projects.json: {total} Projekte (davon {with_years} mit Jahresangaben, {with_people} mit Personenverknüpfung)"
    )
    print(f"[OK] topics.json: {len(topics)} Topics")
    if ppl_links:
        print(f"[OK] people_projects.json: {len(ppl_links)} Personen mit Projekten")


if __name__ == "__main__":
    main()
