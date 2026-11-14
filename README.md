# Rypekart Helgeland

Kartet viser beregnet tetthet av lirype (fugl per km²) i august i Statskogs takseringsområder
Helgeland 1, 2 og 3 for årene 2013–2026, fordelt på ruteceller på 250 × 250 m. Tettheten bygger på
NINAs publiserte estimater fra linjetakseringene og fordeles innenfor hvert område etter en
habitatindeks laget fra arealressurskart og terreng. Utenfor takseringsområdene vises bare habitatindeksen.

**Kartet:** _[lenke til Cloudflare Pages kommer her]_

## Metode i korte trekk

- **Kalibrering mot NINA:** Utgangspunktet er NINAs tetthetsestimat (± 1 SE) per område, år og mål
  (alle fugl eller voksne). For hvert område regnes arealvektet snitt av habitatindeksen H̄ innenfor
  takseringsområdet. Tettheten i en celle er `k × H`, der `k = tetthet / H̄`. Dermed er det arealvektede
  snittet av celletettheten innenfor takseringsområdet nøyaktig lik NINAs estimat (testet med toleranse 1e-6).
- **Habitatindeks** `H = K × T × S × M`, med verdier fra 0 til 1:
  - **K (klasse):** arealvektet sum av vekter for 16 habitatgrupper fra AR50, for eksempel fjellbjørkeskog
    (1,0), frisk snaumark (0,9) og myr (0,7). Vektene er samlet og begrunnet i
    [`config/habitat.toml`](config/habitat.toml).
  - **T (tregrense):** en gaussisk topp like over den lokale tregrensa, som er beregnet fra skogens
    høydefordeling i blokker på 5 × 5 km.
  - **S (helning):** full verdi opp til 25°, synker til 0,3 ved 45°.
  - **M (mosaikk):** en liten bonus for blanding av skog, snaumark og myr i cellen.
- **Følsomhet:** 200 Monte Carlo-trekk der vektene og parameterne varieres (fast frø). Spredningen gir
  CV<sub>fordeling</sub> per celle. Kartets usikkerhetslag viser
  CV<sub>total</sub> = √(CV<sub>NINA</sub>² + CV<sub>fordeling</sub>²), som er en tilnærming.
  CV<sub>fordeling</sub> er uavhengig av år og mål fordi tetthet = k × H og k bare skalerer.
  Den regnes derfor én gang og gjenbrukes for alle år.
- **Totalen avhenger ikke av vektene:** Antall fugl i et område er NINAs tetthet × areal av
  takseringsområdet. Habitatvektene bestemmer bare hvordan fuglene fordeles innenfor området.

## Begrensninger

- Habitatvektene er faglige antakelser. Med bare tre områder kan de ikke tilpasses statistisk.
- AR50 er laget for oversikt, ikke for presis arealanalyse (minste kartleggingsenhet 1,5 hektar).
  1 070 km² skog mangler treslag og bonitet og er antatt å være fjellskog.
- Tetthet vises bare innenfor takseringsområdene. Utenfor vises bare habitatindeksen.
- Takseringsområdene ligger i bedre habitat enn omgivelsene: H̄ innenfor er 1,4–1,7 ganger H̄ utenfor.
  Tettheten kan derfor ikke uten videre overføres til områdene rundt.
- Dette er fase 1. Rådataene fra linjetakseringene er ikke brukt ennå (se Fase 2).

## Kjøre selv

Krever [uv](https://docs.astral.sh/uv/). Nedlastinger fra NIBIO og Kartverket caches i `data/raw/`,
og resultatene skrives til `data/processed/rypekart.gpkg`.

```bash
uv sync
```

Stegene kjøres i denne rekkefølgen:

```bash
uv run python -m rypekart.omrader      # takseringsområder, union og estimater
uv run python -m rypekart.ar50         # AR50 fra NIBIOs WFS
uv run python -m rypekart.dtm          # terrengmodell fra Kartverkets WCS
uv run python -m rypekart.rutenett     # 250 m-rutenett med arealklasser og terreng
uv run python -m rypekart.tregrense    # lokal tregrense
uv run python -m rypekart.habitat      # habitatindeks H = K × T × S × M
uv run python -m rypekart.kalibrering  # kalibrering mot NINA
uv run python -m rypekart.folsomhet    # Monte Carlo-følsomhet
uv run python -m rypekart.qa_habitat   # QA-kart og rapport i outputs/qa/
uv run python -m rypekart.eksport      # data til webkartet i web/data/
```

Fra og med `rutenett` hopper et steg over seg selv hvis det allerede er oppdatert i forhold til stegene
før, sin egen kode og `config/habitat.toml`. Legg til `--force` for å kjøre et steg på nytt likevel.

Tester:

```bash
uv run pytest
```

Lokal visning av webkartet på <http://localhost:8000>:

```bash
uv run python -m http.server -d web
```

## Publisering på Cloudflare Pages

Webkartet er en statisk side uten byggesteg. I Cloudflare Pages:

1. Opprett et prosjekt med *Connect to Git* og velg GitHub-repoet.
2. *Framework preset*: None. *Build command*: tom. *Build output directory*: `web`.
3. Hver push til `main` publiserer siden på nytt.

## Datakilder

- **Hønsefuglportalen (NINA):** Tetthetsestimater, takseringsinnsats og områdeavgrensninger for
  Helgeland 1–3 er hentet fra Hønsefuglportalens åpne innsyn, <https://honsefugl.nina.no/Innsyn/>,
  den 3. november 2026. Portalen drives av Norsk institutt for naturforskning (NINA). Takseringene er
  gjort på Statskogs grunn. Det er ikke oppgitt noen lisens. Tallene gjengis med kildehenvisning, og
  rettighetene tilhører NINA og Statskog.
- **AR50 (NIBIO):** Arealressurskart AR50 © Norsk institutt for bioøkonomi (NIBIO), hentet via
  NIBIOs WFS. Lisens: Norsk lisens for offentlige data (NLOD) 1.0, ifølge Geonorge-metadata for
  AR50 (åpne data).
- **Høydedata (Kartverket):** Digital terrengmodell © Kartverket, hentet via WCS. Lisens: CC BY 4.0.
- **Bakgrunnskart:** Topografisk norgeskart © Kartverket, CC BY 4.0.

## Fase 2

Rådata fra linjetakseringene på Statskogs grunn er publisert åpent på GBIF:
Nilsen, E. B., Vang, R. & Breisjøberget, J. I. (2022). *Tetraonid line transect surveys from Norway:
Data from Statskog.* NINA. <https://doi.org/10.15468/q2ehlk>. Lisens: CC BY 4.0.

Med rådataene kan vi i fase 2 lage en egen deteksjonsfunksjon og en density surface model, i stedet for
å nedskalere de publiserte estimatene.

## Lisens

Koden er lisensiert under MIT, se [`LICENSE`](LICENSE). MIT gjelder bare koden. Data og avledede
datasett, også filene i `data/raw/` og `web/data/`, følger lisensene til kildene ovenfor.

## Bakgrunn

Prosjektet er laget i emnet *Geografisk IT og kunstig intelligens* ved Universitetet i Agder.
