# Prompt 1 – Prosjektoppsett og datagrunnlag

Les CLAUDE.md først. Lag en plan og vis den før du skriver kode. Ikke bygg modellen ennå – dette steget
skal bare få alle datalag på plass i et felles rutenett.

## 1. Prosjektoppsett
- `uv init` med Python 3.12, pakke `rypekart` under `src/`.
- Avhengigheter: geopandas, pyogrio, shapely, pyproj, rasterio, numpy, pandas, requests, owslib, matplotlib.
- Lag mappene `data/raw`, `data/processed`, `outputs/qa` og en `.gitignore` som utelater `data/` og `outputs/`.
- `helgeland_lirype_estimater.csv` og `helgeland_takseringsomrader.geojson` ligger allerede i `data/raw/`.

## 2. Områder og estimater → GeoPackage
Modul `rypekart.omrader`:
- Les polygonene, reprojiser til EPSG:25833, skriv lag `takseringsomrader` til `data/processed/rypekart.gpkg`.
- Lag `studieomrade`: ett rektangel per område (Helgeland 1, 2, 3) = polygonenes bbox + 5 km buffer, justert til hele 250 m.
- Skriv estimat-CSV-en som ikke-romlig tabell `estimater` i samme GeoPackage.
- Sjekk: 26 polygoner (12/7/7), 42 estimatrader, arealsummer ca. 142 / 190 / 674 km².

## 3. AR50
Modul `rypekart.ar50`:
- Hent AR50 fra NIBIOs WFS (`https://wfs.nibio.no/cgi-bin/ar50_2`). Les GetCapabilities først for å finne riktig
  typename og støttede CRS – ikke gjett. Hent per studieområde med bbox i EPSG:25833, med paginering om nødvendig.
- Cache rådata i `data/raw/ar50/`. Klipp til studieområdene, skriv lag `ar50` til GeoPackage.
- Skriv ut en krysstabell over `ARTYPE` × `ARVEGET` (og `ARTRESLAG` for skog) med areal i km² per område,
  slik at vi kan bestemme habitatklasser i neste steg.
- Hvis WFS feiler: stopp og rapporter feilen, så finner vi alternativ (Geonorge-nedlasting per kommune).

## 4. Terreng (DTM)
Modul `rypekart.dtm`:
- Hent DTM fra Kartverkets WCS (`https://wcs.geonorge.no/skwms1/wcs.hoyde-dtm-nhm-25833`). Finn coverage-navn
  i GetCapabilities. Hent per studieområde med 25 m oppløsning (holder for 250 m-celler), i fliser hvis tjenesten
  har størrelsesgrense. Slå sammen til én GeoTIFF per område i `data/raw/dtm/`.
- Avled helning (grader) og eksposisjon som `nordlighet = cos(aspect)` og `ostlighet = sin(aspect)`.

## 5. Rutenett med variabler
Modul `rypekart.rutenett`:
- 250 m-celler over hvert studieområde, kant justert til multipler av 250 m i EPSG:25833.
- Per celle: `celle_id`, `omrade`, `andel_i_takseringsomrade` (0–1, arealandel som overlapper takseringspolygonene).
- AR50: arealandel per klasse fra krysstabellen (f.eks. skog etter treslag, myr, snaumark per vegetasjonsklasse,
  bart fjell, ferskvann, jordbruk, bebygd). Andelene skal summere til ~1.
- Terreng: middel- og standardavvik for høyde, middel helning, middel nordlighet/østlighet.
- Skriv lag `rutenett` til GeoPackage.

## 6. Kvalitetssjekk
Modul `rypekart.qa`:
- Én PNG per område i `outputs/qa/`: AR50-arealtype med takseringspolygonene oppå, og en hillshade av DTM.
- Skriv ut: antall celler per område, antall celler med `andel_i_takseringsomrade > 0`, høydespenn per område,
  og andel av takseringspolygonenes areal per AR50-klasse.

## Til slutt
Rapporter hva som ble hentet, hva som feilet, og eventuelle overraskelser i dataene. Ikke gå videre til
habitatmodellen – den tar vi i prompt 2 når vi har sett krysstabellen.
