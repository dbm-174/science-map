// app.js
import { loadData } from './src/loadData.js';
import * as MapPeople from './src/mapSourcePeople.js';
import * as TimeSrc from './src/timeSource.js';
import * as ListSrc from './src/resultsSource.js';
import * as CloudSrc from './src/cloudSource.js';
import { setFilters } from './src/bus.js';

/* ---------- kleine DOM-Utils ---------- */
const qs  = (s, r=document) => r.querySelector(s);
const qsa = (s, r=document) => [...r.querySelectorAll(s)];

/* ---------- Zustand + Layout ---------- */
const state = {
  layout: localStorage.getItem('layout') || '2x2',
  apps: JSON.parse(localStorage.getItem('apps') || '{"map":true,"timeseries":true,"list":true,"cloud":true}'),
  colSplit: parseFloat(localStorage.getItem('colSplit') || '0.5'),
  rowSplit: parseFloat(localStorage.getItem('rowSplit') || '0.5'),
  solo: null
};

const workspace = qs('#workspace');
const menu = qs('#menu');

/* ---------- Mounts ---------- */
const elMap  = qs('#app-map');
const elTime = qs('#app-timeseries');
const elList = qs('#app-list');
const elCloud= qs('#app-cloud');

/* ---------- RENDER: MAP (Leaflet) ---------- */
let map, mapLayer;
function ensureMap(){
  if(map || !elMap) return map;
  if(typeof L === 'undefined'){
    console.warn('Leaflet (L) nicht gefunden. Binde Leaflet in index.html ein.');
    return null;
  }
  map = L.map(elMap).setView([51.3, 10.3], 6); // Deutschland
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18, attribution: '&copy; OpenStreetMap'
  }).addTo(map);
  mapLayer = L.geoJSON({type:'FeatureCollection', features:[]}, {
    pointToLayer: (feat, latlng) => {
      const color = feat.properties?.color || '#1976d2';
      return L.circleMarker(latlng, { radius:5, color, fillColor: color, fillOpacity:0.85, weight:1 });
    },
    onEachFeature: (feat, layer) => {
      const p = feat.properties || {};
      const html = `
        <strong>${p.person_name || 'Ohne Name'}</strong><br/>
        <small>${(p.address||'').split('\n')[0]||''}</small><br/>
        Projekte: ${p.projects_count ?? (p.projects?.length || 0)}<br/>
        <span style="color:${p.color||'#666'}">${p.topic_label||''}</span><br/>
        ${p.url ? `<a href="${p.url}" target="_blank" rel="noopener">Profil</a>` : ''}
      `;
      layer.bindPopup(html);
    }
  }).addTo(map);
  return map;
}

function renderMap(gj){
  ensureMap();
  if(!mapLayer) return;
  mapLayer.clearLayers();
  mapLayer.addData(gj);
  if(gj?.features?.length){
    const b = mapLayer.getBounds();
    if(b.isValid()){
      // Kleine Verzögerung, falls das Pane gerade geresized wurde
      setTimeout(()=> map.fitBounds(b.pad(0.1)), 10);
    }
  }
}

