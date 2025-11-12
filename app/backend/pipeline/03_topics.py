#!/usr/bin/env python3
import json, math
from pathlib import Path
from collections import Counter
from typing import List, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

BASE = Path(__file__).resolve().parents[2]
INTERIM = BASE / "backend" / "data" / "interim"
PROCESSED = BASE / "backend" / "data" / "processed"


def choose_k(n_docs: int) -> int:
    if n_docs <= 8:
        return max(1, n_docs // 2)
    return max(4, min(20, int(round(math.sqrt(n_docs / 2)))))


def top_terms_per_cluster(vect, X, labels, topn=5):
    terms = vect.get_feature_names_out()
    out = {}
    for cid in set(labels):
        idx = (labels == cid).nonzero()[0]
        centroid = X[idx].mean(axis=0)
        arr = centroid.A1 if hasattr(centroid, "A1") else centroid
        top_idx = arr.argsort()[-topn:][::-1]
        out[cid] = [terms[i] for i in top_idx if arr[i] > 0]
    return out


def hue_for_cluster(cid: int, k: int) -> str:
    # evenly spaced hues (HSL -> hex)
    import colorsys

    h = (cid / max(1, k)) % 1.0
    r, g, b = colorsys.hls_to_rgb(h, 0.55, 0.6)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def main():
    in_path = INTERIM / "geocoded_people.json"
    with open(in_path, "r", encoding="utf-8") as f:
        people = json.load(f)

    docs = [
        " . ".join(p.get("projects", [])) or p.get("person_name", "") for p in people
    ]
    vect = TfidfVectorizer(
        ngram_range=(1, 2), max_features=20000, stop_words=("german", "english")
    )
    X = vect.fit_transform(docs)
    k = choose_k(len(docs))
    km = KMeans(n_clusters=k, n_init="auto", random_state=42)
    labels = km.fit_predict(X)

    terms = top_terms_per_cluster(vect, X, labels, topn=6)

    # cluster label = top terms joined
    topics = []
    for cid in range(k):
        label = ", ".join(terms.get(cid, [])[:3]) or f"Topic {cid}"
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

    # attach to people
    for i, p in enumerate(people):
        cid = int(labels[i])
        topic = next(t for t in topics if t["id"] == cid)
        p["topic_id"] = cid
        p["topic_label"] = topic["label"]
        p["color"] = topic["color"]

    PROCESSED.mkdir(parents=True, exist_ok=True)
    with open(PROCESSED / "topics.json", "w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)
    with open(INTERIM / "topics_people.json", "w", encoding="utf-8") as f:
        json.dump(people, f, ensure_ascii=False, indent=2)
    print(f"[03] Wrote topics.json with k={k} topics")


if __name__ == "__main__":
    main()
