// src/util/text.js
export function normalize(s){
  return (s||"")
    .toLowerCase()
    .normalize("NFD").replace(/\p{Diacritic}/gu,"")
    .replace(/[^a-z0-9äöüß\s\-]/gi," ")
    .replace(/\s+/g," ")
    .trim();
}

export function tokenize(s){
  const t = normalize(s);
  if(!t) return [];
  return t.split(/\s+/).filter(w => w.length > 2); // min Länge 3
}

