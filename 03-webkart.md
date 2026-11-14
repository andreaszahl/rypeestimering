# Prompt 3 – Webkart, README og lisens

Les CLAUDE.md først. Vis en plan før du skriver kode. Repoet er offentlig på GitHub, og webkartet
skal publiseres som statisk side på Cloudflare Pages.

## 0. Forarbeid
- **Tregrense:** Hvis CLAUDE.md ikke allerede sier at tregrensen er kontrollert, sammenlign tre varianter:
  (a) dagens metode, (b) uten «skog uten treslag» i skogcellene, (c) 90-persentil i stedet for 95.
  Vis i en tabell median tregrense per område, H̄ innenfor takseringsområdene og hvor mye de 1 % beste
  cellene flytter seg i høyde. **Stopp og la meg velge variant** før du går videre. Oppdater så
  `config/habitat.toml` og kjør stegene på nytt med `--force`.
- **OneDrive:** Sjekk om `.venv` fortsatt ligger i OneDrive. Gjør den det, si fra og foreslå
  `UV_PROJECT_ENVIRONMENT`. Ikke flytt noe på egen hånd.
- **`.gitignore`:** Ankre mønstrene til roten (`/data/`, `/outputs/`), slik at `web/data/` blir committet.
  Commit også `data/raw/helgeland_lirype_estimater.csv` og `data/raw/helgeland_takseringsomrader.geojson`
  via unntak, slik at andre kan kjøre prosjektet. AR50, DTM og andre store filer skal fortsatt ikke committes.

## 1. Eksport: modul `rypekart.eksport`
Skriv til `web/data/`:
- **`celler.geojson`:** celler med andel_i_takseringsomrade > 0, i EPSG:4326 med 5 desimaler.
  Egenskaper: `id`, `omrade` (1/2/3), `H` (3 desimaler), `cv_fordeling` (2 desimaler), `andel` (2 desimaler),
  `klasse` (dominerende habitatgruppe) og `hoyde` (moh, heltall). Rapporter filstørrelsen.
  Er den over 5 MB, foreslå alternativer før du går videre.
- **`kalibrering.json`:** nøstet som `{omrade: {aar: {total|voksne: {...}}}}`. Hver post har k, k_minus_se,
  k_pluss_se, tetthet, minus_se, pluss_se, cv, estimert_antall og antall ± SE. Ta også med `hbar` og
  `areal_km2` per område.
- **`omrader.geojson`:** unionspolygonene per område med navn og areal. Ta også med de opprinnelige
  polygonene som eget lag, med `polygon_id`.
- **`habitat_H1.png`, `habitat_H2.png`, `habitat_H3.png` og `habitat_bounds.json`:** H for hele
  studieområdet, warpet til EPSG:3857. NaN skal være gjennomsiktig. Bruk en sekvensiell fargeskala som skiller
  seg tydelig fra tetthetsskalaen. Bounds oppgis i lat/lng for `L.imageOverlay`.

Merk: CV_fordeling er uavhengig av år og mål, fordi tetthet = k × H og k bare skalerer. Den kan derfor
gjenbrukes for alle år. Skriv dette i README.

## 2. Webkart: `web/` (Leaflet, ingen byggesteg)
- Bruk vanlig HTML, CSS og JS med ES-moduler. Leaflet og Chart.js lastes fra CDN med låste versjoner.
- **Bakgrunnskart:** Kartverkets cache, `topo` og `topograatone` som lagvalg, med `topograatone` som standard
  fordi det gjør datalagene lettere å lese. Bekreft URL-mønsteret mot Kartverkets dokumentasjon.
  Attribusjon: «© Kartverket». Flisene skal ikke lastes ned eller caches lokalt. Kartverket krever egen
  tillatelse for kopiering fra zoomnivå 12 og opp.
- **Kontroller:** årsvelger 2013–2026 (glider, standard 2026), valg mellom total og voksne, og lagvalg
  mellom tetthet (standard), habitatindeks og usikkerhet.
- **Tetthet per celle:** k[omrade][aar][maal] × H, beregnet i nettleseren. Bruk faste fargeklasser for
  alle år, slik at årene kan sammenlignes. Sett klassene ut fra 99-persentilen over alle år. Legg til
  forklaring (legende).
