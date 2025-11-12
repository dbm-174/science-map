const API = location.origin;

let map, layerGroup;

function sizeForCount(n) {
  // sqrt scaling, 6..20 px
  const minR=6, maxR=20;
  const s = Math.sqrt(Math.max(1, n));
  return Math.min(maxR, minR + s*3);
}

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function loadTopics() {
  const topics = await fetchJSON(`${API}/api/topics`);
  const sel = document.getElementById("topicSelect");
  sel.innerHTML = `<option value="">Alle Themen</option>` + topics.map(t =>
    `<option value="${t.id}">${t.label} (${t.count})</option>`).join("");
  // legend
  const leg = document.getElementById("legend");
  leg.innerHTML = topics.map(t => `
    <div class="legend-item"><span class="legend-color" style="background:${t.color}"></span>${t.label}</div>
  `).join("");
  return topics;
}

function addFeatures(fc) {
  if (layerGroup) layerGroup.remove();
  layerGroup = L.layerGroup().addTo(map);
  fc.features.forEach(f => {
    const p = f.properties;
    const [lon, lat] = f.geometry.coordinates;
    const r = sizeForCount(p.projects_count);
    const marker = L.circleMarker([lat, lon], {
      radius: r,
      color: "#000",
      weight: 1,
      fillColor: p.color || "#3388ff",
      fillOpacity: 0.8
    }).addTo(layerGroup);
    const html = `
      <b>${p.person_name}</b><br/>
      <small>${(p.address||"").replace(/\n/g,"<br>")}</small><br/>
      <b>Projekte:</b> ${p.projects_count}<br/>
      <b>Thema:</b> ${p.topic_label || ""}<br/>
      <details><summary>Projektliste</summary><ul>
      ${(p.projects||[]).map(t=>`<li>${t}</li>`).join("")}
      </ul></details>
      <a href="${p.url}" target="_blank" rel="noopener">GEPRIS-Seite</a>
    `;
    marker.bindPopup(html);
  });
}

async function applyFilters() {
  const topic = document.getElementById("topicSelect").value;
  const q = document.getElementById("searchBox").value.trim();
  const url = new URL(`${API}/api/people`);
  if (topic !== "") url.searchParams.set("topic_id", topic);
  if (q) url.searchParams.set("q", q);
  const fc = await fetchJSON(url.toString());
  addFeatures(fc);
}

async function main() {
  map = L.map('map').setView([51.15, 10.45], 6); // Deutschland Mitte
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18, attribution: '&copy; OpenStreetMap'
  }).addTo(map);

  await loadTopics();
  await applyFilters();
  document.getElementById("applyBtn").addEventListener("click", applyFilters);
}

main().catch(err => alert(err));