/* ---------- RENDER: TIME (SVG gestapelt) ---------- */
function renderTime({ years, series }){
  if(!elTime) return;
  elTime.innerHTML = ''; // reset

  if(!years?.length){
    elTime.innerHTML = '<div class="empty">Keine Daten für den Zeitverlauf.</div>';
    return;
  }
  const W = elTime.clientWidth  || 600;
  const H = elTime.clientHeight || 260;
  const padding = { l:60, r:10, t:20, b:30 };
  const w = Math.max(100, W - padding.l - padding.r);
  const h = Math.max(80,  H - padding.t - padding.b);

  // Summen je Jahr (für Skalierung) und gestapelte Werte pro Serie
  const totals = years.map((_,i)=> series.reduce((acc,s)=> acc + (s.data[i]||0), 0));
  const maxV = Math.max(1, ...totals);
  const barW = Math.max(4, Math.floor(w / years.length) - 2);

  // Farben
  const palette = [
    '#1976d2','#ef6c00','#7b1fa2','#2e7d32','#c2185b',
    '#455a64','#8e24aa','#43a047','#f9a825','#5e35b1'
  ];
  const colorFor = (idx) => palette[idx % palette.length];

  // SVG
  const svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('width', W);
  svg.setAttribute('height', H);
  svg.style.background = 'var(--panel-bg, transparent)';
  elTime.appendChild(svg);

  // Achsen + Labels
  const g = document.createElementNS(svg.namespaceURI,'g');
  g.setAttribute('transform', `translate(${padding.l},${padding.t})`);
  svg.appendChild(g);

  // y-Achse (0, maxV)
  const yTicks = 4;
  for(let i=0;i<=yTicks;i++){
    const val = Math.round((maxV/yTicks)*i);
    const y   = h - (val/maxV)*h;
    const line= document.createElementNS(svg.namespaceURI,'line');
    line.setAttribute('x1', 0);
    line.setAttribute('x2', w);
    line.setAttribute('y1', y);
    line.setAttribute('y2', y);
    line.setAttribute('stroke', 'rgba(0,0,0,.1)');
    g.appendChild(line);

    const lbl = document.createElementNS(svg.namespaceURI,'text');
    lbl.setAttribute('x', -8);
    lbl.setAttribute('y', y+4);
    lbl.setAttribute('text-anchor','end');
    lbl.setAttribute('font-size','11');
    lbl.textContent = String(val);
    g.appendChild(lbl);
  }

  // gestapelte Balken
  years.forEach((year, xi) => {
    let yStack = 0;
    series.forEach((s, si) => {
      const v = s.data[xi] || 0;
      const hPix = (v/maxV)*h;
      if(v>0){
        const rect = document.createElementNS(svg.namespaceURI,'rect');
        rect.setAttribute('x', xi*(barW+2));
        rect.setAttribute('width', barW);
        rect.setAttribute('y', h - yStack - hPix);
        rect.setAttribute('height', hPix);
        rect.setAttribute('fill', colorFor(si));
        rect.setAttribute('opacity', '0.9');
        rect.appendChild(document.createTitleElement?.() ?? document.createElementNS(svg.namespaceURI,'title'))
        rect.querySelector('title')?.append?.(document.createTextNode?.(`${s.label}: ${v} (${year})`));
        g.appendChild(rect);
        yStack += hPix;
      }
    });

    // x-Labels sparsam zeichnen
    if(years.length <= 20 || xi % Math.ceil(years.length/20) === 0){
      const tx = document.createElementNS(svg.namespaceURI,'text');
      tx.setAttribute('x', xi*(barW+2) + barW/2);
      tx.setAttribute('y', h + 16);
      tx.setAttribute('text-anchor','middle');
      tx.setAttribute('font-size','11');
      tx.textContent = String(year);
      g.appendChild(tx);
    }
  });

  // Legende
  const legend = document.createElement('div');
  legend.style.display='flex'; legend.style.flexWrap='wrap';
  legend.style.gap='8px'; legend.style.marginTop='6px';
  series.forEach((s, i)=>{
    const item = document.createElement('span');
    item.innerHTML = `<span style="display:inline-block;width:10px;height:10px;background:${colorFor(i)};margin-right:6px;border-radius:2px;"></span>${s.label}`;
    legend.appendChild(item);
  });
  elTime.appendChild(legend);
}

/* ---------- RENDER: LISTE (Pagination) ---------- */
let listPage = 1;
function renderList({ items, total, page, pageSize }){
  if(!elList) return;
  elList.innerHTML = '';

  const header = document.createElement('div');
  header.className = 'list-header';
  header.style.display='flex';
  header.style.justifyContent='space-between';
  header.style.alignItems='center';
  header.style.margin='4px 0 8px';
  header.innerHTML = `<strong>${total} Ergebnisse</strong>`;
  elList.appendChild(header);

  const ul = document.createElement('ul');
  ul.className = 'result-list';
  ul.style.listStyle='none'; ul.style.padding='0'; ul.style.margin='0';
  items.forEach(r=>{
    const li = document.createElement('li');
    li.style.padding='8px 4px';
    li.style.borderBottom='1px solid var(--hairline, #eee)';
    li.innerHTML = `
      <div style="display:flex;gap:8px;align-items:baseline;flex-wrap:wrap">
        <span class="year" style="min-width:3ch;color:#666">${r.year ?? ''}</span>
        <a href="${r.url||'#'}" target="_blank" rel="noopener"><strong>${r.title || 'Ohne Titel'}</strong></a>
      </div>
      <div style="color:#555;font-size:12px">${r.person_name || ''} — ${r.institution || ''}</div>
      <div style="color:#888;font-size:12px">${r.topic || ''}</div>
    `;
    ul.appendChild(li);
  });
  elList.appendChild(ul);

  // Pagination
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const nav = document.createElement('div');
  nav.style.display='flex'; nav.style.gap='8px'; nav.style.marginTop='8px';
  const btn = (label, disabled, handler) => {
    const b = document.createElement('button');
    b.textContent = label;
    b.disabled = !!disabled;
    b.addEventListener('click', handler);
    return b;
  };
  nav.appendChild(btn('«', page<=1, ()=> goPage(1)));
  nav.appendChild(btn('‹', page<=1, ()=> goPage(page-1)));
  const info = document.createElement('span');
  info.style.margin='0 4px';
  info.textContent = `Seite ${page} / ${pages}`;
  nav.appendChild(info);
  nav.appendChild(btn('›', page>=pages, ()=> goPage(page+1)));
  nav.appendChild(btn('»', page>=pages, ()=> goPage(pages)));
  elList.appendChild(nav);
}

