// src/sources/mapSource.js
import { subscribe as onFilterChange, getFilters } from "./bus.js";
import { normalize } from "./text.js";

/** interne Daten */
let rows = [];   // Originaldaten
let snapshot = { type:"FeatureCollection", features: [] };

/**
 * Initialisiere mit Daten
 * @param {Array} data projects.json Zeilen
 */
export function init(data){
  rows = Array.isArray(data) ? data : [];
  recompute();
  onFilterChange(()=>{ recompute(); notify(); });
}

/** Abonnieren (für das Karten-Widget) */
const listeners = new Set();
export function subscribe(fn){ listeners.add(fn); fn(snapshot); return () => listeners.delete(fn); }
function notify(){ for(const fn of listeners) fn(snapshot); }

/** Liefert aktuelles GeoJSON */
export function getSnapshot(){ return snapshot; }

/** Filter anwenden und Features bilden (pro Person/Ort aggregiert) */
function recompute(){
  const f = getFilters();
  const topicAllow = f.topics.size ? f.topics : null;
  const personAllow = f.personIds.size ? f.personIds : null;
  const searchNeedle = normalize(f.search);

  // Gruppierung key = person_id|lat|lng
  const map = new Map();
  for(const r of rows){
    if(topicAllow && !topicAllow.has(r.topic)) continue;
    if(personAllow && !personAllow.has(r.person_id)) continue;
    if(f.years && (r.year < f.years[0] || r.year > f.years[1])) continue;
    if(searchNeedle){
      const hay = `${r.title} ${r.abstract} ${r.person_name} ${r.institution}`;
      if(!normalize(hay).includes(searchNeedle)) continue;
    }
    if(!(Number.isFinite(r.lat) && Number.isFinite(r.lng))) continue;

    const key = `${r.person_id}|${r.lat}|${r.lng}`;
    const g = map.get(key) || {
      person_id: r.person_id,
      person_name: r.person_name,
      institution: r.institution,
      lat: r.lat, lng: r.lng,
      topics: new Map(), // topic -> count
      count: 0,
      years: new Set(),
      project_ids: []
    };
    g.count++;
    g.years.add(r.year);
    g.project_ids.push(r.id);
    g.topics.set(r.topic, (g.topics.get(r.topic)||0)+1);
    map.set(key, g);
  }

  snapshot = {
    type: "FeatureCollection",
    features: [...map.values()].map(g => ({
      type: "Feature",
      geometry: { type:"Point", coordinates:[g.lng, g.lat] },
      properties: {
        person_id: g.person_id,
        person_name: g.person_name,
        institution: g.institution,
        count: g.count,
        dominant_topic: dominantTopic(g.topics),
        topics: Object.fromEntries(g.topics),
        years: [...g.years].sort(),
        project_ids: g.project_ids
      }
    }))
  };
}

function dominantTopic(topicMap){
  let best=null, n=-1;
  for(const [t,c] of topicMap.entries()){
    if(c>n){ best=t; n=c; }
  }
  return best;
}