- **Usikkerhet per celle:** CV_total = √(cv_NINA(omrade, aar, maal)² + cv_fordeling²).
- **Klikk på celle:** tetthet ± SE, H, habitatgruppe og høyde.
- **Sidepanel per område** (åpnes ved klikk på området eller ved valg i liste):
  - estimert antall fugl ± SE for valgt år og mål
  - H̄
  - tidsserie 2013–2026 med SE-bånd, der valgt år er markert
- **«Om kartet»-panel:** metode i kort form, begrensninger og kilder (samme tekst som i README).
  Begrensningene er:
  - vektene er faglige antakelser
  - AR50 er ikke laget for presis arealanalyse
  - tetthet vises bare innenfor takseringsområdene
  - dette er fase 1
- Siden skal fungere på mobil. All tekst skal være på norsk.
- Test lokalt med `uv run python -m http.server -d web`. Ta skjermbilder på desktop- og mobilbredde og se
  over dem selv.

## 3. README.md
Skriv README på norsk med disse delene:
1. **Rypekart Helgeland:** to–tre setninger om hva kartet viser. Plassholder for lenke til kartet på Cloudflare.
2. **Metode i korte trekk:** kalibrering mot NINAs estimater, habitatindeksen (K × T × S × M), følsomhet,
   og hvorfor totalt antall per område ikke avhenger av vektene.
3. **Begrensninger:** som i «Om kartet», og at takseringslinjene ligger i bedre habitat enn omgivelsene
   (H̄ innenfor/utenfor er 1,4–1,7).
4. **Kjøre selv:** `uv sync`, rekkefølgen på stegene, `--force`, `uv run pytest` og eksport og lokal visning.
5. **Datakilder** (bruk denne teksten, og fyll inn det som står i hakeparentes):
   - **Hønsefuglportalen (NINA):** Tetthetsestimater, takseringsinnsats og områdeavgrensninger for
     Helgeland 1–3 er hentet fra Hønsefuglportalens åpne innsyn, <https://honsefugl.nina.no/Innsyn/>,
     den 3. november 2026. Portalen drives av Norsk institutt for naturforskning (NINA). Takseringene er
     gjort på Statskogs grunn. Det er ikke oppgitt noen lisens. Tallene gjengis med kildehenvisning, og
     rettighetene tilhører NINA og Statskog.
   - **AR50 (NIBIO):** Arealressurskart AR50 © Norsk institutt for bioøkonomi (NIBIO), hentet via
     NIBIOs WFS. Lisens: [slå opp i Geonorge-metadata for AR50 og skriv inn den faktiske lisensen.
     Ikke gjett].
   - **Høydedata (Kartverket):** Digital terrengmodell © Kartverket, hentet via WCS. Lisens: CC BY 4.0.
   - **Bakgrunnskart:** Topografisk norgeskart © Kartverket, CC BY 4.0.
6. **Fase 2:** Rådata fra linjetakseringene på Statskogs grunn er publisert åpent på GBIF:
   Nilsen, E. B., Vang, R. & Breisjøberget, J. I. (2022). *Tetraonid line transect surveys from Norway:
   Data from Statskog.* NINA. <https://doi.org/10.15468/q2ehlk>. [Sjekk lisensen på GBIF-siden og skriv
   den inn.]
7. **Lisens:** Koden er lisensiert under MIT, se `LICENSE`. MIT gjelder bare koden. Data og avledede
   datasett følger lisensene til kildene ovenfor.
8. **Bakgrunn:** Prosjektet er laget i emnet *Geografisk IT og kunstig intelligens* ved Universitetet i Agder.

## 4. LICENSE
MIT-lisens med inneværende år. Hent navnet på rettighetshaveren fra `git config user.name`.
Spør meg hvis det mangler.

## 5. Publisering
Legg til en kort seksjon i README om oppsett i Cloudflare Pages: koble til GitHub-repoet, ingen
byggkommando, output-mappe `web`. Ikke publiser noe selv. Jeg kobler opp Cloudflare.

## Til slutt
Oppdater CLAUDE.md med de nye beslutningene, blant annet valgt tregrensevariant og at rådata finnes på GBIF.
Rapporter:
- filstørrelser i `web/data/`
- hva du så på skjermbildene
- lisensene du fant for AR50 og GBIF-datasettet

Ikke commit eller push. Det gjør jeg selv etter gjennomgang.