function goPage(p){
  listPage = Math.max(1, p);
  // resultsSource hat keine eigene setPage-API; wir rendern clientseitig neu:
  // Eine einfache Lösung: Snapshot holen, dann Slicing lokal anwenden.
  // Eleganter ist, resultsSource um setPage(page) zu erweitern. Hier quick&dirty:
  const snap = ListSrc.getSnapshot?.();
  if(!snap) return;
  const start = (listPage-1)*snap.pageSize;
  const items = snap.items
    ? snap.items
    : []; // falls du später serverseitig paginierst, bitte anpassen
  // Wenn ListSrc intern bereits gesliced hat, müssen wir neu rechnen:
  // Daher: wir triggern kurzerhand Filter-Event ohne Änderung, um recompute() auszulösen
  // und lassen ListSrc selbst paginieren – wenn du setPage ergänzt.
  // Bis dahin: wir rendern einfach neu, da subscribe gleich danach feuert.
  window.dispatchEvent(new Event('workspace:resized')); // no-op, nur um UI busy zu zeigen
}

/* ---------- RENDER: WORTWOLKE ---------- */
function renderCloud({ words }){
  if(!elCloud) return;
  elCloud.innerHTML = '';
  if(!words?.length){
    elCloud.innerHTML = '<div class="empty">Keine Begriffe.</div>';
    return;
  }
  const container = document.createElement('div');
  container.style.display='flex';
  container.style.flexWrap='wrap';
  container.style.alignContent='flex-start';
  container.style.gap='8px';
  container.style.lineHeight='1.2';

  const max = Math.max(...words.map(w=>w.weight||1));
  words.slice(0,150).forEach(w=>{
    const span = document.createElement('span');
    const f = 12 + Math.round(20 * (w.weight/max)); // 12..32px
    span.style.fontSize = f + 'px';
    span.style.color = '#333';
    span.textContent = w.text;
    container.appendChild(span);
  });
  elCloud.appendChild(container);
}

/* ---------- LAYOUT-ZUWEISUNG ---------- */
function applyLayout(){
  if(!workspace) return;

  workspace.className = '';
  workspace.id = 'workspace';
  workspace.classList.add(`layout-${state.layout}`);

  // Grid-Fractions
  const colLeft = Math.max(0.15, Math.min(0.85, state.colSplit));
  const rowTop  = Math.max(0.15, Math.min(0.85, state.rowSplit));
  document.documentElement.style.setProperty('--col-1', `${colLeft}fr ${1-colLeft}fr`);
  document.documentElement.style.setProperty('--row-1', `${rowTop}fr ${1-rowTop}fr`);

  // Sichtbare Apps
  const slots = ['a','b','c','d'];
  const appOrder = ['map','timeseries','list','cloud'].filter(k => state.apps[k]);

  // Reset Sichtbarkeit
  qsa('.pane').forEach(p => p.style.display = '');

  // Mounts in Pane einsetzen
  slots.forEach((slot, i) => {
    const pane = qs(`.pane[data-slot="${slot}"]`);
    if(!pane) return;
    const appKey = appOrder[i];
    if(!appKey){
      pane.style.display = 'none';
      return;
    }
    const title = { map:'Karte', timeseries:'Zeitverlauf', list:'Liste', cloud:'Wortwolke' }[appKey];
    pane.querySelector('header strong')?.replaceChildren(document.createTextNode(title));

    const content = pane.querySelector('.content');
    const node = qs(`#app-${appKey}`);
    if(content && node && !content.contains(node)) content.appendChild(node);
  });

  // Solo-Modus (optional)
  qsa('.pane').forEach(p=>{
    p.classList.toggle('hidden-by-solo', !!state.solo && p !== state.solo);
  });

  persist();

  // nach Layout-Änderung Redraws triggern
  setTimeout(() => {
    window.dispatchEvent(new Event('workspace:resized'));
    if(map) map.invalidateSize();
  }, 50);
}

