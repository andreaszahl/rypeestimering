// Rypekart Helgeland – static Leaflet map. Density per cell = k[omrade][aar][maal] × H (computed here).
import { CV_FARGER, CV_GRENSER, TETTHET_FARGER, klasseFarge, legendeHtml, tetthetsklasser } from "./farger.js";
import { visOmrade } from "./panel.js";

const KARTVERKET = (lag) => `https://cache.kartverket.no/v1/wmts/1.0.0/${lag}/default/webmercator/{z}/{y}/{x}.png`;
const ATTRIBUSJON = '© <a href="https://www.kartverket.no/" target="_blank" rel="noopener">Kartverket</a>';

const tilstand = { aar: 2026, maal: "total", lag: "tetthet", omrade: null };
const fmt = (x, d = 0) => x.toLocaleString("nb-NO", { minimumFractionDigits: d, maximumFractionDigits: d });

async function hent(sti) {
  const svar = await fetch(sti);
  if (!svar.ok) throw new Error(`${sti}: HTTP ${svar.status}`);
  return svar.json();
}

function lagKart() {
  const kart = L.map("kart", { zoomControl: true, preferCanvas: true, minZoom: 6, maxZoom: 16 });
  const graatone = L.tileLayer(KARTVERKET("topograatone"), { attribution: ATTRIBUSJON, maxZoom: 18 });
  const topo = L.tileLayer(KARTVERKET("topo"), { attribution: ATTRIBUSJON, maxZoom: 18 });
  graatone.addTo(kart);
  kart.createPane("habitat").style.zIndex = 405;
  kart.createPane("celler").style.zIndex = 410;
  kart.createPane("omrader").style.zIndex = 420;
  L.control.scale({ imperial: false }).addTo(kart);
  return { kart, bakgrunn: { "Topografisk, gråtone": graatone, "Topografisk": topo } };
}

function cellefarge(p, data) {
  if (p.H === null) return null;
  const post = data.kalibrering[p.omrade][tilstand.aar][tilstand.maal];
  if (tilstand.lag === "tetthet") return klasseFarge(post.k * p.H, data.klasser[tilstand.maal].grenser, TETTHET_FARGER);
  if (tilstand.lag === "usikkerhet") return klasseFarge(cvTotal(p, post), CV_GRENSER, CV_FARGER);
  return null;
}

function cvTotal(p, post) {
  if (p.cv_fordeling === null) return null;
  return Math.sqrt(post.cv ** 2 + p.cv_fordeling ** 2);
}

function cellestil(data) {
  return (feature) => {
    if (tilstand.lag === "habitat") {
      // the habitat raster is shown underneath; keep the cells clickable but invisible
      return { stroke: false, fill: true, fillOpacity: 0 };
    }
    const farge = cellefarge(feature.properties, data);
    return { stroke: false, fill: true, fillColor: farge ?? "#bdbdbd", fillOpacity: 0.85 };
  };
}

function popupHtml(p, data) {
  const omr = data.kalibrering[p.omrade];
  const post = omr[tilstand.aar][tilstand.maal];
  const gruppe = data.grupper[p.klasse]?.navn ?? p.klasse;
  const maaltekst = tilstand.maal === "total" ? "alle fugl" : "voksne";
  let tetthet = "Ikke beregnet";
  if (p.H !== null) {
    tetthet = `${fmt(post.k * p.H, 1)} fugl/km² <br><small>± 1 SE: ${fmt(post.k_minus_se * p.H, 1)}–${fmt(post.k_pluss_se * p.H, 1)}</small>`;
  }
  const cv = p.H === null ? null : cvTotal(p, post);
  return `<div class="popup"><h3>${omr.navn} · celle ${p.id}</h3><table>
    <tr><th>Tetthet ${tilstand.aar} (${maaltekst})</th><td>${tetthet}</td></tr>
    <tr><th>Habitatindeks H</th><td>${p.H === null ? "–" : fmt(p.H, 3)}</td></tr>
    <tr><th>Habitatgruppe</th><td>${gruppe}</td></tr>
    <tr><th>Høyde</th><td>${p.hoyde === null ? "–" : `${fmt(p.hoyde)} moh`}</td></tr>
    <tr><th>Usikkerhet CV<sub>total</sub></th><td>${cv === null ? "–" : fmt(cv, 2)}</td></tr>
    <tr><th>Andel i takseringsområdet</th><td>${fmt(p.andel * 100)} %</td></tr>
  </table></div>`;
}

