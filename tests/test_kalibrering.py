import numpy as np
import pandas as pd
import pyogrio

from conftest import krever_lag
from rypekart import config, lagring
from rypekart.kalibrering import hbar_per_omrade, kalibreringstabell


def _arealvektet_snitt(tetthet, areal):
    ok = np.isfinite(tetthet)
    return np.sum(areal[ok] * tetthet[ok]) / np.sum(areal[ok])


def test_syntetisk_kalibrering_gjenskaper_estimatet():
    rng = np.random.default_rng(1)
    omrade = np.repeat(config.OMRADER, 50)
    h = rng.uniform(0, 1, omrade.size)
    h[::17] = np.nan
    areal = rng.uniform(0, 0.0625, omrade.size)
    areal[::5] = 0
    est = pd.DataFrame({"omrade": config.OMRADER, "aar": 2026,
                        "tetthet": [10.0, 20.0, 30.0], "tetthet_minus_se": [8.0, 15.0, 25.0],
                        "tetthet_pluss_se": [12.0, 25.0, 35.0], "tetthet_voksne": [4.0, 6.0, 9.0],
                        "voksne_minus_se": [3.0, 5.0, 8.0], "voksne_pluss_se": [5.0, 7.0, 10.0]})
    hbar = hbar_per_omrade(h, areal, omrade)
    tab = kalibreringstabell(est, hbar, pd.Series(1.0, index=config.OMRADER))
    for r in tab.itertuples():
        m = (omrade == r.omrade) & (areal > 0)
        for k, maal in ((r.k, r.tetthet), (r.k_minus_se, r.minus_se), (r.k_pluss_se, r.pluss_se)):
            assert abs(_arealvektet_snitt(k * h[m], areal[m]) - maal) < 1e-6


@krever_lag("kalibrering", "rutenett")
def test_kalibreringen_gjenskaper_nina_alle_aar_og_maal():
    tab = pyogrio.read_dataframe(config.GPKG, layer="kalibrering")
    df = lagring.les_rutenett(["omrade", "andel_i_takseringsomrade", "H"],
                              where="andel_i_takseringsomrade > 0")
    areal = df["andel_i_takseringsomrade"].to_numpy() * config.CELLE**2 / 1e6
    assert len(tab) == 84  # 42 estimates × 2 measures
    for r in tab.itertuples():
        m = (df["omrade"] == r.omrade).to_numpy()
        h = df.loc[m, "H"].to_numpy()
        for k, maal in ((r.k, r.tetthet), (r.k_minus_se, r.minus_se), (r.k_pluss_se, r.pluss_se)):
            assert abs(_arealvektet_snitt(k * h, areal[m]) - maal) < 1e-6, (r.omrade, r.aar, r.maal)


@krever_lag("kalibrering", "tetthet_2026")
def test_tetthetslaget_gjenskaper_nina_2026():
    lag = pyogrio.read_dataframe(config.GPKG, layer="tetthet_2026", read_geometry=False)
    est = pyogrio.read_dataframe(config.GPKG, layer="estimater")
    est = est[est["aar"] == 2026].set_index("omrade")
    par = [("tetthet_total", "tetthet"), ("total_minus_se", "tetthet_minus_se"),
           ("total_pluss_se", "tetthet_pluss_se"), ("tetthet_voksne", "tetthet_voksne"),
           ("voksne_minus_se", "voksne_minus_se"), ("voksne_pluss_se", "voksne_pluss_se")]
    for omrade, g in lag.groupby("omrade"):
        for kol, estkol in par:
            snitt = _arealvektet_snitt(g[kol].to_numpy(), g["areal_km2"].to_numpy())
            assert abs(snitt - est.loc[omrade, estkol]) < 1e-6, (omrade, kol)
