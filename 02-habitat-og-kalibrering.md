# Prompt 2 – Habitatindeks, kalibrering og følsomhet

Les CLAUDE.md og rapporten fra prompt 1. Vis en plan før du skriver kode, og vis klassekoblingen i steg 2
før du kjører noe som bruker den.

Bakgrunn: Med bare tre områder kan habitatvektene ikke tilpasses statistisk. I fase 1 er vektene faglige
antakelser. De skal ligge samlet i én konfigurasjonsfil, slik at de kan dokumenteres og testes for følsomhet.
Habitatindeksen bestemmer bare hvordan fuglene fordeles innenfor et område. Totalt antall fugl i et
takseringsområde (NINAs tetthet × areal) påvirkes ikke av vektene.

## 1. Opprydding fra prompt 1
- **Overlappende polygoner:** Slå sammen takseringspolygonene per område til lag `takseringsomrade_union`.
  Regn ut `andel_i_takseringsomrade` på nytt mot unionen. Sjekk at arealene blir 138,7 / 190,1 / 671,0 km².
- **Caching i rutenett-steget:** Hopp over steget hvis laget `rutenett` er nyere enn alle inndata.
  `--force` skal tvinge ny kjøring. Gjør det samme for de nye stegene under.

## 2. Konfigurasjon: `config/habitat.toml`
Alle vekter og parametere i dette dokumentet skal ligge her, med en kommentar som begrunner hver verdi.

Klassevekter `w` (0–1) for lirype i august. Koble hver av de 20 AR50-klassene i rutenettet til én gruppe:

| Gruppe | w | Merknad |
|---|---|---|
| Lauvskog, lav bonitet | 1,0 | Fjellbjørkeskog, kjernehabitat |
| Lauvskog, middels/høy bonitet | 0,6 | |
| Skog uten treslag/bonitet | 0,8 | Antatt fjellskog. Flagg antakelsen |
| Blandingsskog | 0,4 | |
| Barskog, lav bonitet | 0,3 | |
| Barskog, middels/høy bonitet | 0,15 | |
| Snaumark, frisk vegetasjon | 0,9 | Vier og lynghei |
| Snaumark, skrinn vegetasjon | 0,6 | |
| Bart fjell / blokkmark | 0,05 | |
| Snø/isbre | 0 | |
| Åpen myr | 0,7 | |
| Myr med skog | 0,7 | |
| Ferskvann / hav | 0 | |
| Jordbruk | 0,2 | |
| Bebygd / samferdsel | 0 | |
| Ikke kartlagt | – | Ekskluderes (se steg 3) |

Hvis en klasse ikke passer i noen gruppe: spør meg, ikke gjett.

## 3. Lokal tregrense: modul `rypekart.tregrense`
- Skogceller er celler med samlet skogandel ≥ 0,5 (alle skoggrupper).
- Del området i blokker på 5×5 km. For hver blokk med minst 20 skogceller: tregrense = 95-persentilen
  av middelhøyden i skogcellene.
- Fyll blokker uten nok skogceller ved interpolasjon fra nabo-blokker, og glatt resultatet.
  Klipp til 250–900 moh.
- Lagre `tregrense_moh` per celle i `rutenett`. Rapporter fordelingen per område og varsle hvis noe ser
  urimelig ut. Forventet nivå er omtrent 400–650 moh.

## 4. Habitatindeks: modul `rypekart.habitat`
For hver celle: `H = K × T × S × M`. Resultatet skal ligge i [0, 1].

- **K (klasse):** Σ andel_klasse × w, regnet over den kartlagte delen av cellen (andelene skaleres opp til 1).
  Er «ikke kartlagt» > 0,5, settes H = NaN (svensk side).
- **T (tregrense):** rel = middelhøyde − tregrense_moh.
  T = t_min + (1 − t_min) · exp(−½ · ((rel − μ) / σ)²), med μ = +50 m, σ = 150 m og t_min = 0,15.
- **S (helning):** 1 opp til 25°, synker lineært til 0,3 ved 45°, og er 0,3 over det.
- **M (mosaikk):** M = (1 + β · Shannon_norm) / (1 + β), med β = 0,2.
  Shannon_norm regnes over tre grupper: skog, snaumark og myr.
- Mangler cellen høydedata, settes H = NaN. Rapporter om noen slike celler ligger innenfor takseringsområdene.
- Lagre K, T, S, M og H som kolonner i `rutenett`.

## 5. Kalibrering: modul `rypekart.kalibrering`
For område a, år t og mål m ∈ {total, voksne}:
- areal per celle: a_c = andel_i_takseringsomrade × 0,0625 km².
- H̄_a = Σ a_c·H_c / Σ a_c over celler med a_c > 0 og H ikke NaN. Rapporter hvor stor del av arealet som falt bort.
- k = tetthet / H̄_a. Beregn også k for estimat − SE og estimat + SE.
- Tetthet i en celle = k × H_c. Den beregnes bare for celler innenfor takseringsområdene.
  Utenfor vises bare H.

Skriv tabellen `kalibrering` med kolonnene omrade, aar, maal, tetthet, minus_se, pluss_se, hbar,
k, k_minus_se, k_pluss_se, areal_km2 (union) og estimert_antall (tetthet × areal) med ± SE.

Skriv også laget `tetthet_2026` (total og voksne, med ± SE) for celler med a_c > 0, slik at det kan kontrolleres.

## 6. Følsomhet: modul `rypekart.folsomhet`
- Gjør 200 Monte Carlo-trekk. I hvert trekk endres parameterne slik:
  - hver klassevekt × lognormal(0, 0,3), klippet til [0, 1]
  - μ ~ U(−50, +150) m
  - σ ~ U(100, 250) m
  - β ~ U(0, 0,4)
  - helningsgrensene ± 5°
- Beregn H og kalibrert total tetthet for 2026 på nytt i hvert trekk.
- Per celle: median, 5- og 95-persentil og CV_fordeling. Lagre i laget `folsomhet`.
- Kombinert usikkerhet per celle (tilnærming): CV_total = √(CV_NINA² + CV_fordeling²).
- Fast frø (seed), slik at resultatet kan gjenskapes.

## 7. Tester (pytest, `tests/`)
- Kalibreringen gjenskaper NINA: Det arealvektede snittet av celletettheten innenfor unionen skal være lik
  NINAs tetthet for alle områder, år og mål (toleranse 1e-6).
- H ligger i [0, 1] eller er NaN. K, T, S og M ligger i forventet område.
- Klasseandelene summerer til 1 (±1e-3).
- Unionsarealene er 138,7 / 190,1 / 671,0 km² (±0,1).
- Følsomhetssteget gir samme resultat to ganger med samme frø.

## 8. Kvalitetssjekk og rapport
PNG-er per område i `outputs/qa/`: tregrense, H med polygonomriss, total tetthet 2026 og CV_total.

Skriv ut:
- Klassekoblingen og hvor mye areal hver gruppe dekker innenfor takseringsområdene.
- **H̄ innenfor vs. utenfor takseringsområdene per område:** Ligger takseringslinjene i bedre habitat enn
  omgivelsene? Dette er viktig hvis vi senere skal ekstrapolere.
- H̄ per område mot snitt-tettheten 2013–2026. Bare tre punkter, så rapporter tallene uten å trekke
  konklusjoner.
- Celler med høyest og lavest tetthet i 2026, og hvilken klasse som dominerer i dem.

Oppdater CLAUDE.md med beslutningene fra denne prompten. Stopp etterpå. Webkartet tar vi i prompt 3.
