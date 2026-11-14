"""Step 10: export data for the static web map to web/data/.

- celler.geojson         cells with andel_i_takseringsomrade > 0 (EPSG:4326, 5 decimals):
                         id, omrade (1/2/3), H, cv_fordeling, andel, klasse (dominant group, short
                         code), hoyde
- habitatgrupper.json    short code -> group id, name and weight (lookup for `klasse`)
- kalibrering.json       {omrade: {hbar, areal_km2, navn, <aar>: {total|voksne: {k, ..., antall ± SE}}}}
- omrader.geojson        survey-union polygons (lag = "union") and original polygons (lag = "polygon")
- habitat_H?.png         H for the whole study area, warped to EPSG:3857, NaN transparent
- habitat_bounds.json    image bounds [[south, west], [north, east]] for L.imageOverlay

Density per cell is computed in the browser as k[omrade][aar][maal] × H. cv_fordeling does not depend
on year or measure because k only scales H, so it is exported once.
"""

import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyogrio
from matplotlib import colormaps
from PIL import Image
from rasterio.transform import array_bounds, from_origin
from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds

from rypekart import config, habitat, lagring, parametere, steg
from rypekart.rutenett import AR50_KLASSER

WEB_DATA = config.ROOT / "web" / "data"
H_FARGESKALA = "YlGnBu"  # habitat index; the density scale in the map is YlOrRd
MAKS_MB = 5.0
# Two-letter codes for `klasse` in celler.geojson keep the file under MAKS_MB (decided 2026-11-14);
# habitatgrupper.json maps them back to group id, name and weight.
KORTKODER = {
    "lauvskog_lav": "LL", "lauvskog_middels_hoy": "LM", "skog_uten_treslag": "SU",
    "blandingsskog": "BL", "barskog_lav": "BA", "barskog_middels_hoy": "BM",
    "snaumark_frisk": "SF", "snaumark_skrinn_til_god": "SG", "snaumark_skrinn": "SS",
    "bart_fjell": "BF", "sno_isbre": "SI", "myr_apen": "MA", "myr_med_skog": "MS",
    "vann": "VA", "jordbruk": "JO", "bebygd": "BE",
}
SKALERING_PNG = 2  # output pixels per 3857 cell size, keeps cell edges crisp when scaled


def _nr(omrade: str) -> int:
    return int(omrade.split()[-1])


def _rund(v, desimaler):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return None
    return round(float(v), desimaler)


def _skriv_json(sti: Path, data) -> None:
    sti.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _ring(geom) -> list:
    return [[round(x, 5), round(y, 5)] for x, y in geom.exterior.coords]


def _polygon_koordinater(geom) -> tuple[str, list]:
    if geom.geom_type == "Polygon":
        return "Polygon", [_ring(geom)] + [[[round(x, 5), round(y, 5)] for x, y in i.coords]
                                           for i in geom.interiors]
    return "MultiPolygon", [_polygon_koordinater(p)[1] for p in geom.geoms]


def eksporter_celler(par: parametere.Parametere) -> Path:
    kol = ["celle_id", "omrade", "andel_i_takseringsomrade", "hoyde_middel", "H",
           *habitat.klassekolonner()]
    df = lagring.les_rutenett(kol, geometri=True, where="andel_i_takseringsomrade > 0")
    fols = pyogrio.read_dataframe(config.GPKG, layer="folsomhet", read_geometry=False,
                                  columns=["celle_id", "cv_fordeling"])
    df = df.merge(fols, on="celle_id", how="left", validate="one_to_one")
    gruppeandel = (df[habitat.klassekolonner()].to_numpy()
                   @ parametere.gruppematrise(par, AR50_KLASSER))
    mangler = {g.id for g in par.grupper} - set(KORTKODER)
    if mangler:
        raise ValueError(f"Habitatgrupper uten kortkode i eksport.KORTKODER: {sorted(mangler)}")
    koder = np.array([KORTKODER[g.id] for g in par.grupper])
    df["klasse"] = koder[gruppeandel.argmax(axis=1)]
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs=config.ANALYSE_CRS).to_crs(config.WEB_CRS)

    features = []
    for r in gdf.itertuples():
        features.append({
            "type": "Feature",
            "properties": {
                "id": r.celle_id,
                "omrade": _nr(r.omrade),
                "H": _rund(r.H, 3),
                "cv_fordeling": _rund(r.cv_fordeling, 2),
                "andel": _rund(r.andel_i_takseringsomrade, 2),
                "klasse": r.klasse,
                "hoyde": None if not math.isfinite(r.hoyde_middel) else int(round(r.hoyde_middel)),
            },
            "geometry": {"type": "Polygon", "coordinates": [_ring(r.geometry)]},
        })
    sti = WEB_DATA / "celler.geojson"
    _skriv_json(sti, {"type": "FeatureCollection", "features": features})

    _skriv_json(WEB_DATA / "habitatgrupper.json",
                {KORTKODER[g.id]: {"id": g.id, "navn": g.navn, "w": g.w, "antakelse": g.antakelse}
                 for g in par.grupper})
    return sti