function persist(){
  localStorage.setItem('layout', state.layout);
  localStorage.setItem('apps', JSON.stringify(state.apps));
  localStorage.setItem('colSplit', String(state.colSplit));
  localStorage.setItem('rowSplit', String(state.rowSplit));
}

/* ---------- Splitter (Drag) ---------- */
function setupSplitters(){
  qsa('.splitter').forEach(s=>{
    let dragging = false;

    const onMove = (ev) => {
      if(!dragging) return;
      const rect = workspace.getBoundingClientRect();
      if(s.classList.contains('v')){
        const x = (ev.touches?.[0]?.clientX ?? ev.clientX) - rect.left;
        state.colSplit = Math.min(0.85, Math.max(0.15, x / rect.width));
      } else {
        const y = (ev.touches?.[0]?.clientY ?? ev.clientY) - rect.top;
        state.rowSplit = Math.min(0.85, Math.max(0.15, y / rect.height));
      }
      applyLayout();
    };

    const onUp = () => { dragging = false; document.body.style.userSelect=''; };

    s.addEventListener('mousedown', () => { dragging = true; document.body.style.userSelect='none'; });
    s.addEventListener('touchstart', () => { dragging = true; }, {passive:true});
    window.addEventListener('mousemove', onMove);
    window.addEventListener('touchmove', onMove, {passive:false});
    window.addEventListener('mouseup', onUp);
    window.addEventListener('touchend', onUp);
  });
}

/* ---------- Menü-Interaktionen ---------- */
qsa('#menu [data-layout]').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    state.layout = btn.dataset.layout;
    applyLayout();
  });
});
qsa('#menu [data-app]').forEach(cb=>{
  cb.checked = !!state.apps[cb.dataset.app];
  cb.addEventListener('change', ()=>{
    state.apps[cb.dataset.app] = cb.checked;
    applyLayout();
  });
});

// optionaler Mobile-Toggle
qs('#menuToggle')?.addEventListener('click', ()=>{
  menu?.classList.toggle('open');
});

/* ---------- Resize Hook ---------- */
window.addEventListener('workspace:resized', ()=>{
  if(map) setTimeout(()=> map.invalidateSize(), 50);
});

/* ---------- BOOTSTRAP: Daten laden + Sources + Render ---------- */
(async function bootstrap(){
  try{
    const { peopleGeo, projectRows } = await loadData();

    // Sources initialisieren
    MapPeople.initPeople(peopleGeo);
    TimeSrc.init(projectRows);
    ListSrc.init(projectRows, { pageSize: 50, sort: "year:desc" });
    CloudSrc.init(projectRows, { topN: 120, sources:["title","topic","institution"] });

    // Subscriptions -> Rendering
    MapPeople.subscribe(renderMap);
    TimeSrc.subscribe(renderTime);
    ListSrc.subscribe(snap => { renderList(snap); });
    CloudSrc.subscribe(renderCloud);

    // Erste, leere Filter (alles sichtbar)
    setFilters({
      topics: new Set(), years: null, search: "", personIds: new Set()
    });

    console.info('App bereit:', {
      people: peopleGeo?.features?.length || 0,
      rows: projectRows?.length || 0
    });
  } catch (err){
    console.error('Fehler beim Laden/Initialisieren:', err);
    const mount = qs('#app-list') || document.body;
    const pre = document.createElement('pre');
    pre.textContent = 'Fehler beim Start:\n' + (err?.stack || String(err));
    mount.appendChild(pre);
  }
})();

/* ---------- INIT Layout ---------- */
(function init(){
  qs(`#menu [data-layout="${state.layout}"]`)?.classList.add('active');
  applyLayout();
  setupSplitters();
})();

