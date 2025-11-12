#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GEPRIS Personen-Scraper
- Crawlt Personenlisten aus GEPRIS (context=person) ODER
- gewinnt Personen-Links aus bestehenden Projekt-JSON/Projektseiten (--from-projects-json)
- Extrahiert: person_number, person_name, address (mehrzeilig), project_list (Projekttitel)
- Progress-Bar mit tqdm (optional)
"""

import argparse
import csv
import json
import re
import time
from typing import Optional, Iterable, List, Dict, Tuple, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

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


NAV_H1_BLOCKLIST = {
    "servicenavigation",
    "hauptnavigation",
    "zusatzinformationen",
    "footer",
    "suchergebnisse",
    "detailseite",
    "person",
    "zurück",
}

def get_main_container(soup: BeautifulSoup) -> Tag | BeautifulSoup:
    for sel in [
        "main[role='main']",
        "main",
        "div#content",
        "div[role='main']",
        "section#content",
        "div#main",
        "div.content",
    ]:
        node = soup.select_one(sel)
        if node:
            return node
    return soup

def _text_equals(node: Tag | NavigableString, label: str) -> bool:
    txt = ""
    if isinstance(node, NavigableString):
        txt = str(node).strip()
    elif hasattr(node, "get_text"):
        txt = node.get_text(" ", strip=True)
    return re.fullmatch(label, txt, flags=re.I) is not None

def find_label_node(container: Tag | BeautifulSoup, label: str) -> Optional[Tag]:
    # Suche ein Element, dessen sichtbarer Text exakt dem Label entspricht
    # Bevorzugt Überschriften oder starke Marker
    for el in container.select("h1,h2,h3,h4,strong,b,dt"):
        if _text_equals(el, label):
            return el
    # Fallback: exakter Textknoten irgendwo im Container
    for el in container.find_all(string=True):
        if _text_equals(el, label):
            return el.parent if hasattr(el, "parent") else None
    return None

def extract_block_after_label_multiline(soup: BeautifulSoup, label: str, stop_labels: List[str]) -> str:
    container = get_main_container(soup)
    start = find_label_node(container, label)
    if not start:
        return ""

    stop_re = re.compile(r"^(?:%s)$" % "|".join(map(re.escape, stop_labels)), re.I)

    lines: List[str] = []

    # Wir sammeln Geschwister nach 'start' bis zum nächsten Stop-Label / nächsten Heading
    for sib in start.next_siblings:
        # NavigableString
        if isinstance(sib, NavigableString):
            txt = sib.strip()
            if txt:
                if stop_re.match(txt):
                    break
                lines.append(txt)
            continue

        if not isinstance(sib, Tag):
            continue

        # Wenn das Geschwister selbst wie eine Überschrift/Label aussieht -> abbrechen
        if sib.name and sib.name.lower() in {"h1", "h2", "h3", "h4", "dt"}:
            heading_txt = sib.get_text(" ", strip=True)
            if not heading_txt or stop_re.match(heading_txt) or True:
                break

        # Text des Blocks holen – <br> als Zeilenumbrüche
        txt = sib.get_text("\n", strip=True)
        if txt:
            # Innerhalb des Blocks vor Stopp-Zeilen cutten
            parts = [p.strip() for p in re.split(r"\n+", txt)]
            cut_parts: List[str] = []
            for p in parts:
                if stop_re.match(p):
                    break
                cut_parts.append(p)
            if cut_parts:
                lines.append("\n".join(cut_parts))

        # Heuristik: eine zusammenhängende <div>/<p>/<ul>-Gruppe genügt meist
        if sib.name and sib.name.lower() in {"div", "p", "ul", "ol"}:
            if len("\n".join(lines)) > 10:
                break

    addr_raw = "\n".join([ln for ln in ("\n".join(lines)).splitlines() if ln.strip()])
    addr = re.sub(r"\n{3,}", "\n\n", addr_raw).strip()
    return addr

def extract_address(soup: BeautifulSoup) -> str:
    stop_labels = [
        "ORCID-ID",
        "ORCID",
        "Projekte",
        "Projektliste",
        "Forschungsschwerpunkte",
        "Kontakt",
        "Kontaktdaten",
        "Beteiligte",
        "Publikationen",
        "Zusatzinformationen",
    ]
    addr = extract_block_after_label_multiline(soup, label="Adresse", stop_labels=stop_labels)
    if not addr:
        addr = extract_block_after_label_multiline(soup, label="Anschrift", stop_labels=stop_labels)

    if not addr:
        # Fallback: typischer Address-Container im Inhaltsbereich
        main = get_main_container(soup)
        tag = main.find("address")
        if tag:
            addr = tag.get_text("\n", strip=True)
        if not addr:
            cand = main.select_one(".address, .anschrift, div.address, div.anschrift")
            if cand:
                addr = cand.get_text("\n", strip=True)

    if addr:
        # Alles ab erstem Stopp-Label rigoros abschneiden
        addr = re.split(
            r"\n(?:ORCID-ID|ORCID|Projekte|Projektliste|Forschungsschwerpunkte|Zusatzinformationen|Kontakt|Kontaktdaten)\b",
            addr,
            flags=re.I,
        )[0]
        # Überschrift entfernen
        addr = re.sub(r"^(Adresse|Anschrift)\s*\n+", "", addr, flags=re.I).strip()
        # gelegentliche Navigationsreste am Anfang entfernen
        nav_garbage = [
            "Direkt zum Inhalt springen",
            "Direkt zu Textvergrößerung und Kontrast springen",
            "Servicenavigation",
            "Hauptnavigation",
            "Detailseite",
        ]
        lines = [ln for ln in addr.splitlines() if ln.strip() and ln.strip() not in nav_garbage]
        return "\n".join(lines).strip()

    return ""

def parse_person_name(soup: BeautifulSoup) -> str:
    container = get_main_container(soup)
    # 1) H1 innerhalb des Inhaltsbereichs, aber mit Blockliste
    h1 = container.find("h1")
    if h1:
        name = clean_field(h1.get_text(" ", strip=True))
        if name and name.lower() not in NAV_H1_BLOCKLIST:
            return name
    # 2) Alternative Überschriften im Content
    for tag in container.select("h1, h2"):
        t = clean_field(tag.get_text(" ", strip=True))
        if t and t.lower() not in NAV_H1_BLOCKLIST and len(t) > 3:
            return t
    # 3) Microdata/Fallback
    cand = soup.select_one("[itemprop='name']")
    if cand:
        t = clean_field(cand.get_text(" ", strip=True))
        if t and t.lower() not in NAV_H1_BLOCKLIST:
            return t
    # 4) <title> als Fallback
    if soup.title and soup.title.string:
        return clean_field(re.sub(r"^\s*DFG\s*-\s*GEPRIS\s*-\s*", "", soup.title.string))
    return ""

def iter_project_titles_from_person_page(soup: BeautifulSoup) -> List[str]:
    """
    Sammelt Projekttitel über Links auf /gepris/projekt/ und dedupliziert.
    """
    titles: List[str] = []
    seen = set()
    for a in soup.select("a[href*='/gepris/projekt/']"):
        href = a.get("href") or ""
        u = urlparse(urljoin(DETAIL_BASE, href))
        if not re.match(r"^/gepris/projekt/\d+$", u.path):
            continue
        # sichtbarer Text, Fallback title-Attribut oder umgebende Heading
        title = clean_field(a.get_text(" ", strip=True)) or clean_field(a.get("title") or "")
        if not title:
            parent_h = a.find_parent(["h1", "h2", "h3"])
            if parent_h:
                title = clean_field(parent_h.get_text(" ", strip=True))
        if title and title not in seen:
            seen.add(title)
            titles.append(title)
    return titles


# ---------------------- HTTP & Listen-Handling ----------------------

def get_soup(
    session: requests.Session,
    url: str,
    params: dict | None = None,
    sleep: float = 0.0,
    debug_save: str | None = None,
) -> BeautifulSoup:
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
    if debug_save and last_text:
        with open(debug_save, "w", encoding="utf-8") as f:
            f.write(last_text)
    r.raise_for_status()
    return BeautifulSoup(last_text, "html.parser")

def build_param_variants_person(index: int, hits: int) -> List[dict | None]:
    base = {
        "language": "de",
        "hitsPerPage": str(hits),
        "index": str(index),
    }
    v1 = {"context": "person", "task": "doSearchExtended", "findButton": "historyCall", **base}
    v2 = {"context": "person", "task": "showList", **base}
    v3 = {"context": "person", **base}
    # None = GET ohne Parameter auf OCTOPUS
    return [None, v1, v2, v3]

def normalize_person_url(href: str) -> Optional[str]:
    try:
        u = urlparse(urljoin(DETAIL_BASE, href))
        if "displayMode=print" in (u.query or ""):
            return None
        if re.match(r"^/gepris/person/\d+$", u.path):
            return f"{u.scheme}://{u.netloc}{u.path}"
    except Exception:
        pass
    return None

def iter_person_links_from_list(soup: BeautifulSoup) -> Iterable[str]:
    seen = set()
    for a in soup.select("a[href*='/gepris/person/']"):
        href = a.get("href") or ""
        url = normalize_person_url(href)
        if not url or url in seen:
            continue
        seen.add(url)
        yield url


# ---------------------- Detailseite einer Person ----------------------

def parse_person_detail(session: requests.Session, url: str, sleep: float = 0.2) -> Dict[str, object]:
    time.sleep(max(0.0, sleep))
    r = session.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    m = re.search(r"/gepris/person/(\d+)", url)
    person_number = m.group(1) if m else ""

    name = parse_person_name(soup)
    address = extract_address(soup)
    project_list = iter_project_titles_from_person_page(soup)

    return {
        "person_number": person_number,
        "person_name": name,
        "address": address,
        "project_list": project_list,
        "url": url,
        "error": "",
    }


# ---------------------- Personen aus Projekten gewinnen (optional) ----------------------

def normalize_project_url(href: str) -> Optional[str]:
    try:
        u = urlparse(urljoin(DETAIL_BASE, href))
        if "displayMode=print" in (u.query or ""):
            return None
        if re.match(r"^/gepris/projekt/\d+$", u.path):
            return f"{u.scheme}://{u.netloc}{u.path}"
    except Exception:
        pass
    return None

def extract_person_links_from_project_html(soup: BeautifulSoup) -> List[str]:
    """
    Sucht in Projektseiten nach Personenlinks (/gepris/person/...) z. B. in 'Antragsteller' oder 'Beteiligte'.
    """
    links: List[str] = []
    seen = set()
    for a in soup.select("a[href*='/gepris/person/']"):
        href = a.get("href") or ""
        u = urlparse(urljoin(DETAIL_BASE, href))
        if re.match(r"^/gepris/person/\d+$", u.path):
            url = f"{u.scheme}://{u.netloc}{u.path}"
            if url not in seen:
                seen.add(url)
                links.append(url)
    return links

def collect_person_urls_from_projects(
    session: requests.Session, project_urls: List[str], sleep: float = 0.2
) -> List[str]:
    person_urls: List[str] = []
    seen: Set[str] = set()
    pbar = tqdm(total=len(project_urls), desc="Scanne Projekte auf Personen", unit="proj") if tqdm else None
    for purl in project_urls:
        try:
            time.sleep(max(0.0, sleep))
            r = session.get(purl, headers=HEADERS, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            found = extract_person_links_from_project_html(soup)
            for u in found:
                if u not in seen:
                    seen.add(u)
                    person_urls.append(u)
        except Exception:
            # Einfach überspringen
            pass
        if pbar:
            pbar.update(1)
    if pbar:
        pbar.close()
    return person_urls


# ---------------------- Crawl-Modus 1: Personenseitenlisten ----------------------

def fetch_person_list_soup(
    session: requests.Session, index: int, hits: int, sleep: float, debug: bool = False
) -> Tuple[BeautifulSoup, dict | None]:
    chosen_params = None
    soup: BeautifulSoup | None = None
    variants = build_param_variants_person(index, hits)
    for i, params in enumerate(variants):
        dbg = f"_debug_person_list_{index}_{i}.html" if debug and index == 0 else None
        soup = get_soup(
            session,
            BASE_URL,
            params=params,
            sleep=sleep if i == 0 else 0.0,
            debug_save=dbg,
        )
        if any(iter_person_links_from_list(soup)):
            chosen_params = params
            return soup, chosen_params
    assert soup is not None
    return soup, chosen_params

def crawl_persons_from_lists(max_items: int, hits: int, sleep: float) -> List[Dict[str, object]]:
    session = requests.Session()
    index = 0
    soup, chosen_params = fetch_person_list_soup(session, index, hits, sleep, debug=True)

    collected: List[Dict[str, object]] = []
    seen_links: Set[str] = set()

    pbar = tqdm(total=max_items, desc="Sammle Personen", unit="pers") if tqdm else None

    while True:
        page_links = list(iter_person_links_from_list(soup))
        new_links = [l for l in page_links if l not in seen_links]

        if not new_links and not page_links:
            txt = soup.get_text(" ", strip=True).lower()
            if "javascript" in txt and "aktivieren" in txt:
                raise RuntimeError(
                    "GEPRIS liefert eine Seite, die JavaScript verlangt. Erhöhe --sleep (2.0–3.0) und starte erneut."
                )
            break

        for link in new_links:
            if len(collected) >= max_items:
                break
            try:
                data = parse_person_detail(session, link, sleep=max(0.1, sleep / 4))
                collected.append(data)
                if pbar:
                    pbar.update(1)
                else:
                    print(f"[{len(collected)}/{max_items}] {data.get('person_name', '')[:70]}")
            except Exception as e:
                collected.append(
                    {
                        "person_number": "",
                        "person_name": "",
                        "address": "",
                        "project_list": [],
                        "url": link,
                        "error": str(e),
                    }
                )

        seen_links.update(new_links)
        if len(collected) >= max_items:
            break

        # nächste Seite
        index += hits
        if chosen_params is None:
            cand = build_param_variants_person(index, hits)[0]  # None -> nackte URL
        else:
            cand = dict(chosen_params) if chosen_params is not None else None
            if cand is not None:
                cand["index"] = str(index)
                cand["hitsPerPage"] = str(hits)

        time.sleep(sleep)
        soup = get_soup(
            session,
            BASE_URL,
            params=cand,
            sleep=0.0,
            debug_save=f"_debug_person_list_{index}.html",
        )

    if pbar:
        pbar.close()
    return collected


# ---------------------- Crawl-Modus 2: Aus Projekten gespeiste Personenseiten ----------------------

def crawl_persons_from_projects_json(projects_json_path: str, sleep: float) -> List[Dict[str, object]]:
    """
    Nimmt dein bestehendes Projekte-JSON (aus gepris_grabber.py),
    ruft die Projektseiten ab, sammelt Personen-Links und lädt anschließend die Personendetails.
    """
    with open(projects_json_path, "r", encoding="utf-8") as f:
        projects = json.load(f)
    project_urls = [p.get("url") for p in projects if isinstance(p, dict) and p.get("url")]
    project_urls = [u for u in project_urls if isinstance(u, str)]

    session = requests.Session()
    person_urls = collect_person_urls_from_projects(session, project_urls, sleep=max(0.1, sleep / 2))

    # Deduplizieren
    person_urls = list(dict.fromkeys(person_urls))

    results: List[Dict[str, object]] = []
    pbar = tqdm(total=len(person_urls), desc="Lese Personendetails", unit="pers") if tqdm else None
    for u in person_urls:
        try:
            data = parse_person_detail(session, u, sleep=max(0.1, sleep / 4))
            results.append(data)
        except Exception as e:
            results.append(
                {
                    "person_number": "",
                    "person_name": "",
                    "address": "",
                    "project_list": [],
                    "url": u,
                    "error": str(e),
                }
            )
        if pbar:
            pbar.update(1)

    if pbar:
        pbar.close()
    return results


# ---------------------- Persist ----------------------

def save_outputs(rows: List[Dict[str, object]], out_csv: str, out_json: str) -> None:
    fieldnames = [
        "person_number",
        "person_name",
        "address",
        "project_list",
        "url",
        "error",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            # project_list als durch Komma getrennte Liste für CSV
            row_out = dict(row)
            if isinstance(row_out.get("project_list"), list):
                row_out["project_list"] = ", ".join(row_out["project_list"])
            w.writerow(
                {
                    k: (
                        row.get(k, "")
                        if k != "project_list"
                        else row_out.get("project_list", "")
                    )
                    for k in fieldnames
                }
            )

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


# ---------------------- CLI ----------------------

def main():
    ap = argparse.ArgumentParser(description="GEPRIS Personen-Scraper")
    ap.add_argument("--hits", type=int, default=50, help="Treffer pro Seite (GEPRIS Personenliste)")
    ap.add_argument("--max", type=int, default=50, help="Maximale Anzahl zu sammelnder Personen (Listenmodus)")
    ap.add_argument("--sleep", type=float, default=1.0, help="Pause zwischen Anfragen (Sek.)")
    ap.add_argument("--out-csv", default="gepris_persons.csv")
    ap.add_argument("--out-json", default="gepris_persons.json")
    ap.add_argument(
        "--from-projects-json",
        default=None,
        help="Optional: Pfad zu deinem Projekte-JSON. Dann werden Personen aus den Projektseiten gewonnen.",
    )
    args = ap.parse_args()

    if args.from_projects_json:
        persons = crawl_persons_from_projects_json(args.from_projects_json, sleep=args.sleep)
    else:
        persons = crawl_persons_from_lists(max_items=args.max, hits=args.hits, sleep=args.sleep)

    save_outputs(persons, args.out_csv, args.out_json)
    print(f"Fertig: {len(persons)} Personen -> {args.out_csv} / {args.out_json}")


if __name__ == "__main__":
    main()

