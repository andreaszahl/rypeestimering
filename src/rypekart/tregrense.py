"""Step 5: local tree line per cell -> column `tregrense_moh` in `rutenett`.

Per study area: 5 × 5 km blocks; for blocks with enough forest cells the tree line is a high
percentile of the forest cells' mean elevation. Empty blocks are filled from neighbouring blocks,
the block grid is smoothed and interpolated bilinearly to the cell centres, then clipped.
All parameters are in [tregrense] in config/habitat.toml.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.interpolate import RegularGridInterpolator

from rypekart import config, lagring, parametere, steg

FORVENTET_MOH = (400, 650)


def skogklasser(par: parametere.Parametere) -> list[str]:
    return [k for i in par.grupper_i_mosaikk("skog") for k in par.grupper[i].klasser]


def _fyll_fra_naboer(b: np.ndarray) -> np.ndarray:
    """Iteratively fill NaN blocks with the mean of their valid 8-neighbours."""
    b = b.copy()
    if np.isnan(b).all():
        raise RuntimeError("Ingen blokker har nok skogceller – kan ikke estimere tregrense")
    while np.isnan(b).any():
        p = np.pad(b, 1, constant_values=np.nan)
        naboer = np.stack([p[1 + dr: 1 + dr + b.shape[0], 1 + dk: 1 + dk + b.shape[1]]
                           for dr in (-1, 0, 1) for dk in (-1, 0, 1) if (dr, dk) != (0, 0)])
        antall = np.isfinite(naboer).sum(axis=0)
        sum_ = np.nansum(naboer, axis=0)
        fyll = np.isnan(b) & (antall > 0)
        b[fyll] = sum_[fyll] / antall[fyll]
    return b


def _glatt(b: np.ndarray, ganger: int) -> np.ndarray:
    for _ in range(ganger):
        p = np.pad(b, 1, mode="edge")
        b = np.mean([p[1 + dr: 1 + dr + b.shape[0], 1 + dk: 1 + dk + b.shape[1]]
                     for dr in (-1, 0, 1) for dk in (-1, 0, 1)], axis=0)
    return b


def beregn_omrade(hoyde: np.ndarray, skog: np.ndarray, tg: dict) -> tuple[np.ndarray, dict]:
    """hoyde/skog are (rader × kolonner) grids. Returns tree line per cell and block info."""
    n = tg["blokk_celler"]
    rader, kolonner = hoyde.shape
    nb_r, nb_k = -(-rader // n), -(-kolonner // n)
    blokk = np.full((nb_r, nb_k), np.nan)
    antall = np.zeros((nb_r, nb_k), dtype=int)
    for i in range(nb_r):
        for j in range(nb_k):
            z = hoyde[i * n:(i + 1) * n, j * n:(j + 1) * n]
            s = skog[i * n:(i + 1) * n, j * n:(j + 1) * n] & np.isfinite(z)
            antall[i, j] = s.sum()
            if antall[i, j] >= tg["min_skogceller"]:
                blokk[i, j] = np.percentile(z[s], tg["persentil"])
    estimert = np.isfinite(blokk)
    glatt = _glatt(_fyll_fra_naboer(blokk), tg["glatting"])

    # bilinear interpolation from block centres (in cell units) to cell centres
    sentre_r = (np.arange(nb_r) + 0.5) * n
    sentre_k = (np.arange(nb_k) + 0.5) * n
    rr, kk = np.meshgrid(np.arange(rader) + 0.5, np.arange(kolonner) + 0.5, indexing="ij")
    rr = np.clip(rr, sentre_r[0], sentre_r[-1])  # constant beyond the outermost block centres
    kk = np.clip(kk, sentre_k[0], sentre_k[-1])
    if nb_r == 1 or nb_k == 1:
        raise RuntimeError("For få blokker til interpolasjon")
    interp = RegularGridInterpolator((sentre_r, sentre_k), glatt, method="linear")
    tregrense = interp(np.stack([rr.ravel(), kk.ravel()], axis=1)).reshape(rader, kolonner)
    tregrense = np.clip(tregrense, tg["min_moh"], tg["maks_moh"])
    info = {
        "blokker": blokk.size,
        "blokker_estimert": int(estimert.sum()),
        "blokk_min": float(np.nanmin(blokk)),
        "blokk_maks": float(np.nanmax(blokk)),
        "blokk_utenfor_klipp": int(((blokk < tg["min_moh"]) | (blokk > tg["maks_moh"])).sum()),
    }
    return tregrense, info


def beregn(df: pd.DataFrame, studie: gpd.GeoDataFrame, par: parametere.Parametere):
    skogandel = df[[f"andel_{k}" for k in skogklasser(par)]].sum(axis=1).to_numpy()
    skog = skogandel >= par.tregrense["skogandel_min"]
    ut = np.full(len(df), np.nan)
    info = {}
    for rad in studie.itertuples():
        m = (df["omrade"] == rad.omrade).to_numpy()
        r, k = df.loc[m, "rad"].to_numpy(), df.loc[m, "kol"].to_numpy()
        hoyde = np.full((rad.rader, rad.kolonner), np.nan)
        s = np.zeros((rad.rader, rad.kolonner), dtype=bool)
        hoyde[r, k] = df.loc[m, "hoyde_middel"].to_numpy()
        s[r, k] = skog[m]
        tg, info[rad.omrade] = beregn_omrade(hoyde, s, par.tregrense)
        info[rad.omrade]["skogceller"] = int(s.sum())
        ut[m] = tg[r, k]
    return ut, info


def main() -> None:
    if not steg.skal_kjore("tregrense", ["rutenett"], [Path(__file__), config.HABITAT_TOML]):
        return
    par = parametere.les()
    studie = gpd.read_file(config.GPKG, layer="studieomrade")
    kolonner = ["celle_id", "omrade", "rad", "kol", "hoyde_middel", "andel_i_takseringsomrade",
                *[f"andel_{k}" for k in skogklasser(par)]]
    df = lagring.les_rutenett(kolonner)
    df["tregrense_moh"], info = beregn(df, studie, par)
    lagring.oppdater_kolonner(df[["celle_id", "tregrense_moh"]])
    steg.registrer("tregrense")

    print("Blokker (5×5 km):")
    print(pd.DataFrame(info).T.round(0).to_string())
    print("\nTregrense per celle (moh):")
    g = df.groupby("omrade")["tregrense_moh"]
    fordeling = g.describe(percentiles=[0.05, 0.5, 0.95])[["min", "5%", "50%", "95%", "max"]]
    inne = df[df["andel_i_takseringsomrade"] > 0].groupby("omrade")["tregrense_moh"]
    fordeling["median_i_taksering"] = inne.median()
    print(fordeling.round(0).to_string())

    advarsler = []
    for omrade, v in fordeling.iterrows():
        if not FORVENTET_MOH[0] <= v["50%"] <= FORVENTET_MOH[1]:
            advarsler.append(f"{omrade}: median {v['50%']:.0f} moh er utenfor forventet "
                             f"{FORVENTET_MOH[0]}–{FORVENTET_MOH[1]} moh")
        klippet = (g.get_group(omrade).isin([par.tregrense["min_moh"],
                                             par.tregrense["maks_moh"]])).mean()
        if klippet > 0.05:
            advarsler.append(f"{omrade}: {klippet:.0%} av cellene er klippet til grenseverdiene")
    for omrade, i in info.items():
        if i["blokk_utenfor_klipp"]:
            advarsler.append(f"{omrade}: {i['blokk_utenfor_klipp']} blokker hadde estimat utenfor "
                             f"klippegrensene (blokkverdier {i['blokk_min']:.0f}–{i['blokk_maks']:.0f})")
    print("\n" + ("\n".join("ADVARSEL: " + a for a in advarsler) if advarsler
                  else "Ingen advarsler: tregrensen ligger innenfor forventet nivå."))


if __name__ == "__main__":
    main()
