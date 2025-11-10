#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GEPRIS Projektlisten-Scraper
- Robuste Listenabfrage (mehrere Parameter-Varianten inkl. Fallback ohne Params)
- Detail-Extraktion inkl. Titel, Antragsteller, Fachliche Zuordnung, DFG-Verfahren, Förderung
- Optionaler Verfahren-Filter per --procedure (z. B. "Sachbeihilfen")
- Progress-Bar (tqdm, optional; fällt auf Simple-Progress zurück)
- Ignoriert Print-Ansichten, dedupliziert Projekte
"""

import argparse
import csv
import json
import re
import time
from typing import Optional, Iterable, List, Dict, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString

# ---------------------- Konfiguration ----------------------

BASE_URL = "https://gepris.dfg.de/gepris/OCTOPUS"
DETAIL_BASE = "https://gepris.dfg.de"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GEPRIS-ResearchBot/1.0; +contact@example.org)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}

# tqdm ist optional
try:
    from tqdm import tqdm
except Exception:
    tqdm = None  # type: ignore


# ---------------------- Utilities ----------------------

def clean_field(v: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (v or "").strip())


def normalize_people(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = re.sub(r"\s*[,;]\s*", "; ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s or None


def get_soup(session: requests.Session, url: str, params: dict | None = None,
             sleep: float = 0.0, debug_save: str | None = None) -> BeautifulSoup:
    if sleep:
        time.sleep(max(0.0, sleep))
    last_text = ""
    for attempt in range(3):
        r = session.get(url, params=params, headers=HEADERS, timeout=30, allow_redirects=True)
        last_text = r.text or ""
        if r.status_code == 200 and last_text:
            if debug_save:
                with open(debug_save, "w", encoding="utf-8") as f:
                    f.write(last_text)
            return BeautifulSoup(last_text, "html.parser")
        time.sleep(1.5 * (attempt + 1))
    # Letzter Inhalt zur Fehlersuche ablegen
    if debug_save and last_text:
        with open(debug_save, "w", encoding="utf-8") as f:
            f.write(last_text)
    r.raise_for_status()
    return BeautifulSoup(last_text, "html.parser")


def build_param_variants(index: int, hits: int, include_sub: bool = False) -> List[dict | None]:
    # Mehrere real existierende Varianten; None = ganz ohne Params
    base = {
        "language": "de",
        "hitsPerPage": str(hits),
        "index": str(index),
    }
    v1 = {"context": "projekt", "task": "doSearchExtended", "findButton": "historyCall", **base}
    v2 = {"context": "projekt", "task": "showList", **base}
    v3 = {"context": "projekt", **base}  # minimale Variante
    if include_sub:
        for v in (v1, v2, v3):
            if v is not None:
                # GEPRIS verwendet je nach Ansicht unterschiedliche Keys; beide setzen
                v["teilprojekte"] = "true"
                v["includeSubProjects"] = "true"
    return [None, v1, v2, v3]


def fetch_list_soup(session: requests.Session, index: int, hits: int,
                    include_sub: bool, sleep: float, debug: bool = False) -> Tuple[BeautifulSoup, dict | None]:
    chosen_params = None
    soup = None  # type: ignore
    variants = build_param_variants(index, hits, include_sub)
    for i, params in enumerate(variants):
        dbg = f"_debug_list_{index}_{i}.html" if debug and index == 0 else None
        soup = get_soup(session, BASE_URL, params=params, sleep=sleep if i == 0 else 0.0, debug_save=dbg)
        if any(iter_result_links(soup)):
            chosen_params = params
            return soup, chosen_params
    return soup, chosen_params  # type: ignore


def normalize_project_url(href: str) -> Optional[str]:
    try:
        u = urlparse(urljoin(DETAIL_BASE, href))
        if "displayMode=print" in (u.query or ""):
            return None
        # Nur reine Projektpfade /gepris/projekt/<ID>
        if re.match(r"^/gepris/projekt/\d+$", u.path):
            return f"{u.scheme}://{u.netloc}{u.path}"
    except Exception:
        pass
    return None


def iter_result_links(soup: BeautifulSoup) -> Iterable[str]:
    seen = set()
    for a in soup.select("a[href*='/gepris/projekt/']"):
        href = a.get("href")
        if not href:
            continue
        url = normalize_project_url(href)
        if not url:
            continue
        if url in seen:
            continue
        seen.add(url)
        yield url


# ---------------------- Detail-Extraktion ----------------------

def parse_title(soup: BeautifulSoup) -> str:
    # erst <h1>, dann <title>
    h1 = soup.find("h1")
    if h1:
        txt = clean_field(h1.get_text(" ", strip=True))
        if txt and txt.lower() not in {"servicenavigation", "hauptnavigation", "zusatzinformationen"}:
            return txt
    if soup.title and soup.title.string:
        return clean_field(re.sub(r"^\s*DFG\s*-\s*GEPRIS\s*-\s*", "", soup.title.string))
    return ""


def extract_after_label(soup: BeautifulSoup, body_text: str, label: str, next_labels: List[str]) -> Optional[str]:
    # 1) DOM-basiert: nächste sinnvolle Text/Link-Node nach dem Label
    lab = soup.find(string=re.compile(rf"^{re.escape(label)}\s*$", re.I))
    if lab and lab.parent:
        parts: List[str] = []
        for sib in lab.parent.next_siblings:
            name = getattr(sib, "name", None)
            if name in {"h1", "h2", "h3", "section"}:
                break
            if name in {"div", "ul", "ol", "p"}:
                txt = sib.get_text(" ", strip=True)
                if txt:
                    parts.append(txt)
                break
            if name == "a":
                parts.append(sib.get_text(" ", strip=True))
            elif name in {"span", "br"} or isinstance(sib, NavigableString):
                txt = (sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else str(sib)).strip()
                if txt:
                    parts.append(txt)
        value = clean_field(" ".join(parts))
        value = re.sub(r"\s*(Weitere Informationen.*)$", "", value, flags=re.I).strip()
        if value:
            return value

    # 2) Text-Fallback: zwischen Label und nächstem Label schneiden
    pat = rf"{re.escape(label)}\s*(.+?)\s*(?:{'|'.join(map(re.escape, next_labels))})"
    m = re.search(pat, body_text, flags=re.I | re.S)
    if m:
        value = clean_field(m.group(1))
        return value or None

    return None


def parse_detail(session: requests.Session, url: str, sleep: float = 0.2) -> Dict[str, str]:
    time.sleep(max(0.0, sleep))
    r = session.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    body_text = soup.get_text(" ", strip=True)

    # Projektnummer aus URL bevorzugen
    m_url = re.search(r"/gepris/projekt/(\d+)", url)
    project_number = m_url.group(1) if m_url else ""

    data = {
        "title": parse_title(soup),
        "project_number": project_number,
        "applicants": "",
        "field": "",
        "procedure": "",
        "funding": "",
        "url": url,
        "error": "",
    }

    # Antragsteller
    applicants = extract_after_label(
        soup, body_text, "Antragsteller",
        next_labels=["Fachliche Zuordnung", "Förderung", "Projektkennung", "Projektbeschreibung",
                     "DFG-Verfahren", "Zusatzinformationen", "Beteiligte", "Laufzeit"]
    )
    data["applicants"] = normalize_people(applicants) or ""

    # DFG-Verfahren
    procedure = extract_after_label(
        soup, body_text, "DFG-Verfahren",
        next_labels=["Zusatzinformationen", "Projektbeschreibung", "Förderung", "Projektkennung",
                     "Fachliche Zuordnung", "Beteiligte", "Laufzeit"]
    )
    data["procedure"] = clean_field(procedure or "")

    # Fachliche Zuordnung
    field_val = extract_after_label(
        soup, body_text, "Fachliche Zuordnung",
        next_labels=["Förderung", "Projektkennung", "Projektbeschreibung", "DFG-Verfahren",
                     "Zusatzinformationen", "Antragsteller", "Laufzeit"]
    )
    data["field"] = clean_field(field_val or "")

    # Förderung
    funding = extract_after_label(
        soup, body_text, "Förderung",
        next_labels=["Projektkennung", "Projektbeschreibung", "DFG-Verfahren", "Fachliche Zuordnung",
                     "Zusatzinformationen", "Antragsteller", "Laufzeit"]
    )
    data["funding"] = clean_field(funding or "")

    return data


# ---------------------- Crawl + Persist ----------------------

def crawl(max_items: int, hits: int, sleep: float, include_subprojects: bool,
          procedure_filter: Optional[str]) -> List[Dict[str, str]]:
    session = requests.Session()

    index = 0
    soup, chosen_params = fetch_list_soup(session, index, hits, include_subprojects, sleep, debug=True)

    collected: List[Dict[str, str]] = []
    seen_links, seen_projects = set(), set()
    processed = 0

    # Progress-Bar vorbereiten: wir zählen "gesammelt" (nicht "gesehen")
    pbar = None
    if tqdm is not None:
        pbar = tqdm(total=max_items, desc="Sammle Projekte", unit="proj")

    while True:
        page_links = list(iter_result_links(soup))
        new_links = [l for l in page_links if l not in seen_links]

        if not new_links and not page_links:
            txt = soup.get_text(" ", strip=True).lower()
            if "javascript" in txt and "aktivieren" in txt:
                raise RuntimeError("GEPRIS liefert eine Seite, die JavaScript verlangt. Erhöhe --sleep (2.0–3.0) und starte erneut.")
            break

        for link in new_links:
            if len(collected) >= max_items:
                break
            processed += 1
            try:
                data = parse_detail(session, link, sleep=max(0.1, sleep / 4))
                key = data.get("project_number") or link
                if key in seen_projects:
                    continue

                # Verfahren-Filter (Teilstring, case-insensitive)
                if procedure_filter:
                    if not data.get("procedure"):
                        # Falls das Feld leer ist, nicht zählen
                        pass
                    elif procedure_filter.lower() not in data["procedure"].lower():
                        # Nicht passend -> überspringen
                        seen_projects.add(key)
                        seen_links.add(link)
                        # Fortschrittstext bei tqdm anzeigen
                        if pbar is not None:
                            pbar.set_postfix(processed=processed, matched=len(collected))
                        continue

                seen_projects.add(key)
                collected.append(data)
                if pbar is not None:
                    pbar.update(1)
                    pbar.set_postfix(processed=processed, matched=len(collected))
                else:
                    # Simple Progress Fallback
                    print(f"[{len(collected)}/{max_items}] {data.get('title','')[:70]}")

            except Exception as e:
                collected.append({
                    "title": "",
                    "project_number": "",
                    "applicants": "",
                    "field": "",
                    "procedure": "",
                    "funding": "",
                    "url": link,
                    "error": str(e),
                })
                if pbar is not None:
                    pbar.update(1)
                    pbar.set_postfix(processed=processed, matched=len(collected))

        seen_links.update(new_links)
        if len(collected) >= max_items:
            break

        # Nächste Seite: dasselbe Param-Schema wiederverwenden
        index += hits
        if chosen_params is None:
            cand = build_param_variants(index, hits, include_subprojects)[0]  # None -> nackte URL
        else:
            cand = dict(chosen_params) if chosen_params is not None else None
            if cand is not None:
                cand["index"] = str(index)
                cand["hitsPerPage"] = str(hits)

        time.sleep(sleep)
        soup = get_soup(session, BASE_URL, params=cand, sleep=0.0, debug_save=f"_debug_list_{index}.html")

    if pbar is not None:
        pbar.close()
    return collected


def save_outputs(rows: List[Dict[str, str]], out_csv: str, out_json: str) -> None:
    fieldnames = ["title", "project_number", "applicants", "field", "procedure", "funding", "url", "error"]

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: clean_field(row.get(k, "")) for k in fieldnames})

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


# ---------------------- CLI ----------------------

def main():
    ap = argparse.ArgumentParser(description="GEPRIS Projektlisten-Scraper (mit Progress-Bar und Verfahren-Filter)")
    ap.add_argument("--hits", type=int, default=50, help="Treffer pro Seite (GEPRIS)")
    ap.add_argument("--max", type=int, default=10, help="Maximale Anzahl zu sammelnder Projekte (nach Filter!)")
    ap.add_argument("--sleep", type=float, default=1.0, help="Pause zwischen Anfragen (Sek.)")
    ap.add_argument("--include-subprojects", action="store_true", help="Teilprojekte mit aufnehmen")
    ap.add_argument("--procedure", default=None,
                    help="Nur Projekte sammeln, deren DFG-Verfahren diesen Text enthält (z. B. 'Sachbeihilfen').")
    ap.add_argument("--out-csv", default="gepris_projekte.csv")
    ap.add_argument("--out-json", default="gepris_projekte.json")
    args = ap.parse_args()

    rows = crawl(
        max_items=args.max,
        hits=args.hits,
        sleep=args.sleep,
        include_subprojects=args.include_subprojects,
        procedure_filter=args.procedure,
    )
    save_outputs(rows, args.out_csv, args.out_json)
    print(f"Fertig: {len(rows)} Projekte gespeichert -> {args.out_csv} / {args.out_json}")


if __name__ == "__main__":
    main()

