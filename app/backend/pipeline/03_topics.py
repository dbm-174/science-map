#!/usr/bin/env python3
import json, math, sys
from pathlib import Path
from collections import Counter

from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
from sklearn.cluster import KMeans
import numpy as np

BASE = Path(__file__).resolve().parents[2]
INTERIM = BASE / "backend" / "data" / "interim"
PROCESSED = BASE / "backend" / "data" / "processed"

GERMAN_STOPWORDS = {
    "und",
    "oder",
    "aber",
    "denn",
    "dass",
    "daß",
    "die",
    "der",
    "das",
    "ein",
    "eine",
    "einer",
    "einem",
    "einen",
    "mit",
    "ohne",
    "vom",
    "von",
    "im",
    "in",
    "auf",
    "an",
    "am",
    "als",
    "auch",
    "sowie",
    "zu",
    "zum",
    "zur",
    "für",
    "ist",
    "sind",
    "war",
    "waren",
    "wird",
    "werden",
    "werden",
    "wurde",
    "wurden",
    "bei",
    "durch",
    "nach",
    "vor",
    "zwischen",
    "über",
    "unter",
    "gegen",
    "entlang",
    "bis",
    "seit",
    "aus",
    "noch",
    "nur",
    "mehr",
    "weniger",
    "dies",
    "diese",
    "dieser",
    "dieses",
    "jener",
    "jene",
    "jenes",
    "wir",
    "ihr",
    "sie",
    "man",
    "er",
    "es",
    "einerseits",
    "andererseits",
    "z.b",
    "bzw",
    "etc",
    "et al",
    "u.a",
    "sowie",
    "inkl",
    "inklusive",
}


def choose_k(n_docs: int) -> int:
    if n_docs <= 2:
        return 1
    if n_docs <= 8:
        return max(1, n_docs // 2)
    return max(4, min(20, int(round(math.sqrt(max(1, n_docs) / 2)))))


def top_terms_per_cluster(vect, X, labels, topn=5):
    terms = vect.get_feature_names_out()
    out = {}
    for cid in sorted(set(labels)):
        idx = np.where(labels == cid)[0]
        if idx.size == 0:
            out[cid] = []
            continue
        centroid = X[idx].mean(axis=0)
        arr = centroid.A1 if hasattr(centroid, "A1") else np.asarray(centroid).ravel()
        if arr.size == 0:
            out[cid] = []
            continue
        top_idx = np.argsort(arr)[-topn:][::-1]
        out[cid] = [terms[i] for i in top_idx if arr[i] > 0]
    return out


def hue_for_cluster(cid: int, k: int) -> str:
    import colorsys

    h = (cid / max(1, k)) % 1.0
    r, g, b = colorsys.hls_to_rgb(h, 0.55, 0.6)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def main():
    in_path = INTERIM / "geocoded_people.json"
    if not in_path.exists():
        print(
            f"[03] ERROR: {in_path} nicht gefunden. Vorher 01_clean_persons.py und 02_geocode.py ausführen.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(in_path, "r", encoding="utf-8") as f:
        people = json.load(f)

    # Dokument je Person: alle Projekttitel (Fallback: Name)
    docs = []
    for p in people:
        projs = [t for t in (p.get("projects") or []) if isinstance(t, str)]
        text = " . ".join(projs).strip()
        if not text:
            text = p.get("person_name", "") or ""
        docs.append(text)

    # Falls alles leer -> Dummy-Label
    if not any(d.strip() for d in docs):
        topics = [
            {
                "id": 0,
                "label": "Allgemein",
                "color": "#8888cc",
                "count": len(people),
                "keywords": [],
            }
        ]
        for p in people:
            p["topic_id"] = 0
            p["topic_label"] = topics[0]["label"]
            p["color"] = topics[0]["color"]
        PROCESSED.mkdir(parents=True, exist_ok=True)
        (PROCESSED / "topics.json").write_text(
            json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (INTERIM / "topics_people.json").write_text(
            json.dumps(people, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[03] Alle Dokumente leer – alles in ein Thema gruppiert.")
        return

    # Stopwords: Englisch (sklearn) + kleine deutsche Liste
    stop_words = set(ENGLISH_STOP_WORDS) | GERMAN_STOPWORDS

    vect = TfidfVectorizer(
        ngram_range=(1, 2),
        max_features=20000,
        stop_words=list(stop_words),
        lowercase=True,
        strip_accents="unicode",
    )
    X = vect.fit_transform(docs)

    # k bestimmen, aber nicht größer als Anzahl non-empty Dokumente
    nnz_docs = int((X.sum(axis=1) > 0).A1.sum())
    if nnz_docs == 0:
        # alle Vektoren leer -> fallback wie oben
        topics = [
            {
                "id": 0,
                "label": "Allgemein",
                "color": "#8888cc",
                "count": len(people),
                "keywords": [],
            }
        ]
        for p in people:
            p["topic_id"] = 0
            p["topic_label"] = topics[0]["label"]
            p["color"] = topics[0]["color"]
        PROCESSED.mkdir(parents=True, exist_ok=True)
        (PROCESSED / "topics.json").write_text(
            json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (INTERIM / "topics_people.json").write_text(
            json.dumps(people, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[03] Alle TF-IDF-Vektoren leer – alles in ein Thema gruppiert.")
        return

    k = min(choose_k(len(docs)), max(1, nnz_docs))
    km = KMeans(n_clusters=k, n_init=10, random_state=42)
    labels = km.fit_predict(X)

    terms = top_terms_per_cluster(vect, X, labels, topn=6)

    topics = []
    for cid in range(k):
        label = ", ".join(terms.get(cid, [])[:3]) or f"Thema {cid}"
        color = hue_for_cluster(cid, k)
        count = int((labels == cid).sum())
        topics.append(
            {
                "id": cid,
                "label": label,
                "color": color,
                "count": count,
                "keywords": terms.get(cid, []),
            }
        )

    for i, p in enumerate(people):
        cid = int(labels[i])
        t = topics[cid]
        p["topic_id"] = cid
        p["topic_label"] = t["label"]
        p["color"] = t["color"]

    PROCESSED.mkdir(parents=True, exist_ok=True)
    (PROCESSED / "topics.json").write_text(
        json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (INTERIM / "topics_people.json").write_text(
        json.dumps(people, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[03] topics.json geschrieben (k={k}, Personen={len(people)})")


if __name__ == "__main__":
    main()
