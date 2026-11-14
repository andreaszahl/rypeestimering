"""Step 4: 250 m grid per study area with survey overlap, AR50 class shares and terrain stats.

Layer `rutenett` in data/processed/rypekart.gpkg, one row per cell:
- celle_id, omrade, rad, kol (row 0 = northernmost)
- andel_i_takseringsomrade   share of the cell inside the area's survey-polygon union (0–1)
- andel_<klasse>             AR50 area share per class, see AR50_KLASSER
- andel_ar50_sum             sum of the class shares (should be 1)
- hoyde_middel, hoyde_sd, helning_middel, nordlighet_middel, ostlighet_middel, andel_dtm_gyldig

The AR50 classes are mapped to habitat groups in config/habitat.toml. Later steps (tregrense,
habitat) add columns to this layer; re-running this step drops them and forces those steps to rerun.
"""

import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely

from rypekart import config, steg
from rypekart.dtm import TERRENG_DIR

AR50_KLASSER = [
    "bebygd", "jordbruk",
    "skog_lauv_lav", "skog_lauv_middels_hoy", "skog_lauv_uten_bonitet",
    "skog_bar_lav", "skog_bar_middels_hoy", "skog_bar_uten_bonitet",
    "skog_bland", "skog_uten_treslag",
    "bart_fjell", "snaumark_skrint_usammenhengende", "snaumark_lavdekke",
    "snaumark_skrint_til_godt", "snaumark_frodig_usammenhengende", "snaumark_ikke_registrert",
    "myr_apen", "myr_med_skog",
    "sno_isbre", "ferskvann", "hav", "ikke_kartlagt",
]
_TRESLAG = {31: "bar", 32: "lauv"}
_BONITET = {11: "lav", 12: "lav", 13: "middels_hoy", 18: "middels_hoy"}  # 11 impediment, 12 lav
_VEGETASJON = {51: "bart_fjell", 52: "snaumark_skrint_usammenhengende", 53: "snaumark_lavdekke",
               54: "snaumark_skrint_til_godt", 55: "snaumark_frodig_usammenhengende"}
_ENKLE = {10: "bebygd", 20: "jordbruk", 70: "sno_isbre", 81: "ferskvann", 82: "hav",
          99: "ikke_kartlagt"}


def ar50_klasse(arealtype, treslag, skogbonitet, vegetasjonsdekke) -> str:
    if arealtype == 30:
        if treslag == 33:
            return "skog_bland"
        if treslag not in _TRESLAG:
            return "skog_uten_treslag"
        return f"skog_{_TRESLAG[treslag]}_{_BONITET.get(skogbonitet, 'uten_bonitet')}"
    if arealtype == 50:
        return _VEGETASJON.get(vegetasjonsdekke, "snaumark_ikke_registrert")
    if arealtype == 60:
        return "myr_med_skog" if treslag in (31, 32, 33) else "myr_apen"
    return _ENKLE.get(arealtype, "ikke_kartlagt")


def klasser(ar50: pd.DataFrame) -> list[str]:
    koder = ar50[["arealtype", "treslag", "skogbonitet", "vegetasjonsdekke"]].fillna(-1).astype(int)
    return [ar50_klasse(*v) for v in koder.itertuples(index=False)]


def lag_celler(rad) -> gpd.GeoDataFrame:
    c = config.CELLE
    r, k = np.meshgrid(np.arange(rad.rader), np.arange(rad.kolonner), indexing="ij")
    r, k = r.ravel(), k.ravel()
    x0 = rad.minx + k * c
    y1 = rad.maxy - r * c
    celler = gpd.GeoDataFrame(
        {
            "celle_id": [f"{rad.kortnavn}_{ri:03d}_{ki:03d}" for ri, ki in zip(r, k)],
            "omrade": rad.omrade,
            "rad": r,
            "kol": k,
        },
        geometry=shapely.box(x0, y1 - c, x0 + c, y1),
        crs=config.ANALYSE_CRS,
    )
    return celler


def _arealandel(celler: gpd.GeoDataFrame, flater: gpd.GeoDataFrame, nokkel: str | None):
    """Intersection area share per cell (and per `nokkel` value if given) via sjoin + vectorised clip."""
    par = gpd.sjoin(celler[["geometry"]], flater[["geometry"]], predicate="intersects", how="inner")
    i_celle = par.index.to_numpy()
    i_flate = par["index_right"].to_numpy()
    areal = shapely.area(shapely.intersection(
        celler.geometry.to_numpy()[celler.index.get_indexer(i_celle)],
        flater.geometry.to_numpy()[flater.index.get_indexer(i_flate)],
    ))
    df = pd.DataFrame({"celle": i_celle, "andel": areal / config.CELLE**2})
    if nokkel is None:
        return df.groupby("celle")["andel"].sum().reindex(celler.index, fill_value=0.0)
    df["klasse"] = flater.loc[i_flate, nokkel].to_numpy()
    return df.pivot_table(index="celle", columns="klasse", values="andel", aggfunc="sum",
                          fill_value=0.0).reindex(celler.index, fill_value=0.0)


