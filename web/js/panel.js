// Side panel per survey area: estimated birds ± SE, H̄ and a 2013–2026 time series with SE band.

const fmt = (x, d = 0) => x.toLocaleString("nb-NO", { minimumFractionDigits: d, maximumFractionDigits: d });

let graf = null;

function aarstall(omr) {
  return Object.keys(omr).filter((k) => /^\d{4}$/.test(k)).map(Number).sort((a, b) => a - b);
}

export function visOmrade(element, kalibrering, omradeNr, aar, maal) {
  const omr = kalibrering[omradeNr];
  const post = omr[aar][maal];
  const maaltekst = maal === "total" ? "alle fugl" : "voksne";
  element.innerHTML = `
    <h2>${omr.navn}</h2>
    <dl class="nokkeltall">
      <div><dt>Estimert antall ${aar} (${maaltekst})</dt>
        <dd>${fmt(post.estimert_antall)}<small>SE-intervall ${fmt(post.antall_minus_se)}–${fmt(post.antall_pluss_se)}</small></dd></div>
      <div><dt>Tetthet ${aar} (fugl/km²)</dt>
        <dd>${fmt(post.tetthet, 1)}<small>SE-intervall ${fmt(post.minus_se, 1)}–${fmt(post.pluss_se, 1)}</small></dd></div>
      <div><dt>Gjennomsnittlig habitatindeks H̄</dt><dd>${fmt(omr.hbar, 3)}</dd></div>
      <div><dt>Areal takseringsområde</dt><dd>${fmt(omr.areal_km2, 1)} km²</dd></div>
    </dl>
    <p class="graf-tittel">Tetthet 2013–2026 (${maaltekst}) med ± 1 SE</p>
    <div class="graf"><canvas id="tidsserie" aria-label="Tidsserie for tetthet"></canvas></div>`;

  const aarListe = aarstall(omr);
  const verdi = (felt) => aarListe.map((a) => omr[a][maal][felt]);
  const valgt = aarListe.map((a) => a === aar);
  if (graf) graf.destroy();
  graf = new Chart(element.querySelector("#tidsserie"), {
    type: "line",
    data: {
      labels: aarListe,
      datasets: [
        { label: "−1 SE", data: verdi("minus_se"), borderWidth: 0, pointRadius: 0, fill: false },
        { label: "+1 SE", data: verdi("pluss_se"), borderWidth: 0, pointRadius: 0, fill: "-1",
          backgroundColor: "rgba(227, 26, 28, 0.15)" },
        { label: "Tetthet", data: verdi("tetthet"), borderColor: "#b10026", backgroundColor: "#b10026",
          borderWidth: 2, tension: 0.2,
          pointRadius: valgt.map((v) => (v ? 6 : 2.5)),
          pointBackgroundColor: valgt.map((v) => (v ? "#fd8d3c" : "#b10026")),
          pointBorderColor: valgt.map((v) => (v ? "#1f2a30" : "#b10026")),
          pointBorderWidth: valgt.map((v) => (v ? 2 : 1)) },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          filter: (item) => item.datasetIndex === 2,
          callbacks: {
            label: (ctx) => {
              const a = aarListe[ctx.dataIndex];
              const p = omr[a][maal];
              return `${fmt(p.tetthet, 1)} fugl/km² (${fmt(p.minus_se, 1)}–${fmt(p.pluss_se, 1)})`;
            },
          },
        },
      },
      scales: {
        y: { beginAtZero: true, title: { display: true, text: "fugl/km²" } },
        x: { ticks: { maxRotation: 0, autoSkip: true } },
      },
    },
  });
}
