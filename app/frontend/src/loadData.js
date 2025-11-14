// data/loadData.js
export async function loadData(){
  const [peopleGeo, projects] = await Promise.all([
    fetch('../backend/data/processed/people.geojson').then(r=>r.json()),
    fetch('../backend/data/processed/projects.json').then(r=>r.json())
  ]);

  // Index der Personen (nach ID als String)
  const peopleIndex = new Map();
  for(const f of peopleGeo.features){
    const p = f.properties;
    peopleIndex.set(String(p.person_number), {
      id: String(p.person_number),
      name: p.person_name,
      address: p.address,
      lat: f.geometry?.coordinates?.[1],
      lng: f.geometry?.coordinates?.[0],
      topic_id: p.topic_id,
      topic_label: p.topic_label,
      color: p.color,
      url: p.url,
      projects_count: p.projects_count,
      projects: p.projects
    });
  }

  // Projekte „denormalisieren“: jede Personen-ID eines Projekts -> eigene Zeile
  // und Personendaten (Name/Koordinaten) anhängen
  const projectRows = [];
  for(const prj of projects){
    for(const pid of prj.people || []){
      const person = peopleIndex.get(String(pid));
      projectRows.push({
        id: prj.id,
        title: prj.title,
        topic: prj.topic_label,     // String für time/cloud
        topic_id: prj.topic_id,
        start_year: prj.start_year,
        end_year: prj.end_year,
        year: prj.end_year ?? prj.start_year, // ein Jahr für Zeitreihe
        url: prj.url,

        // Personbezug
        person_id: String(pid),
        person_name: person?.name ?? '',
        institution: person ? person.address.split('\n')[0] : '',
        lat: person?.lat,
        lng: person?.lng
      });
    }
  }

  return { peopleGeo, projectRows };
}

