// src/mapSourcePeople.js
import { subscribe as onFilterChange, getFilters } from "./bus.js";

let features = [];
let snapshot = { type: "FeatureCollection", features: [] };
const listeners = [];

function notify() {
  for (const fn of listeners) fn(snapshot);
}

function matchesFilters(f, filters) {
  const p = f.properties || {};
  // Topics
  if (filters.topics && filters.topics.size) {
    const topics = Array.isArray(p.topics) ? p.topics : (p.topic ? [p.topic] : []);
    const has = topics.some(t => filters.topics.has(String(t).toLowerCase()));
    if (!has) return false;
  }
  // Years
  if (filters.years && Array.isArray(p.years)) {
    const [minY, maxY] = filters.years; // z.B. [2000, 2025]
    const anyInRange = p.years.some(y => y >= minY && y <= maxY);
    if (!anyInRange) return false;
  }
  // Search
  if (filters.search) {
    const q = String(filters.search).toLowerCase();
    const hay = [
      p.name, p.institution, p.city, p.country,
      ...(Array.isArray(p.topics) ? p.topics : [])
    ].filter(Boolean).join(" ").toLowerCase();
    if (!hay.includes(q)) return false;
  }
  // Person-Whitelist
  if (filters.personIds && filters.personIds.size) {
    const id = p.id ?? p.personId ?? p.uuid;
    if (!filters.personIds.has(id)) return false;
  }
  return true;
}

function recompute() {
  const filters = getFilters();
  const feats = features.filter(f => matchesFilters(f, filters));
  snapshot = { type: "FeatureCollection", features: feats };
}

export function initPeople(peopleGeo) {
  features = Array.isArray(peopleGeo?.features) ? peopleGeo.features : [];
  recompute();
  notify(); // erste Ausgabe
  // Bei jeder Filteränderung neu berechnen + emittieren
  onFilterChange(() => { recompute(); notify(); });
}

export function subscribe(fn) {
  if (typeof fn === "function") {
    listeners.push(fn);
    // sofortigen Snapshot liefern
    fn(snapshot);
  }
}

export function getSnapshot() {
  return snapshot;
}

