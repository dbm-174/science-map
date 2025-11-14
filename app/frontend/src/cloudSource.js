// src/sources/cloudSource.js
import { subscribe as onFilterChange, getFilters } from "./bus.js";
import { tokenize } from "./text.js";

let rows = [];
let snapshot = { words: [] }; // [{text, weight}]

export function init(data, opts={}){
  rows = Array.isArray(data) ? data : [];
  recompute(opts);
  onFilterChange(()=>{ recompute(opts); notify(); });
}

const listeners = new Set();
export function subscribe(fn){ listeners.add(fn); fn(snapshot); return () => listeners.delete(fn); }
export function getSnapshot(){ return snapshot; }
function notify(){ for(const fn of listeners) fn(snapshot); }

function recompute(opts={}){
  const { topN = 80, sources = ["title","abstract","topic"] } = opts;
  const f = getFilters();
  const topicAllow = f.topics.size ? f.topics : null;
  const personAllow = f.personIds.size ? f.personIds : null;

  const freq = new Map();
  for(const r of rows){
    if(topicAllow && !topicAllow.has(r.topic)) continue;
    if(personAllow && !personAllow.has(r.person_id)) continue;
    if(f.years && (r.year < f.years[0] || r.year > f.years[1])) continue;

    let text = "";
    if(sources.includes("title")) text += " " + (r.title||"");
    if(sources.includes("abstract")) text += " " + (r.abstract||"");
    if(sources.includes("topic")) text += " " + (r.topic||"");
    if(sources.includes("institution")) text += " " + (r.institution||"");

    const toks = tokenize(text);
    for(const w of toks){
      if(stopwords.has(w)) continue;
      freq.set(w, (freq.get(w) || 0) + 1);
    }
  }

  const words = [...freq.entries()]
    .sort((a,b)=> b[1]-a[1])
    .slice(0, topN)
    .map(([text, weight]) => ({ text, weight }));

  snapshot = { words };
}

const stopwords = new Set([
  "und","der","die","das","mit","für","ein","eine","von","auf","im","in","am",
  "zur","zum","oder","ohne","auch","sowie","bei","über","the","and","of"
]);

