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
- **Tregrensen er kontrollert (2026-11-14):** dagens metode (a) ble sammenlignet med (b) uten «skog uten
  treslag» og (c) P90, og brukeren valgte (a). «Skog uten treslag» ligger i samme høyde som lauvskog med
  lav bonitet, så den hører til skogen som danner tregrensa. H2/H3 har median ca. 710/670 moh (over
  forventet 400–650), men nivået antas å være reelt for innlandet. Varianten påvirker H̄ med maks ±0,02.
- Kalibrering: k = tetthet / H̄ per område/år/mål; celletetthet = k × H bare innenfor unionen.
  Det arealvektede snittet gjenskaper NINA eksakt (testet). Vektene endrer fordelingen, ikke totalen.
- Følsomhet: 200 Monte Carlo-trekk med fast frø. CV_total = √(CV_NINA² + CV_fordeling²) er en tilnærming.
- Rekkefølge: omrader → ar50 → dtm → rutenett → tregrense → habitat → kalibrering → folsomhet → qa_habitat
  → eksport (`qa` er QA-steget fra prompt 1). Tester: `uv run pytest`.
- Fase 2: rådata fra linjetakseringene på Statskogs grunn finnes åpent på GBIF (Nilsen, Vang &
  Breisjøberget 2022, <https://doi.org/10.15468/q2ehlk>, CC BY 4.0).

## Webkart (prompt 3)
- `rypekart.eksport` skriver `web/data/`: `celler.geojson` (celler med andel > 0, EPSG:4326, 5 desimaler),
  `habitatgrupper.json`, `kalibrering.json`, `omrader.geojson` (`lag` = union/polygon),
  `habitat_H?.png` (H warpet til EPSG:3857, YlGnBu) og `habitat_bounds.json`.
- `klasse` i `celler.geojson` er en kortkode på to bokstaver (`eksport.KORTKODER`), og navnet slås opp i
  `habitatgrupper.json`. Det holder filen under 5 MB (4,8 MB; ca. 0,5 MB komprimert). Valgt av bruker 2026-11-14.
- CV for voksne finnes ikke i CSV-en og regnes som (pluss_se − minus_se) / 2 / estimat. For total stemmer
  denne formelen med NINAs `tetthet_cv`.
- `web/` er statisk HTML/CSS/JS (ES-moduler) uten byggesteg. Leaflet 1.9.4 og Chart.js 4.4.1 lastes fra
  cdnjs med SRI-hash. Tettheten k × H regnes i nettleseren, med faste fargeklasser per mål fra
  99-persentilen over alle år.
- Bakgrunnskart: Kartverkets cache, `https://cache.kartverket.no/v1/wmts/1.0.0/{topograatone|topo}/default/webmercator/{z}/{y}/{x}.png`
  (bekreftet i WMTSCapabilities). Attribusjon «© Kartverket». Flisene lastes ikke ned eller caches lokalt.
- Cellene tegnes på canvas med `smoothFactor: 0`, ellers forsvinner 250 m-celler ved lav zoom.
  Områdeomrissene tegnes med SVG, fordi et canvas-polygon fanger klikk i hele innsiden og blokkerer cellene.
- Publiseres på GitHub Pages (<https://andreaszahl.github.io/rypeestimering/>) via
  `.github/workflows/pages.yml`, som laster opp `web/` ved push til `main`. Valgt 2026-11-14 i stedet for
  Cloudflare Pages, som prompt 3 nevner. Pages-kilden må være «GitHub Actions», fordi «Deploy from a branch»
  bare støtter roten og `/docs`.
- Lisenser: koden er MIT (`LICENSE`). AR50 er NLOD 1.0 (Geonorge-metadata). DTM og bakgrunnskart er
  CC BY 4.0. For NINA-estimatene er det ikke oppgitt lisens, så de gjengis med kildehenvisning.

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
- Data og outputs committes ikke (`.gitignore`, mønstrene er ankret til roten: `/data/*`, `/outputs/`).
  Unntak: de håndlagde inndatafilene i `data/raw` (`helgeland_lirype_estimater.csv`,
  `helgeland_takseringsomrader.geojson`, `build_helgeland.py`), som ikke kan lastes ned på nytt.
  `web/data/` committes, fordi GitHub Pages publiserer den.
- Norske navn på kolonner og lag; kode og kommentarer kan være på engelsk.
- Vis en plan før større endringer, og stopp og rapporter hvis en datakilde feiler – ikke lag mock-data uten å si fra.
