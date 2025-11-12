#!/usr/bin/env python3
import os
from pathlib import Path
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import json

BASE = Path(__file__).resolve().parents[2]
PROCESSED = BASE / "backend" / "data" / "processed"
FRONTEND = BASE / "frontend"

app = FastAPI(title="GEPRIS Map Prototype", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static: serve frontend and processed JSON
app.mount("/app", StaticFiles(directory=str(FRONTEND), html=True), name="app")
app.mount("/data", StaticFiles(directory=str(PROCESSED)), name="data")


@app.get("/api/topics")
def get_topics():
    p = PROCESSED / "topics.json"
    if not p.exists():
        raise HTTPException(404, "topics.json not found")
    return JSONResponse(json.loads(p.read_text(encoding="utf-8")))


@app.get("/api/people")
def get_people(topic_id: int | None = None, q: str | None = None):
    p = PROCESSED / "people.geojson"
    if not p.exists():
        raise HTTPException(404, "people.geojson not found")
    geo = json.loads(p.read_text(encoding="utf-8"))
    feats = geo.get("features", [])
    if topic_id is not None:
        feats = [f for f in feats if f["properties"].get("topic_id") == topic_id]
    if q:
        ql = q.lower()
        feats = [
            f
            for f in feats
            if ql in f["properties"].get("person_name", "").lower()
            or any(ql in (t or "").lower() for t in f["properties"].get("projects", []))
        ]
    return JSONResponse({"type": "FeatureCollection", "features": feats})


@app.get("/")
def root():
    # Redirect to frontend
    return FileResponse(FRONTEND / "index.html")