def terrengstatistikk(rad, celler: gpd.GeoDataFrame) -> pd.DataFrame:
    """Block statistics: each 250 m cell is exactly n × n DTM pixels (raster is grid-aligned)."""
    n = config.CELLE // config.DTM_OPPLOSNING
    with rasterio.open(TERRENG_DIR / f"{rad.kortnavn}_terreng.tif") as src:
        assert src.width == rad.kolonner * n and src.height == rad.rader * n
        lag = {src.descriptions[i]: src.read(i + 1) for i in range(src.count)}

    def blokker(a):
        return a.reshape(rad.rader, n, rad.kolonner, n).transpose(0, 2, 1, 3).reshape(
            rad.rader, rad.kolonner, n * n)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN cells -> NaN
        z = blokker(lag["hoyde"])
        stat = {
            "hoyde_middel": np.nanmean(z, axis=2),
            "hoyde_sd": np.nanstd(z, axis=2),
            "helning_middel": np.nanmean(blokker(lag["helning"]), axis=2),
            "nordlighet_middel": np.nanmean(blokker(lag["nordlighet"]), axis=2),
            "ostlighet_middel": np.nanmean(blokker(lag["ostlighet"]), axis=2),
            "andel_dtm_gyldig": np.isfinite(z).mean(axis=2),
        }
    r, k = celler["rad"].to_numpy(), celler["kol"].to_numpy()
    return pd.DataFrame({navn: v[r, k] for navn, v in stat.items()}, index=celler.index)


def lag_rutenett(rad, union: gpd.GeoDataFrame, ar50: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    celler = lag_celler(rad)
    egen = union[union["omrade"] == rad.omrade].reset_index(drop=True)
    celler["andel_i_takseringsomrade"] = _arealandel(celler, egen, None).clip(0, 1)

    flater = ar50[ar50["omrade"] == rad.omrade].reset_index(drop=True)
    flater["klasse"] = klasser(flater)
    andeler = _arealandel(celler, flater, "klasse").reindex(columns=AR50_KLASSER, fill_value=0.0)
    andeler.columns = [f"andel_{k}" for k in andeler.columns]
    celler = celler.join(andeler)
    celler["andel_ar50_sum"] = andeler.sum(axis=1)

    celler = celler.join(terrengstatistikk(rad, celler))
    return celler


def main() -> None:
    if not steg.skal_kjore("rutenett", ["omrader", "ar50", "dtm"], [Path(__file__)]):
        return
    config.sikre_mapper()
    studie = gpd.read_file(config.GPKG, layer="studieomrade")
    union = gpd.read_file(config.GPKG, layer="takseringsomrade_union")
    ar50 = gpd.read_file(config.GPKG, layer="ar50")
    deler = []
    for rad in studie.itertuples():
        print(f"{rad.omrade}: {rad.kolonner}×{rad.rader} = {rad.kolonner * rad.rader} celler")
        deler.append(lag_rutenett(rad, union, ar50))
    rutenett = gpd.GeoDataFrame(pd.concat(deler, ignore_index=True), crs=config.ANALYSE_CRS)
    rutenett.to_file(config.GPKG, layer="rutenett", driver="GPKG")
    steg.registrer("rutenett")

    s = rutenett["andel_ar50_sum"]
    print(f"\nSkrev lag rutenett: {len(rutenett)} celler, {rutenett.shape[1] - 1} kolonner")
    print(f"andel_ar50_sum: min {s.min():.4f}, median {s.median():.4f}, maks {s.max():.4f}; "
          f"celler med sum < 0,99: {(s < 0.99).sum()}, > 1,01: {(s > 1.01).sum()}")
    print(f"Celler uten gyldig DTM: {(rutenett['andel_dtm_gyldig'] == 0).sum()}")
    ekv = rutenett.groupby("omrade")["andel_i_takseringsomrade"].sum() * config.CELLE**2 / 1e6
    print("Takseringsareal fra cellene (km², mot unionen):")
    print(ekv.round(2).to_string())


if __name__ == "__main__":
    main()
