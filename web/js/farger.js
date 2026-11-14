// Colour scales and legends. Density classes are fixed across all years (from the 99th percentile
// over every year and cell for the chosen measure) so years can be compared directly.

export const TETTHET_FARGER = ["#ffffb2", "#fed976", "#feb24c", "#fd8d3c", "#fc4e2a", "#e31a1c", "#b10026"]; // YlOrRd
export const CV_FARGER = ["#f2f0f7", "#dadaeb", "#bcbddc", "#9e9ac8", "#756bb1", "#54278f"]; // Purples
export const CV_GRENSER = [0.15, 0.2, 0.3, 0.4, 0.5];
// YlGnBu – must match H_FARGESKALA in rypekart.eksport (habitat_H?.png)
export const H_GRADIENT = ["#ffffd9", "#edf8b1", "#c7e9b4", "#7fcdbb", "#41b6c4", "#1d91c0", "#225ea8", "#253494", "#081d58"];
export const INGEN_DATA = "#bdbdbd";

function pentSteg(x) {
  const e = Math.floor(Math.log10(x));
  const f = x / 10 ** e;
  const n = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
  return n * 10 ** e;
}

function persentil(verdier, p) {
  const s = Float64Array.from(verdier).sort();
  const i = Math.min(s.length - 1, Math.max(0, Math.round((p / 100) * (s.length - 1))));
  return s[i];
}

/** Six equal-width classes up to the (rounded) 99th percentile, plus one open top class. */
export function tetthetsklasser(celler, kalibrering, maal) {
  const verdier = [];
  for (const c of celler) {
    const H = c.properties.H;
    if (H === null) continue;
    const omr = kalibrering[c.properties.omrade];
    for (const [aar, post] of Object.entries(omr)) {
      if (!/^\d{4}$/.test(aar)) continue;
      verdier.push(post[maal].k * H);
    }
  }
  const p99 = persentil(verdier, 99);
  const steg = pentSteg(p99 / 6);
  return { p99, grenser: [1, 2, 3, 4, 5, 6].map((i) => i * steg) };
}

export function klasseFarge(verdi, grenser, farger) {
  if (verdi === null || Number.isNaN(verdi)) return INGEN_DATA;
  let i = 0;
  while (i < grenser.length && verdi >= grenser[i]) i++;
  return farger[i];
}

const tall = (x) => x.toLocaleString("nb-NO", { maximumFractionDigits: 2 });

function klasseRader(grenser, farger, enhet = "") {
  const rader = [];
  for (let i = 0; i < farger.length; i++) {
    const tekst = i === 0 ? `< ${tall(grenser[0])}`
      : i === farger.length - 1 ? `≥ ${tall(grenser[i - 1])}`
        : `${tall(grenser[i - 1])}–${tall(grenser[i])}`;
    rader.push(`<div class="rad"><span class="farge" style="background:${farger[i]}"></span>${tekst}${enhet}</div>`);
  }
  rader.push(`<div class="rad"><span class="farge" style="background:${INGEN_DATA}"></span>Ingen data</div>`);
  return `<div class="rader">${rader.join("")}</div>`;
}

export function legendeHtml(lag, maal, klasser) {
  if (lag === "tetthet") {
    return `<h4>Tetthet, ${maal === "total" ? "alle fugl" : "voksne"} (fugl/km²)</h4>`
      + klasseRader(klasser.grenser, TETTHET_FARGER)
      + `<div class="fotnote">Samme klasser for alle år</div>`;
  }
  if (lag === "usikkerhet") {
    return `<h4>Usikkerhet (CV<sub>total</sub>)</h4>` + klasseRader(CV_GRENSER, CV_FARGER)
      + `<div class="fotnote">√(CV<sub>NINA</sub>² + CV<sub>fordeling</sub>²)</div>`;
  }
  return `<h4>Habitatindeks H</h4>`
    + `<div class="gradient" style="background:linear-gradient(to right,${H_GRADIENT.join(",")})"></div>`
    + `<div class="skala"><span>0</span><span>0,5</span><span>1</span></div>`
    + `<div class="fotnote">Hele studieområdet. Gjennomsiktig = ikke beregnet.</div>`;
}
