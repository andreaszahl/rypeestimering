"""Step 6: habitat index H = K × T × S × M per cell -> columns K, T, S, M, H in `rutenett`.

- K (klasse):    Σ group share × w over the mapped part of the cell (shares rescaled to 1);
                 NaN where «ikke kartlagt» > maks_ikke_kartlagt (Swedish side).
- T (tregrense): t_min + (1 − t_min) · exp(−½ ((rel − mu) / sigma)²), rel = høyde − tregrense.
- S (helning):   1 up to full_til, linear to s_min at min_ved, s_min above.
- M (mosaikk):   (1 + beta · Shannon_norm) / (1 + beta), Shannon over skog/snaumark/myr shares.
- H = NaN where the cell has no elevation data.
Parameters: config/habitat.toml. The pure functions here are reused by `folsomhet` and the tests.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from rypekart import config, lagring, parametere, steg
from rypekart.parametere import MOSAIKKGRUPPER, Parametere
from rypekart.rutenett import AR50_KLASSER


@dataclass
class Habitatdata:
    """Parameter-independent inputs, precomputed once per run."""
    gruppeandel: np.ndarray    # (n × grupper) share of the cell per group (unscaled)
    kartlagt: np.ndarray       # share of the cell that is not excluded
    ikke_kartlagt: np.ndarray  # share excluded («ikke kartlagt»)
    rel: np.ndarray            # hoyde_middel − tregrense_moh (m)
    helning: np.ndarray        # mean slope (deg)
    shannon_norm: np.ndarray   # Shannon over skog/snaumark/myr, / ln 3 (0 if none present)
    omrade: np.ndarray
    areal_km2: np.ndarray      # a_c = andel_i_takseringsomrade × 0.0625


def klassekolonner() -> list[str]:
    return [f"andel_{k}" for k in AR50_KLASSER]


def lag_data(df: pd.DataFrame, par: Parametere) -> Habitatdata:
    parametere.sjekk_klassekobling(par, AR50_KLASSER)
    andeler = df[klassekolonner()].to_numpy()
    gruppeandel = andeler @ parametere.gruppematrise(par, AR50_KLASSER)
    ikke_kartlagt = df[[f"andel_{k}" for k in par.ekskludert]].sum(axis=1).to_numpy()

    mosaikk = np.stack([gruppeandel[:, par.grupper_i_mosaikk(m)].sum(axis=1)
                        for m in MOSAIKKGRUPPER], axis=1)
    total = mosaikk.sum(axis=1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = np.where(total > 0, mosaikk / total, 0.0)
        shannon = -np.where(p > 0, p * np.log(p), 0.0).sum(axis=1) / np.log(len(MOSAIKKGRUPPER))

    return Habitatdata(
        gruppeandel=gruppeandel,
        kartlagt=1.0 - ikke_kartlagt,
        ikke_kartlagt=ikke_kartlagt,
        rel=(df["hoyde_middel"] - df["tregrense_moh"]).to_numpy(),
        helning=df["helning_middel"].to_numpy(),
        shannon_norm=shannon,
        omrade=df["omrade"].to_numpy(),
        areal_km2=df["andel_i_takseringsomrade"].to_numpy() * config.CELLE**2 / 1e6,
    )


def faktor_t(rel, mu, sigma, t_min):
    return t_min + (1 - t_min) * np.exp(-0.5 * ((rel - mu) / sigma) ** 2)


def faktor_s(helning, full_til, min_ved, s_min):
    return np.interp(helning, [full_til, min_ved], [1.0, s_min])  # clamps outside the range


def faktor_m(shannon_norm, beta):
    return (1 + beta * shannon_norm) / (1 + beta)


def beregn(d: Habitatdata, par: Parametere) -> dict[str, np.ndarray]:
    with np.errstate(invalid="ignore", divide="ignore"):
        k = (d.gruppeandel @ par.vekter) / d.kartlagt
    k = np.where((d.ikke_kartlagt > par.maks_ikke_kartlagt) | (d.kartlagt <= 0), np.nan, k)
    t = faktor_t(d.rel, par.mu, par.sigma, par.t_min)          # NaN where elevation is missing
    s = np.where(np.isfinite(d.helning),
                 faktor_s(d.helning, par.helning_full_til, par.helning_min_ved, par.s_min), np.nan)
    m = faktor_m(d.shannon_norm, par.beta)
    h = k * t * s * m
    return {"K": k, "T": t, "S": s, "M": m, "H": h}


def main() -> None:
    if not steg.skal_kjore("habitat", ["tregrense"], [Path(__file__), config.HABITAT_TOML]):
        return
    par = parametere.les()
    kolonner = ["celle_id", "omrade", "andel_i_takseringsomrade", "hoyde_middel",
                "helning_middel", "tregrense_moh", *klassekolonner()]
    df = lagring.les_rutenett(kolonner)
    d = lag_data(df, par)
    res = beregn(d, par)
    ut = pd.DataFrame({"celle_id": df["celle_id"], **res, "shannon_norm": d.shannon_norm})
    lagring.oppdater_kolonner(ut)
    steg.registrer("habitat")

    ut["omrade"] = d.omrade
    ut["inne"] = d.areal_km2 > 0
    print("Habitatfaktorer per område (snitt over celler med H):")
    gyldig = ut[ut["H"].notna()]
    print(gyldig.groupby("omrade")[["K", "T", "S", "M", "H"]].mean().round(3).to_string())
    nan = ut.groupby("omrade").agg(celler=("H", "size"), H_nan=("H", lambda s: s.isna().sum()))
    nan["H_nan_i_taksering"] = ut[ut["inne"]].groupby("omrade")["H"].apply(lambda s: s.isna().sum())
    print("\nCeller med H = NaN:")
    print(nan.fillna(0).astype(int).to_string())
    if nan["H_nan_i_taksering"].fillna(0).sum() > 0:
        print("ADVARSEL: det finnes celler med H = NaN innenfor takseringsområdene.")


if __name__ == "__main__":
    main()
