"""Step 8: Monte Carlo sensitivity of H and calibrated total density (kartaar) to the assumptions.

Each draw perturbs (see [folsomhet] in config/habitat.toml):
- every group weight × lognormal(0, sd), clipped to [0, 1]
- mu ~ U, sigma ~ U, beta ~ U
- both slope limits shifted by U(−delta, +delta)
and recomputes H, H̄ per area, k and cell density. Total birds per area are unchanged by design.

Writes layer `folsomhet` (all cells): H_median/p05/p95/cv and, inside the survey union,
tetthet_median/p05/p95, cv_fordeling, cv_nina and cv_total = √(cv_nina² + cv_fordeling²).
Also writes table `folsomhet_trekk` with the parameters and H̄ of every draw.
"""

from dataclasses import replace
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio

from rypekart import config, habitat, lagring, parametere, steg
from rypekart.kalibrering import hbar_per_omrade


def trekk_parametere(par: parametere.Parametere, rng: np.random.Generator) -> parametere.Parametere:
    f = par.folsomhet
    w = np.clip(par.vekter * np.exp(rng.normal(0.0, f["vekt_lognormal_sd"], len(par.grupper))),
                0.0, 1.0)
    d = f["helning_delta"]
    return replace(
        par.med_vekter(w),
        mu=rng.uniform(*f["mu"]),
        sigma=rng.uniform(*f["sigma"]),
        beta=rng.uniform(*f["beta"]),
        helning_full_til=par.helning_full_til + rng.uniform(-d, d),
        helning_min_ved=par.helning_min_ved + rng.uniform(-d, d),
    )


def kjor_trekk(d: habitat.Habitatdata, par: parametere.Parametere,
               tetthet: dict[str, float], n: int, seed: int):
    """Returns (H draws (n × celler), density draws (n × celler inside union), draw table)."""
    rng = np.random.default_rng(seed)
    inne = d.areal_km2 > 0
    h_trekk = np.empty((n, len(d.rel)), dtype=np.float32)
    d_trekk = np.empty((n, inne.sum()), dtype=np.float32)
    k_celle = np.empty(inne.sum())
    rader = []
    for i in range(n):
        p = trekk_parametere(par, rng)
        h = habitat.beregn(d, p)["H"]
        hbar = hbar_per_omrade(h, d.areal_km2, d.omrade)["hbar"]
        for o in hbar.index:
            k_celle[d.omrade[inne] == o] = tetthet[o] / hbar[o]
        h_trekk[i] = h
        d_trekk[i] = k_celle * h[inne]
        rader.append({"trekk": i, "mu": p.mu, "sigma": p.sigma, "beta": p.beta,
                      "helning_full_til": p.helning_full_til,
                      "helning_min_ved": p.helning_min_ved,
                      **{f"w_{g.id}": g.w for g in p.grupper},
                      **{f"hbar_{config.kortnavn(o)}": v for o, v in hbar.items()}})
    return h_trekk, d_trekk, pd.DataFrame(rader)


def statistikk(trekk: np.ndarray, prefiks: str) -> dict[str, np.ndarray]:
    """Median, P5, P95 and CV per column; columns that are NaN in any draw stay NaN."""
    ut = {f"{prefiks}_{n}": np.full(trekk.shape[1], np.nan) for n in ("median", "p05", "p95", "cv")}
    ok = np.isfinite(trekk).all(axis=0)
    x = trekk[:, ok].astype(np.float64)
    p05, med, p95 = np.percentile(x, [5, 50, 95], axis=0)
    snitt = x.mean(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        cv = np.where(snitt > 0, x.std(axis=0, ddof=1) / snitt, np.nan)
    for navn, v in (("median", med), ("p05", p05), ("p95", p95), ("cv", cv)):
        ut[f"{prefiks}_{navn}"][ok] = v
    return ut


def main() -> None:
    if not steg.skal_kjore("folsomhet", ["kalibrering"], [Path(__file__), config.HABITAT_TOML]):
        return
    par = parametere.les()
    f = par.folsomhet
    kolonner = ["celle_id", "omrade", "andel_i_takseringsomrade", "hoyde_middel",
                "helning_middel", "tregrense_moh", *habitat.klassekolonner()]
    df = lagring.les_rutenett(kolonner)
    d = habitat.lag_data(df, par)
    est = pyogrio.read_dataframe(config.GPKG, layer="estimater")
    est = est[est["aar"] == par.kartaar].set_index("omrade")
    tetthet = est["tetthet"].to_dict()

    print(f"Kjører {f['trekk']} trekk (seed {f['seed']}) …")
    h_trekk, d_trekk, trekktabell = kjor_trekk(d, par, tetthet, f["trekk"], f["seed"])

    ut = pd.DataFrame({"celle_id": df["celle_id"], "omrade": df["omrade"]})
    for navn, v in statistikk(h_trekk, "H").items():
        ut[navn] = v
    inne = d.areal_km2 > 0
    for navn, v in statistikk(d_trekk, "tetthet").items():
        kol = "cv_fordeling" if navn == "tetthet_cv" else navn
        ut[kol] = np.nan
        ut.loc[inne, kol] = v
    ut["cv_nina"] = np.where(inne, df["omrade"].map(est["tetthet_cv"]), np.nan)
    ut["cv_total"] = np.sqrt(ut["cv_nina"] ** 2 + ut["cv_fordeling"] ** 2)

    geo = lagring.les_rutenett(["celle_id"], geometri=True)
    assert (geo["celle_id"].to_numpy() == ut["celle_id"].to_numpy()).all()
    lag = gpd.GeoDataFrame(ut, geometry=geo.geometry.values, crs=config.ANALYSE_CRS)
    lag.to_file(config.GPKG, layer="folsomhet", driver="GPKG")
    pyogrio.write_dataframe(trekktabell, config.GPKG, layer="folsomhet_trekk", driver="GPKG")
    steg.registrer("folsomhet")

    i = ut[inne]
    print("\nInnenfor takseringsområdene (celler):")
    oppsum = i.groupby("omrade").agg(
        cv_nina=("cv_nina", "first"),
        cv_fordeling_median=("cv_fordeling", "median"),
        cv_fordeling_p95=("cv_fordeling", lambda s: s.quantile(0.95)),
        cv_total_median=("cv_total", "median"),
    )
    print(oppsum.round(3).to_string())
    hb = trekktabell[[c for c in trekktabell if c.startswith("hbar_")]]
    print("\nH̄ over trekkene (P5 / median / P95):")
    print(hb.quantile([0.05, 0.5, 0.95]).round(3).to_string())


if __name__ == "__main__":
    main()
