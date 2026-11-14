"""Step 7: calibrate H to NINA's density per area, year and measure.

For area a: a_c = andel_i_takseringsomrade × 0.0625 km², H̄_a = Σ a_c·H_c / Σ a_c over cells with
a_c > 0 and finite H. k = tetthet / H̄_a (also for estimate ± SE). Cell density = k × H_c, only for
cells inside the survey union – so the area-weighted mean density equals NINA's estimate exactly.
Total birds in an area (tetthet × union area) does not depend on the habitat weights.

Writes:
- table `kalibrering`: omrade, aar, maal, tetthet, minus_se, pluss_se, hbar, k, k_minus_se,
  k_pluss_se, areal_km2, estimert_antall, antall_minus_se, antall_pluss_se
- layer `tetthet_<kartaar>`: cells with a_c > 0, total and adult density with ± SE
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio

from rypekart import config, lagring, parametere, steg

# measure -> (estimate, −SE, +SE) columns in the NINA csv
MAAL = {
    "total": ("tetthet", "tetthet_minus_se", "tetthet_pluss_se"),
    "voksne": ("tetthet_voksne", "voksne_minus_se", "voksne_pluss_se"),
}


def hbar_per_omrade(h: np.ndarray, areal_km2: np.ndarray, omrade: np.ndarray) -> pd.DataFrame:
    """Area-weighted mean H inside the union and the share of union area lost to NaN H."""
    rader = []
    for o in config.OMRADER:
        m = (omrade == o) & (areal_km2 > 0)
        ok = m & np.isfinite(h)
        rader.append({
            "omrade": o,
            "hbar": np.sum(areal_km2[ok] * h[ok]) / np.sum(areal_km2[ok]),
            "areal_km2_celler": areal_km2[m].sum(),
            "areal_km2_med_h": areal_km2[ok].sum(),
        })
    df = pd.DataFrame(rader).set_index("omrade")
    df["andel_bortfall"] = 1 - df["areal_km2_med_h"] / df["areal_km2_celler"]
    return df


def kalibreringstabell(estimater: pd.DataFrame, hbar: pd.DataFrame,
                       union_km2: pd.Series) -> pd.DataFrame:
    deler = []
    for maal, (est, minus, pluss) in MAAL.items():
        t = estimater[["omrade", "aar"]].copy()
        t["maal"] = maal
        t["tetthet"] = estimater[est]
        t["minus_se"] = estimater[minus]
        t["pluss_se"] = estimater[pluss]
        deler.append(t)
    tab = pd.concat(deler, ignore_index=True)
    tab["hbar"] = tab["omrade"].map(hbar["hbar"])
    tab["k"] = tab["tetthet"] / tab["hbar"]
    tab["k_minus_se"] = tab["minus_se"] / tab["hbar"]
    tab["k_pluss_se"] = tab["pluss_se"] / tab["hbar"]
    tab["areal_km2"] = tab["omrade"].map(union_km2)
    tab["estimert_antall"] = tab["tetthet"] * tab["areal_km2"]
    tab["antall_minus_se"] = tab["minus_se"] * tab["areal_km2"]
    tab["antall_pluss_se"] = tab["pluss_se"] * tab["areal_km2"]
    return tab.sort_values(["omrade", "maal", "aar"]).reset_index(drop=True)


def celletetthet(celler: pd.DataFrame, tab: pd.DataFrame, aar: int) -> pd.DataFrame:
    """Density per cell (k × H) for one year; `celler` needs omrade and H."""
    ut = {}
    for maal, prefiks in (("total", "total"), ("voksne", "voksne")):
        t = tab[(tab["aar"] == aar) & (tab["maal"] == maal)].set_index("omrade")
        h = celler["H"]
        ut[f"tetthet_{prefiks}"] = celler["omrade"].map(t["k"]) * h
        ut[f"{prefiks}_minus_se"] = celler["omrade"].map(t["k_minus_se"]) * h
        ut[f"{prefiks}_pluss_se"] = celler["omrade"].map(t["k_pluss_se"]) * h
    return pd.DataFrame(ut, index=celler.index)


def main() -> None:
    if not steg.skal_kjore("kalibrering", ["habitat", "omrader"],
                           [Path(__file__), config.HABITAT_TOML]):
        return
    par = parametere.les()
    df = lagring.les_rutenett(["celle_id", "omrade", "andel_i_takseringsomrade", "H"])
    estimater = pyogrio.read_dataframe(config.GPKG, layer="estimater")
    union = gpd.read_file(config.GPKG, layer="takseringsomrade_union").set_index("omrade")

    areal = df["andel_i_takseringsomrade"].to_numpy() * config.CELLE**2 / 1e6
    hbar = hbar_per_omrade(df["H"].to_numpy(), areal, df["omrade"].to_numpy())
    tab = kalibreringstabell(estimater, hbar, union["areal_km2"])
    pyogrio.write_dataframe(tab, config.GPKG, layer="kalibrering", driver="GPKG")

    inne = df["andel_i_takseringsomrade"] > 0
    geo = lagring.les_rutenett(["celle_id"], geometri=True, where="andel_i_takseringsomrade > 0")
    celler = df[inne].reset_index(drop=True)
    assert (geo["celle_id"].to_numpy() == celler["celle_id"].to_numpy()).all()
    celler["areal_km2"] = celler["andel_i_takseringsomrade"] * config.CELLE**2 / 1e6
    celler = celler.drop(columns="andel_i_takseringsomrade")
    celler = celler.join(celletetthet(celler, tab, par.kartaar))
    lag = gpd.GeoDataFrame(celler, geometry=geo.geometry.values, crs=config.ANALYSE_CRS)
    lag.to_file(config.GPKG, layer=f"tetthet_{par.kartaar}", driver="GPKG")
    steg.registrer("kalibrering")

    print("H̄ innenfor takseringsområdene (union):")
    print(hbar.round(4).to_string())
    if (hbar["andel_bortfall"] > 0).any():
        print("MERK: noe takseringsareal mangler H og er utelatt fra H̄ (se andel_bortfall).")
    vis = tab[tab["aar"] == par.kartaar].set_index(["omrade", "maal"])
    print(f"\nKalibrering {par.kartaar}:")
    print(vis[["tetthet", "minus_se", "pluss_se", "hbar", "k", "areal_km2", "estimert_antall",
               "antall_minus_se", "antall_pluss_se"]].round(2).to_string())
    print(f"\nSkrev tabell kalibrering ({len(tab)} rader) og lag tetthet_{par.kartaar} "
          f"({len(lag)} celler)")


if __name__ == "__main__":
    main()
