// src/sources/timeSource.js
import { subscribe as onFilterChange, getFilters } from "./bus.js";
import { normalize } from "./text.js";

let rows = [];
let snapshot = { years: [], series: [] }; // series: [{key:'KI', data:[counts]}]

export function init(data){
  rows = Array.isArray(data) ? data : [];
  recompute();
  onFilterChange(()=>{ recompute(); notify(); });
}

const listeners = new Set();
export function subscribe(fn){ listeners.add(fn); fn(snapshot); return () => listeners.delete(fn); }
export function getSnapshot(){ return snapshot; }
function notify(){ for(const fn of listeners) fn(snapshot); }

function recompute(){
  const f = getFilters();
  // Bestimme Year-Range aus Filter oder Daten
  const minY = f.years?.[0] ?? Math.min(...rows.map(r=>r.year));
  const maxY = f.years?.[1] ?? Math.max(...rows.map(r=>r.year));
  const years = [];
  for(let y=minY; y<=maxY; y++) years.push(y);

  // Sammele Themen
  const topicSet = new Set(rows.map(r=>r.topic));

  // Zähler [topic][year] -> count
  const counts = new Map();
  for(const t of topicSet) counts.set(t, new Map(years.map(y=>[y,0])));

  const topicAllow = f.topics.size ? f.topics : null;
  const personAllow = f.personIds.size ? f.personIds : null;
  const searchNeedle = normalize(f.search);

  for(const r of rows){
    if(r.year<minY || r.year>maxY) continue;
    if(topicAllow && !topicAllow.has(r.topic)) continue;
    if(personAllow && !personAllow.has(r.person_id)) continue;
    if(searchNeedle){
      const hay = `${r.title} ${r.abstract} ${r.person_name} ${r.institution}`;
      if(!normalize(hay).includes(searchNeedle)) continue;
    }
    counts.get(r.topic)?.set(r.year, counts.get(r.topic).get(r.year)+1);
  }

  const series = [...counts.entries()]
    .filter(([t]) => !topicAllow || topicAllow.has(t))
    .map(([key, map]) => ({ key, data: years.map(y => map.get(y)||0) }));

  snapshot = { years, series };
}

