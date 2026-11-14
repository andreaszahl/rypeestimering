# Rypekart – tetthetskart for lirype på Helgeland

Kursprosjekt i *Geografisk IT og kunstig intelligens* (UiA). Appen lager et tetthetskart for lirype
i Statskogs takseringsområder Helgeland 1, 2 og 3, basert på publiserte estimater fra
Hønsefuglportalen (NINA) og habitatlag.

## Metode (fase 1)
- Kalibrering: NINAs publiserte tetthet (fugl/km²) per område og år. Ingen egen distance sampling i fase 1.
- Habitatbasert nedskalering: en habitatindeks per 250 m-rutecelle (AR50 + terreng) fordeler
  områdets tetthet utover cellene, slik at arealvektet snitt innenfor takseringspolygonene = NINAs estimat.
- Utenfor polygonene vises kun habitatindeks, ikke tetthet.
- Fase 2 (senere): rådata fra NINA, egen deteksjonsfunksjon og density surface model.

## Data
- `data/raw/helgeland_lirype_estimater.csv` – estimater per område/år 2013–2026.
  Kolonnene `*_minus_se` / `*_pluss_se` er estimat ± 1 SE (ikke 95 % KI).
- `data/raw/helgeland_takseringsomrader.geojson` – 26 polygoner (WGS84), grove avgrensninger (5–14 hjørner).
  Tettheten gjelder hele området samlet, ikke enkeltpolygoner.
- AR50 (NIBIO) – egnet for visualisering, ikke presis arealanalyse; minste kartleggingsenhet 1,5 hektar. Nevn dette i rapportering.
  WFS-feltene heter `arealtype`, `treslag`, `skogbonitet`, `vegetasjonsdekke` (= ARTYPE, ARTRESLAG,
  ARSKOGBON, ARVEGET). Hentes i 10×10 km-fliser fordi STARTINDEX-paginering i tjenesten er ustabil.
  «Ikke kartlagt» (99) = svensk side av grensen.
- DTM fra Kartverket (WCS `nhm_dtm_topo_25833`, 25 m). Tjenesten har ingen nodata-verdi: sjø og hull
  (bl.a. et rektangel ved svenskegrensen i H3) kommer som 0 og maskeres til NaN.
- Takseringspolygonene overlapper (H1, H3). All arealberegning bruker unionen per område
  (`takseringsomrade_union`: 138,7 / 190,1 / 671,0 km²). Det østligste H3-polygonet går ca. 0,2 km²
  inn i Sverige; der er H = NaN, og arealet faller ut av H̄ (bortfall 0,03 %).

## Habitatmodell og kalibrering (prompt 2)
- Alle vekter og parametere ligger i `config/habitat.toml`, med begrunnelse. Endres der, ikke i koden.
- `rutenett` har 22 AR50-klasser. Hver klasse er koblet til nøyaktig én habitatgruppe (eller
  ekskludert); koden stopper hvis en klasse mangler kobling – spør brukeren, ikke gjett.
- Avklart med bruker 2026-11-03:
  - «Lav bonitet» = impediment (11) + lav (12); middels/høy = 13 + 18.
  - Vegetasjonsdekke 54 «skrint til godt» er egen gruppe «Snaumark, skrinn til god», w = 0,75 (antakelse).
  - Snaumark med uregistrert vegetasjonsdekke → skrinn (0,6). Skog med kjent treslag men uregistrert
    bonitet → lav bonitet for sitt treslag.
  - Skog uten treslag/bonitet (ca. 1 070 km²) antas å være fjellskog, w = 0,8 (antakelse, flagget).
- H = K × T × S × M ∈ [0, 1]. K regnes over kartlagt del av cellen; H = NaN ved > 50 % ikke kartlagt
  eller uten DTM. Lokal tregrense (`rypekart.tregrense`) = P95 av høyden i skogceller per 5×5 km-blokk.
  H2/H3 ligger over forventet nivå (median ca. 710/670 moh) – flagget, ikke korrigert.
- Kalibrering: k = tetthet / H̄ per område/år/mål; celletetthet = k × H bare innenfor unionen.
  Det arealvektede snittet gjenskaper NINA eksakt (testet). Vektene endrer fordelingen, ikke totalen.
- Følsomhet: 200 Monte Carlo-trekk med fast frø. CV_total = √(CV_NINA² + CV_fordeling²) er en tilnærming.
- Rekkefølge: omrader → ar50 → dtm → rutenett → tregrense → habitat → kalibrering → folsomhet → qa_habitat
  (`qa` er QA-steget fra prompt 1). Tester: `uv run pytest`.

## Konvensjoner
- Python via `uv`. Kjør alt med `uv run`.
- Analyse-CRS: EPSG:25833. Webkart-eksport: EPSG:4326.
- Struktur: `src/rypekart/` (moduler), `data/raw` (nedlastinger, cache), `data/processed` (GeoPackage), `outputs/` (figurer).
- Hvert steg er idempotent og kan kjøres med `uv run python -m rypekart.<steg>`. Nedlastinger caches og lastes ikke ned på nytt.
- Fra og med `rutenett` hopper stegene over seg selv når de er nyere enn stegene de bygger på,
  sin egen kildefil og `config/habitat.toml` (tabellen `steglogg` i GeoPackage). `--force` tvinger ny kjøring.
  Hjelpekode som stegene deler (`lagring.py`, `parametere.py`, `steg.py`) følges ikke – bruk `--force` etter endringer der.
- Prosjektet ligger i `C:\Users\andreas.kristiansen\dev\rypekart`, utenfor OneDrive (flyttet 2026-11-14,
  fordi synkroniseringen låste `.venv` og lastet opp GeoPackage-filen ved hver kjøring). Koden sikres med git.
  Ikke legg prosjektet, `.venv` eller `data/` i OneDrive igjen.
- Data og outputs committes ikke (`.gitignore`). Unntak: de håndlagde inndatafilene i `data/raw`
  (`helgeland_lirype_estimater.csv`, `helgeland_takseringsomrader.geojson`, `build_helgeland.py`),
  som ikke kan lastes ned på nytt.
- Norske navn på kolonner og lag; kode og kommentarer kan være på engelsk.
- Vis en plan før større endringer, og stopp og rapporter hvis en datakilde feiler – ikke lag mock-data uten å si fra.
