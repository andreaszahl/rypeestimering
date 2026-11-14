"""Step 2: AR50 from NIBIO's WFS -> cache, clip to study areas, layer `ar50`, crosstab.

WFS facts (read from GetCapabilities / DescribeFeatureType, 2026-11-03):
- typename ``ms:AR50``, WFS 2.0.0 (MapServer), result paging supported, EPSG:25833 supported.
- Attributes are named ``arealtype``, ``treslag``, ``skogbonitet``, ``vegetasjonsdekke``,
  ``jordbruk`` (= ARTYPE, ARTRESLAG, ARSKOGBON, ARVEGET, ARJORDBR in the AR50 file format).
- Code lists: SOSI product specification AR50 v20220523 (NIBIO).

AR50 is suited for visualisation, not precise area analysis (minimum mapping unit 1.5 ha).
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree

import geopandas as gpd
import pandas as pd
import requests
import shapely

from rypekart import config, steg

WFS_URL = "https://wfs.nibio.no/cgi-bin/ar50_2"
TYPENAME = "ms:AR50"
CRS_URN = "urn:ogc:def:crs:EPSG::25833"
FLIS = 10_000  # tile size (m); a 10 km tile holds a few hundred AR50 features

KODEFELT = ["arealtype", "treslag", "skogbonitet", "vegetasjonsdekke", "jordbruk"]

AREALTYPE = {
    10: "Bebygd og samferdsel",
    20: "Jordbruk",
    30: "Skog",
    50: "Snaumark",
    60: "Myr",
    70: "Snø/isbre",
    81: "Ferskvann",
    82: "Hav",
    99: "Ikke kartlagt",
}
TRESLAG = {31: "Barskog", 32: "Lauvskog", 33: "Blandingsskog", 39: "Ikke tresatt",
           98: "Ikke relevant", 99: "Ikke registrert"}
SKOGBONITET = {11: "Impediment", 12: "Lav", 13: "Middels", 18: "Høy og særs høy",
               98: "Ikke relevant", 99: "Ikke registrert"}
VEGETASJONSDEKKE = {51: "Impediment (ikke vegetasjonsdekt)", 52: "Skrint usammenhengende",
                    53: "Lavdekke", 54: "Skrint til godt", 55: "Frodig usammenhengende",
                    98: "Ikke relevant", 99: "Ikke registrert"}


def _get(params: dict, forsok: int = 4) -> bytes:
    for i in range(forsok):
        try:
            r = requests.get(WFS_URL, params=params, timeout=300)
            r.raise_for_status()
            if b"ExceptionReport" in r.content[:2000]:
                raise RuntimeError(f"WFS-feil: {r.content[:1000].decode('utf-8', 'replace')}")
            return r.content
        except (requests.RequestException, RuntimeError) as e:
            if i == forsok - 1:
                raise
            print(f"  forsøk {i + 1} feilet ({e}); prøver igjen")
            time.sleep(5 * (i + 1))
    raise AssertionError


def _har_objekter(fil) -> bool:
    with open(fil, "rb") as f:
        hode = f.read(4000)
    return b'numberReturned="0"' not in hode


def _bbox(rad) -> str:
    return f"{rad.minx},{rad.miny},{rad.maxx},{rad.maxy},{CRS_URN}"


def antall_treff(rad) -> int:
    """numberMatched for the study-area bbox (cached)."""
    cache = config.AR50_RAW / f"{rad.kortnavn}_treff.json"
    if cache.exists():
        return json.loads(cache.read_text())["numberMatched"]
    # SRSNAME must be set here too, otherwise MapServer counts against a reprojected (larger) bbox
    xml = _get({"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
                "TYPENAMES": TYPENAME, "SRSNAME": CRS_URN, "RESULTTYPE": "hits",
                "BBOX": _bbox(rad)})
    n = int(ElementTree.fromstring(xml).attrib["numberMatched"])
    cache.write_text(json.dumps({"numberMatched": n, "bbox": _bbox(rad)}))
    return n


def _fliser(rad):
    """FLIS × FLIS m tiles covering the study-area rectangle."""
    for ix, x0 in enumerate(range(int(rad.minx), int(rad.maxx), FLIS)):
        for iy, y0 in enumerate(range(int(rad.miny), int(rad.maxy), FLIS)):
            yield ix, iy, (x0, y0, min(x0 + FLIS, int(rad.maxx)), min(y0 + FLIS, int(rad.maxy)))


def _hent_flis(kortnavn: str, ix: int, iy: int, bbox) -> gpd.GeoDataFrame | None:
    fil = config.AR50_RAW / f"{kortnavn}_{ix:02d}_{iy:02d}.gml"
    if not fil.exists():
        innhold = _get({"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
                        "TYPENAMES": TYPENAME, "SRSNAME": CRS_URN,
                        "BBOX": ",".join(map(str, bbox)) + f",{CRS_URN}"})
        hode = innhold[:3000]
        if b"next=" in hode:
            raise RuntimeError(f"{fil.name}: svaret er avkortet (har next-lenke) – bruk mindre fliser")
        tmp = fil.with_suffix(".tmp")
        tmp.write_bytes(innhold)
        tmp.replace(fil)
    if not _har_objekter(fil):
        return None
    return gpd.read_file(fil, columns=["lokalid", *KODEFELT])


def hent_omrade(rad) -> gpd.GeoDataFrame:
    """Download (or read cached) AR50 for one study area as spatial tiles.

    STARTINDEX paging on this MapServer WFS is not stable (pages overlap and ~15 % of features
    went missing in a test), so we request small tiles in one go and de-duplicate on lokalid.
    """
    forventet = antall_treff(rad)
    fliser = list(_fliser(rad))
    mangler = sum(not (config.AR50_RAW / f"{rad.kortnavn}_{ix:02d}_{iy:02d}.gml").exists()
                  for ix, iy, _ in fliser)
    if mangler:
        print(f"  {rad.kortnavn}: henter {mangler} av {len(fliser)} fliser")
    with ThreadPoolExecutor(max_workers=4) as pool:
        sider = list(pool.map(lambda f: _hent_flis(rad.kortnavn, *f), fliser))
    sider = [s for s in sider if s is not None and len(s)]

    gdf = pd.concat(sider, ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=config.ANALYSE_CRS)
    unike = gdf["lokalid"].nunique()
    if unike != forventet:
        raise RuntimeError(
            f"{rad.kortnavn}: {unike} unike objekter, men WFS rapporterte {forventet}. "
            "Flisene ga ikke et komplett sett – slett cachen og undersøk."
        )
    return gdf.drop_duplicates("lokalid")


def _polygondel(g):
    if g is None or g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    deler = [d for d in shapely.get_parts(g) if d.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(deler) if deler else None


def klargjor(gdf: gpd.GeoDataFrame, rad) -> gpd.GeoDataFrame:
    for f in KODEFELT:
        gdf[f] = pd.to_numeric(gdf[f], errors="coerce").astype("Int64")
    ugyldig = ~gdf.geometry.is_valid
    if ugyldig.any():
        gdf.loc[ugyldig, "geometry"] = gdf.loc[ugyldig, "geometry"].make_valid()
    gdf = gpd.clip(gdf, rad.geometry)
    # make_valid/clip can return GeometryCollections (polygon + stray lines); keep the polygon parts
    gdf["geometry"] = [_polygondel(g) for g in gdf.geometry]
    tomme = gdf.geometry.isna() | gdf.geometry.is_empty
    if tomme.any():
        print(f"  {rad.kortnavn}: forkaster {tomme.sum()} flater uten polygonareal etter klipping")
    gdf = gdf[~tomme].copy()
    gdf.insert(0, "omrade", rad.omrade)
    gdf["areal_m2"] = gdf.geometry.area
    return gdf


def krysstabell(ar50: gpd.GeoDataFrame) -> pd.DataFrame:
    """Area (km²) per area for every arealtype × treslag × skogbonitet × vegetasjonsdekke."""
    nokler = ["arealtype", "treslag", "skogbonitet", "vegetasjonsdekke"]
    tab = (
        ar50.groupby(nokler + ["omrade"])["areal_m2"].sum().div(1e6)
        .unstack("omrade", fill_value=0.0).reset_index()
    )
    tab.columns.name = None
    omrader = [o for o in config.OMRADER if o in tab.columns]
    tab["sum"] = tab[omrader].sum(axis=1)
    tab.insert(1, "arealtype_navn", tab["arealtype"].map(AREALTYPE))
    tab.insert(3, "treslag_navn", tab["treslag"].map(TRESLAG))
    tab.insert(5, "skogbonitet_navn", tab["skogbonitet"].map(SKOGBONITET))
    tab.insert(7, "vegetasjonsdekke_navn", tab["vegetasjonsdekke"].map(VEGETASJONSDEKKE))
    return tab.sort_values(nokler).reset_index(drop=True)


def skriv_krysstabell(tab: pd.DataFrame) -> None:
    omrader = [o for o in config.OMRADER if o in tab.columns] + ["sum"]
    tab.to_csv(config.QA_DIR / "ar50_krysstabell.csv", index=False)

    with pd.option_context("display.width", 200, "display.max_rows", 200):
        print("\nARTYPE (km², hele studieområdet):")
        art = tab.groupby(["arealtype", "arealtype_navn"])[omrader].sum()
        print(art.round(1).to_string())

        print("\nSkog (30): treslag × skogbonitet (km²):")
        skog = tab[tab["arealtype"] == 30]
        print(skog.groupby(["treslag_navn", "skogbonitet_navn"])[omrader].sum().round(1).to_string())

        print("\nSnaumark (50) og andre: arealtype × vegetasjonsdekke (km²):")
        veg = tab.groupby(["arealtype_navn", "vegetasjonsdekke_navn"])[omrader].sum()
        print(veg[veg["sum"] > 0].round(1).to_string())

        ukjent = tab[tab["arealtype_navn"].isna() | tab["vegetasjonsdekke_navn"].isna()
                     | tab["treslag_navn"].isna() | tab["skogbonitet_navn"].isna()]
        if len(ukjent):
            print("\nADVARSEL: koder som ikke finnes i kodelistene:")
            print(ukjent.round(2).to_string(index=False))


def main() -> None:
    config.sikre_mapper()
    studie = gpd.read_file(config.GPKG, layer="studieomrade")
    deler = []
    for rad in studie.itertuples():
        print(f"{rad.omrade}: {antall_treff(rad)} AR50-objekter i bbox")
        deler.append(klargjor(hent_omrade(rad), rad))
    ar50 = gpd.GeoDataFrame(pd.concat(deler, ignore_index=True), crs=config.ANALYSE_CRS)
    ar50.to_file(config.GPKG, layer="ar50", driver="GPKG", promote_to_multi=True)
    steg.registrer("ar50")
    print(f"\nSkrev lag ar50: {len(ar50)} flater")
    print("Dekningsgrad (AR50-areal / studieområdets areal):")
    dekning = ar50.groupby("omrade")["areal_m2"].sum() / studie.set_index("omrade")["areal_km2"] / 1e6
    print(dekning.round(4).to_string())

    skriv_krysstabell(krysstabell(ar50))
    print(f"\nKrysstabell lagret: {config.QA_DIR / 'ar50_krysstabell.csv'}")


if __name__ == "__main__":
    main()
