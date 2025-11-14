// src/sources/resultsSource.js
import { subscribe as onFilterChange, getFilters } from "./bus.js";
import { normalize } from "./text.js";

let rows = [];
let snapshot = { total:0, page:1, pageSize:25, sort:"year:desc", items:[] };

export function init(data, opts={}){
  rows = Array.isArray(data) ? data : [];
  snapshot.pageSize = opts.pageSize ?? 25;
  snapshot.sort = opts.sort ?? "year:desc";
  recompute();
  onFilterChange(()=>{ recompute(); notify(); });
}

const listeners = new Set();
export function subscribe(fn){ listeners.add(fn); fn(snapshot); return () => listeners.delete(fn); }
export function getSnapshot(){ return snapshot; }
function notify(){ for(const fn of listeners) fn(snapshot); }

/** Externe Steuerung (z.B. Klick in der Liste) */
export function setPage(p){ snapshot.page = Math.max(1, p|0); recompute(); notify(); }
export function setSort(s){ snapshot.sort = s; recompute(); notify(); }

function recompute(){
  const f = getFilters();
  const topicAllow = f.topics.size ? f.topics : null;
  const personAllow = f.personIds.size ? f.personIds : null;
  const searchNeedle = normalize(f.search);

  let arr = rows.filter(r=>{
    if(topicAllow && !topicAllow.has(r.topic)) return false;
    if(personAllow && !personAllow.has(r.person_id)) return false;
    if(f.years && (r.year < f.years[0] || r.year > f.years[1])) return false;
    if(searchNeedle){
      const hay = `${r.title} ${r.abstract} ${r.person_name} ${r.institution}`;
      if(!normalize(hay).includes(searchNeedle)) return false;
    }
    return true;
  });

  // Sortierung: "year:desc", "title:asc", "topic:asc", …
  const [field, dir] = snapshot.sort.split(":");
  arr.sort((a,b)=>{
    const va = a[field], vb = b[field];
    if(va===vb) return 0;
    return (va>vb ? 1 : -1) * (dir==="desc" ? -1 : 1);
  });

  // Pagination
  const total = arr.length;
  const start = (snapshot.page-1)*snapshot.pageSize;
  const items = arr.slice(start, start+snapshot.pageSize);

  snapshot = { ...snapshot, total, items };
}

