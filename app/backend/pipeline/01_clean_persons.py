#!/usr/bin/env python3
import json, sys, re, os
from pathlib import Path

RAW = Path(__file__).resolve().parents[2] / "backend" / "data" / "raw"
INTERIM = Path(__file__).resolve().parents[2] / "backend" / "data" / "interim"


def normalize_address(addr: str) -> dict:
    lines = [l.strip() for l in (addr or "").splitlines() if l.strip()]
    country = ""
    city = ""
    plz = ""
    if lines:
        # Country: oft letzte Zeile
        m_country = lines[-1]
        if re.search(
            r"(deutschland|germany|österreich|austria|schweiz|switzerland|frankreich|france)$",
            m_country,
            re.I,
        ):
            country = m_country
        # PLZ Stadt (DE)
        for l in lines:
            m = re.search(r"\b(\d{5})\s+([A-Za-zÄÖÜäöüß\-\s\.]+)$", l)
            if m:
                plz, city = m.group(1), m.group(2).strip()
        # City-Fallback
        if not city:
            # vorletzte oder letzte sinnvolle Zeile als Stadt-Heuristik
            cand = lines[-2] if len(lines) >= 2 else lines[-1]
            if not re.search(r"\d", cand):
                city = cand
    return {
        "address_lines": lines,
        "address_joined": ", ".join(lines),
        "country": country,
        "city": city,
        "postal_code": plz,
    }


def main():
    in_path = sys.argv[1] if len(sys.argv) > 1 else str(RAW / "gepris_persons.json")
    out_path = INTERIM / "clean_people.json"
    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    out = []
    seen = set()
    for d in data:
        pid = str(d.get("person_number", "")).strip()
        if not pid or pid in seen:
            continue
        seen.add(pid)
        projects = d.get("project_list") or []
        if isinstance(projects, str):
            projects = [projects]
        addr = normalize_address(d.get("address", ""))
        out.append(
            {
                "person_number": pid,
                "person_name": d.get("person_name", "").strip(),
                "address": d.get("address", "").strip(),
                "address_norm": addr,
                "projects": [p for p in projects if isinstance(p, str) and p.strip()],
                "projects_count": len(
                    [p for p in projects if isinstance(p, str) and p.strip()]
                ),
                "url": d.get("url", ""),
            }
        )

    os.makedirs(INTERIM, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[01] Wrote {out_path} with {len(out)} records")


if __name__ == "__main__":
    main()