async function start() {
  const kartEl = document.getElementById("kart");
  const laster = document.createElement("div");
  laster.className = "laster";
  laster.textContent = "Laster kartdata …";
  kartEl.appendChild(laster);

  const { kart, bakgrunn } = lagKart();
  const [celler, kalibrering, omrader, grupper, bilder] = await Promise.all([
    hent("data/celler.geojson"), hent("data/kalibrering.json"), hent("data/omrader.geojson"),
    hent("data/habitatgrupper.json"), hent("data/habitat_bounds.json"),
  ]);
  const data = {
    kalibrering, grupper,
    klasser: {
      total: tetthetsklasser(celler.features, kalibrering, "total"),
      voksne: tetthetsklasser(celler.features, kalibrering, "voksne"),
    },
  };

  const habitatlag = L.layerGroup(Object.entries(bilder).map(([kode, b]) =>
    L.imageOverlay(`data/habitat_${kode}.png`, b, { pane: "habitat", opacity: 0.85, className: "habitatbilde",
      alt: `Habitatindeks ${kode}` })));

  // Outlines use SVG: a canvas polygon captures clicks on its whole interior even without fill,
  // which would block clicks on the cells underneath. SVG paths with fill none only react on the stroke.
  const omrisslag = L.svg({ pane: "omrader" });
  const union = L.geoJSON(omrader, {
    renderer: omrisslag,
    filter: (f) => f.properties.lag === "union",
    style: { color: "#1f2a30", weight: 2, fill: false },
    onEachFeature: (f, lag) => {
      lag.bindTooltip(`${f.properties.navn} (${fmt(f.properties.areal_km2, 1)} km²)`, { sticky: true });
      lag.on("click", () => velgOmrade(String(f.properties.omrade), false));
    },
  }).addTo(kart);
  const polygoner = L.geoJSON(omrader, {
    renderer: omrisslag,
    filter: (f) => f.properties.lag === "polygon",
    style: { color: "#1f2a30", weight: 1, dashArray: "4 4", fill: false },
    onEachFeature: (f, lag) => lag.bindTooltip(`Polygon ${f.properties.polygon_id}`, { sticky: true }),
  });
  L.control.layers(bakgrunn, { "Takseringsområder": union, "Opprinnelige polygoner": polygoner },
    { position: "topright", collapsed: true }).addTo(kart);

  const legende = L.control({ position: "bottomleft" });
  legende.onAdd = () => {
    const el = L.DomUtil.create("div", "legende");
    el.title = "Trykk for å skjule/vise forklaringen";
    L.DomEvent.disableClickPropagation(el);
    L.DomEvent.on(el, "click", () => el.classList.toggle("sammenfoldet"));
    return el;
  };
  legende.addTo(kart);

  // The map needs a view before the canvas renderer is added, otherwise the first draw is incomplete.
  kart.fitBounds(union.getBounds(), { padding: [20, 20] });
  const renderer = L.canvas({ pane: "celler", padding: 0.3 });
  // smoothFactor 0: a 250 m cell is ~1 px at zoom 8, and Leaflet's default simplification drops it.
  const cellelag = L.geoJSON(celler, { renderer, smoothFactor: 0, style: cellestil(data) }).addTo(kart);
  cellelag.on("click", (e) => {
    const p = e.layer.feature.properties;
    L.popup({ maxWidth: 300 }).setLatLng(e.latlng).setContent(popupHtml(p, data)).openOn(kart);
    velgOmrade(String(p.omrade), false);
  });
  laster.remove();

  // ---------- controls ----------
  const panelInfo = document.getElementById("omradeinfo");
  const omradeKnapper = document.querySelectorAll(".omradeliste button");
  const panel = document.getElementById("panel");
  const handtak = document.getElementById("panel-handtak");

  function velgOmrade(nr, zoom) {
    tilstand.omrade = nr;
    omradeKnapper.forEach((k) => k.setAttribute("aria-pressed", String(k.dataset.omrade === nr)));
    visOmrade(panelInfo, kalibrering, nr, tilstand.aar, tilstand.maal);
    if (panel.dataset.lukket === "true") settPanel(true);
    kart.invalidateSize();
    if (zoom) {
      union.eachLayer((l) => {
        if (String(l.feature.properties.omrade) === nr) kart.fitBounds(l.getBounds(), { padding: [20, 20] });
      });
    }
  }

  function oppdater() {
    cellelag.setStyle(cellestil(data));
    if (tilstand.lag === "habitat") habitatlag.addTo(kart); else habitatlag.remove();
    legende.getContainer().innerHTML = legendeHtml(tilstand.lag, tilstand.maal, data.klasser[tilstand.maal]);
    if (tilstand.omrade) visOmrade(panelInfo, kalibrering, tilstand.omrade, tilstand.aar, tilstand.maal);
    kart.closePopup();
  }

  function settPanel(apen) {
    panel.dataset.lukket = String(!apen);
    handtak.setAttribute("aria-expanded", String(apen));
    kart.invalidateSize(); // reads the new container size synchronously, so a following fitBounds is correct
  }

  const aarInput = document.getElementById("aar");
  const aarVerdi = document.getElementById("aar-verdi");
  const settAar = () => {
    if (Number(aarInput.value) === tilstand.aar) return;
    tilstand.aar = Number(aarInput.value);
    aarVerdi.textContent = aarInput.value;
    oppdater();
  };
  aarInput.addEventListener("input", settAar);
  aarInput.addEventListener("change", settAar);
  document.querySelectorAll('input[name="maal"]').forEach((r) => r.addEventListener("change", () => {
    tilstand.maal = r.value;
    oppdater();
  }));
  document.querySelectorAll('input[name="lag"]').forEach((r) => r.addEventListener("change", () => {
    tilstand.lag = r.value;
    oppdater();
  }));
  omradeKnapper.forEach((k) => k.addEventListener("click", () => velgOmrade(k.dataset.omrade, true)));
  handtak.addEventListener("click", () => settPanel(panel.dataset.lukket === "true"));

  const om = document.getElementById("om");
  document.getElementById("vis-om").addEventListener("click", () => om.showModal());

  if (window.matchMedia("(max-width: 760px)").matches) settPanel(false);
  oppdater();
}

start().catch((feil) => {
  console.error(feil);
  const el = document.querySelector(".laster") ?? document.getElementById("kart");
  el.textContent = `Kunne ikke laste kartdata: ${feil.message}`;
});
