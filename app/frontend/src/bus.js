// src/bus.js – sehr kleines zentrales Filter-Bus
let filters = {
  topics: new Set(),
  years: null,          // oder [min,max]
  search: "",
  personIds: new Set()
};

const listeners = [];

export function setFilters(patch = {}) {
  // Patch anwenden (Sets korrekt behandeln)
  if (patch.topics instanceof Set) filters.topics = patch.topics;
  if (Array.isArray(patch.years) || patch.years === null) filters.years = patch.years;
  if (typeof patch.search === "string") filters.search = patch.search;
  if (patch.personIds instanceof Set) filters.personIds = patch.personIds;

  // Alle informieren
  for (const fn of listeners) fn(filters);
}

export function subscribe(fn) {
  if (typeof fn === "function") listeners.push(fn);
}

export function getFilters() {
  return filters;
}