def eksporter_kalibrering() -> Path:
    tab = pyogrio.read_dataframe(config.GPKG, layer="kalibrering")
    est = pyogrio.read_dataframe(config.GPKG, layer="estimater").set_index(["omrade", "aar"])
    ut = {}
    for omrade, g in tab.groupby("omrade"):
        o = ut.setdefault(str(_nr(omrade)), {
            "navn": omrade,
            "hbar": _rund(g["hbar"].iloc[0], 4),
            "areal_km2": _rund(g["areal_km2"].iloc[0], 2),
        })
        for r in g.itertuples():
            if r.maal == "total":
                cv = est.loc[(omrade, r.aar), "tetthet_cv"]
            else:  # the CSV has no CV for adults: use SE / estimate from the ±SE columns
                cv = (r.pluss_se - r.minus_se) / 2 / r.tetthet
            o.setdefault(str(r.aar), {})[r.maal] = {
                "k": _rund(r.k, 4), "k_minus_se": _rund(r.k_minus_se, 4),
                "k_pluss_se": _rund(r.k_pluss_se, 4),
                "tetthet": _rund(r.tetthet, 2), "minus_se": _rund(r.minus_se, 2),
                "pluss_se": _rund(r.pluss_se, 2), "cv": _rund(cv, 3),
                "estimert_antall": _rund(r.estimert_antall, 0),
                "antall_minus_se": _rund(r.antall_minus_se, 0),
                "antall_pluss_se": _rund(r.antall_pluss_se, 0),
            }
    sti = WEB_DATA / "kalibrering.json"
    _skriv_json(sti, ut)
    return sti


def eksporter_omrader() -> Path:
    union = gpd.read_file(config.GPKG, layer="takseringsomrade_union").to_crs(config.WEB_CRS)
    polygoner = gpd.read_file(config.GPKG, layer="takseringsomrader").to_crs(config.WEB_CRS)
    features = []
    for r in union.itertuples():
        typ, koord = _polygon_koordinater(r.geometry)
        features.append({"type": "Feature",
                         "properties": {"lag": "union", "omrade": _nr(r.omrade), "navn": r.omrade,
                                        "areal_km2": _rund(r.areal_km2, 2)},
                         "geometry": {"type": typ, "coordinates": koord}})
    for r in polygoner.itertuples():
        typ, koord = _polygon_koordinater(r.geometry)
        features.append({"type": "Feature",
                         "properties": {"lag": "polygon", "omrade": _nr(r.omrade), "navn": r.omrade,
                                        "polygon_id": int(r.polygon_id),
                                        "areal_km2": _rund(r.areal_km2, 2)},
                         "geometry": {"type": typ, "coordinates": koord}})
    sti = WEB_DATA / "omrader.geojson"
    _skriv_json(sti, {"type": "FeatureCollection", "features": features})
    return sti


def eksporter_habitatbilder() -> list[Path]:
    studie = gpd.read_file(config.GPKG, layer="studieomrade")
    df = lagring.les_rutenett(["omrade", "rad", "kol", "H"])
    cmap = colormaps[H_FARGESKALA]
    grenser, filer = {}, []
    for rad in studie.itertuples():
        d = df[df["omrade"] == rad.omrade]
        h = np.full((rad.rader, rad.kolonner), np.nan, dtype="float32")
        h[d["rad"].to_numpy(), d["kol"].to_numpy()] = d["H"].to_numpy()
        src_t = from_origin(rad.minx, rad.maxy, config.CELLE, config.CELLE)
        dst_t, b, hgt = calculate_default_transform(
            config.ANALYSE_CRS, "EPSG:3857", rad.kolonner, rad.rader,
            rad.minx, rad.miny, rad.maxx, rad.maxy)
        dst_t = dst_t * dst_t.scale(1 / SKALERING_PNG)
        b, hgt = b * SKALERING_PNG, hgt * SKALERING_PNG
        ut = np.full((hgt, b), np.nan, dtype="float32")
        reproject(h, ut, src_transform=src_t, src_crs=config.ANALYSE_CRS, dst_transform=dst_t,
                  dst_crs="EPSG:3857", resampling=Resampling.nearest,
                  src_nodata=np.nan, dst_nodata=np.nan)
        rgba = (cmap(np.clip(np.nan_to_num(ut, nan=0.0), 0, 1)) * 255).astype("uint8")
        rgba[..., 3] = np.where(np.isfinite(ut), 255, 0)
        sti = WEB_DATA / f"habitat_{rad.kortnavn}.png"
        Image.fromarray(rgba, "RGBA").save(sti, optimize=True)
        filer.append(sti)
        vest, sor, ost, nord = transform_bounds("EPSG:3857", config.WEB_CRS,
                                                *array_bounds(hgt, b, dst_t))
        grenser[rad.kortnavn] = [[round(sor, 6), round(vest, 6)], [round(nord, 6), round(ost, 6)]]
    _skriv_json(WEB_DATA / "habitat_bounds.json", grenser)
    return filer


def main() -> None:
    if not steg.skal_kjore("eksport", ["folsomhet", "omrader"], [Path(__file__), config.HABITAT_TOML]):
        return
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    par = parametere.les()
    celler = eksporter_celler(par)
    mb = celler.stat().st_size / 1e6
    print(f"celler.geojson: {mb:.2f} MB")
    if mb > MAKS_MB:
        raise SystemExit(f"celler.geojson er {mb:.2f} MB (> {MAKS_MB} MB) – vurder alternativer "
                         "før publisering (se prompt 3).")
    eksporter_kalibrering()
    eksporter_omrader()
    eksporter_habitatbilder()
    steg.registrer("eksport")
    print("\nFiler i web/data:")
    for f in sorted(WEB_DATA.iterdir()):
        print(f"  {f.name:24s} {f.stat().st_size / 1e3:9.1f} kB")


if __name__ == "__main__":
    main()
