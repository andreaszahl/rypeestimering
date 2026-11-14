"""Step 9: QA maps and report for tree line, habitat index, calibrated density and uncertainty.

One PNG per area in outputs/qa/<H>_habitat.png (tree line, H, total density kartaar, CV_total)
plus printed tables: class→group mapping with area inside the survey union, H̄ inside vs outside,
H̄ vs mean density 2013–2026, and the highest/lowest density cells.
"""

from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyogrio  # noqa: E402

from rypekart import config, habitat, lagring, parametere, steg  # noqa: E402
from rypekart.rutenett import AR50_KLASSER, klasser  # noqa: E402


def _bilde(df: pd.DataFrame, kol: str, rad) -> np.ndarray:
    a = np.full((rad.rader, rad.kolonner), np.nan)
    a[df["rad"].to_numpy(), df["kol"].to_numpy()] = df[kol].to_numpy()
    return a


def kart(rad, df: pd.DataFrame, union: gpd.GeoDataFrame, aar: int) -> Path:
    utstr = (rad.minx, rad.maxx, rad.miny, rad.maxy)
    egen = union[union["omrade"] == rad.omrade]
    paneler = [
        ("tregrense_moh", "Lokal tregrense (moh)", "viridis", None),
        ("H", "Habitatindeks H", "YlGn", (0, 1)),
        ("tetthet_total", f"Total tetthet {aar} (fugl/km²)", "magma_r", None),
        ("cv_total", f"CV_total {aar}", "plasma", None),
    ]
    fig, akser = plt.subplots(2, 2, figsize=(13, 13 * rad.rader / rad.kolonner / 1.6 + 1.5),
                              constrained_layout=True)
    for ax, (kol, tittel, cmap, grenser) in zip(akser.ravel(), paneler):
        bilde = _bilde(df, kol, rad)
        vmin, vmax = grenser or (np.nanpercentile(bilde, 1), np.nanpercentile(bilde, 99))
        if kol in ("tetthet_total", "cv_total"):  # only defined inside the union: grey H underneath
            ax.imshow(_bilde(df, "H", rad), extent=utstr, cmap="Greys", vmin=-1, vmax=2,
                      interpolation="nearest")
        im = ax.imshow(bilde, extent=utstr, cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
        egen.boundary.plot(ax=ax, color="black" if kol != "tetthet_total" else "#1f77b4",
                           linewidth=0.8)
        fig.colorbar(im, ax=ax, shrink=0.8)
        ax.set_title(f"{rad.omrade}: {tittel}", fontsize=10)
        ax.tick_params(labelsize=7)
    fig.suptitle("EPSG:25833 · 250 m celler · omriss = takseringsområde (union). "
                 "Tetthet og CV vises bare innenfor takseringsområdene.", fontsize=9)
    ut = config.QA_DIR / f"{rad.kortnavn}_habitat.png"
    fig.savefig(ut, dpi=110)
    plt.close(fig)
    return ut


def gruppeareal_i_union(par: parametere.Parametere) -> pd.DataFrame:
    """Exact area per habitat group inside each area's survey union (AR50 ∩ union)."""
    ar50 = gpd.read_file(config.GPKG, layer="ar50")
    union = gpd.read_file(config.GPKG, layer="takseringsomrade_union")
    klasse_til_gruppe = {k: g.navn for g in par.grupper for k in g.klasser}
    klasse_til_gruppe.update({k: "Ekskludert (ikke kartlagt)" for k in par.ekskludert})
    deler = []
    for omrade in config.OMRADER:
        f = ar50[ar50["omrade"] == omrade].copy()
        f["gruppe"] = [klasse_til_gruppe[k] for k in klasser(f)]
        snitt = gpd.overlay(f[["gruppe", "geometry"]], union[union["omrade"] == omrade][["geometry"]],
                            how="intersection")
        deler.append(snitt.assign(km2=snitt.area / 1e6).groupby("gruppe")["km2"].sum().rename(omrade))
    return pd.concat(deler, axis=1).fillna(0.0)


def main() -> None:
    if not steg.skal_kjore("qa_habitat", ["folsomhet"], [Path(__file__), config.HABITAT_TOML]):
        return
    par = parametere.les()
    pd.set_option("display.width", 220)
    studie = gpd.read_file(config.GPKG, layer="studieomrade")
    union = gpd.read_file(config.GPKG, layer="takseringsomrade_union")
    kol = ["celle_id", "omrade", "rad", "kol", "andel_i_takseringsomrade", "hoyde_middel",
           "tregrense_moh", "K", "T", "S", "M", "H", *habitat.klassekolonner()]
    df = lagring.les_rutenett(kol)
    tett = pyogrio.read_dataframe(config.GPKG, layer=f"tetthet_{par.kartaar}", read_geometry=False)
    fols = pyogrio.read_dataframe(config.GPKG, layer="folsomhet", read_geometry=False,
                                  columns=["celle_id", "cv_fordeling", "cv_total"])
    df = df.merge(tett[["celle_id", "tetthet_total"]], on="celle_id", how="left")
    df = df.merge(fols, on="celle_id", how="left")

    print("QA-kart:")
    for rad in studie.itertuples():
        ut = kart(rad, df[df["omrade"] == rad.omrade], union, par.kartaar)
        print(f"  skrev {ut.relative_to(config.ROOT)}")

    # 1. class -> group mapping and area inside the survey union
    print("\n1) Klassekobling og areal innenfor takseringsområdene (union):")
    areal = gruppeareal_i_union(par)
    kobling = pd.DataFrame(
        [{"gruppe": g.navn, "w": g.w, "antakelse": "⚑" if g.antakelse else "",
          "klasser": ", ".join(g.klasser)} for g in par.grupper]
        + [{"gruppe": "Ekskludert (ikke kartlagt)", "w": np.nan, "antakelse": "",
            "klasser": ", ".join(par.ekskludert)}]
    ).set_index("gruppe")
    andel = areal / areal.sum() * 100
    kobling = kobling.join(andel.rename(columns=lambda c: f"% {config.kortnavn(c)}")).fillna(
        {f"% {config.kortnavn(c)}": 0.0 for c in config.OMRADER})
    kobling["km² totalt"] = areal.sum(axis=1).reindex(kobling.index).fillna(0.0)
    print(kobling.round(1).assign(w=kobling["w"]).to_string())
    assert set(AR50_KLASSER) == {k for g in par.grupper for k in g.klasser} | set(par.ekskludert)

    # 2. H̄ inside vs outside
    print("\n2) H̄ innenfor vs. utenfor takseringsområdene:")
    a = df["andel_i_takseringsomrade"] * config.CELLE**2 / 1e6
    rader = []
    for o in config.OMRADER:
        m = (df["omrade"] == o) & df["H"].notna()
        inne = m & (a > 0)
        ute = m & (a == 0)
        land = ute & (df[[f"andel_{k}" for k in ("ferskvann", "hav")]].sum(axis=1) < 0.5)
        rader.append({
            "omrade": o,
            "H̄_inne (arealvektet)": np.average(df.loc[inne, "H"], weights=a[inne]),
            "H̄_ute (alle celler)": df.loc[ute, "H"].mean(),
            "H̄_ute (land, <50 % vann)": df.loc[land, "H"].mean(),
            "celler_ute": int(ute.sum()),
            "høyde_inne median": df.loc[inne, "hoyde_middel"].median(),
            "høyde_ute median": df.loc[ute, "hoyde_middel"].median(),
        })
    inne_ute = pd.DataFrame(rader).set_index("omrade")
    inne_ute["forhold inne/ute(land)"] = (inne_ute["H̄_inne (arealvektet)"]
                                          / inne_ute["H̄_ute (land, <50 % vann)"])
    print(inne_ute.round(3).to_string())

    # 3. H̄ vs mean density
    print("\n3) H̄ per område mot snitt-tetthet 2013–2026 (tre punkter – ingen konklusjon):")
    kal = pyogrio.read_dataframe(config.GPKG, layer="kalibrering")
    snitt = kal.pivot_table(index="omrade", columns="maal", values="tetthet", aggfunc="mean")
    snitt.columns = [f"snitt_tetthet_{c}" for c in snitt.columns]
    snitt.insert(0, "H̄", kal.groupby("omrade")["hbar"].first())
    print(snitt.round(3).to_string())

    # 4. highest / lowest density cells
    gruppeandel = df[habitat.klassekolonner()].to_numpy() @ parametere.gruppematrise(par, AR50_KLASSER)
    navn = np.array([g.navn for g in par.grupper])
    df["dominerende_gruppe"] = navn[gruppeandel.argmax(axis=1)]
    df["dominerende_andel"] = gruppeandel.max(axis=1)
    vis = ["celle_id", "tetthet_total", "H", "K", "T", "S", "M", "hoyde_middel", "tregrense_moh",
           "dominerende_gruppe", "dominerende_andel"]
    i = df[(a > 0) & df["tetthet_total"].notna()]
    print(f"\n4) Høyest tetthet {par.kartaar} (fugl/km²):")
    print(i.nlargest(10, "tetthet_total")[vis].round(2).to_string(index=False))
    null = i["tetthet_total"] < 1e-6  # float sums of zero weights are not exactly 0
    print(f"\nCeller med tetthet ≈ 0: {null.sum()} – dominerende grupper: "
          f"{i.loc[null, 'dominerende_gruppe'].value_counts().to_dict()}")
    land = i[["andel_ferskvann", "andel_hav"]].sum(axis=1) < 0.5
    print(f"Lavest tetthet {par.kartaar} blant landceller (< 50 % vann):")
    print(i[land].nsmallest(10, "tetthet_total")[vis].round(3).to_string(index=False))
    steg.registrer("qa_habitat")


if __name__ == "__main__":
    main()
