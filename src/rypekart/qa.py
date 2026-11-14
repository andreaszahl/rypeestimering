"""Step 5: quality check – one PNG per area (AR50 + hillshade) and summary tables."""

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
from matplotlib.colors import LightSource  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from rypekart import config  # noqa: E402
from rypekart.ar50 import AREALTYPE  # noqa: E402
from rypekart.dtm import TERRENG_DIR  # noqa: E402
from rypekart.rutenett import klasser  # noqa: E402

# Conventional map colours per AR50 arealtype
FARGER = {
    10: "#d7301f",  # bebygd
    20: "#f2d94e",  # jordbruk
    30: "#3a7d3a",  # skog
    50: "#d9c7a3",  # snaumark
    60: "#a07fb0",  # myr
    70: "#e8f4f8",  # snø/isbre
    81: "#4a90c8",  # ferskvann
    82: "#1f4e79",  # hav
    99: "#bdbdbd",  # ikke kartlagt
}


def kart(rad, ar50, polygoner) -> None:
    fig, (v, h) = plt.subplots(1, 2, figsize=(14, 9), constrained_layout=True)
    flater = ar50[ar50["omrade"] == rad.omrade]
    flater.plot(ax=v, color=flater["arealtype"].map(FARGER).fillna("#ff00ff"), linewidth=0)
    egne = polygoner[polygoner["omrade"] == rad.omrade]
    egne.boundary.plot(ax=v, color="black", linewidth=1.2)
    tilstede = sorted(flater["arealtype"].dropna().unique())
    fig.legend(handles=[Patch(color=FARGER.get(k, "#ff00ff"), label=AREALTYPE.get(k, str(k)))
                        for k in tilstede] + [Patch(facecolor="none", edgecolor="black",
                                                    label="Takseringsområde")],
               loc="outside lower center", ncol=5, fontsize=8, frameon=False)
    v.set_title(f"{rad.omrade}: AR50 arealtype")

    with rasterio.open(TERRENG_DIR / f"{rad.kortnavn}_terreng.tif") as src:
        z = src.read(1)
        utstrekning = (src.bounds.left, src.bounds.right, src.bounds.bottom, src.bounds.top)
    skygge = LightSource(azdeg=315, altdeg=45).hillshade(
        np.nan_to_num(z, nan=0.0), vert_exag=2, dx=config.DTM_OPPLOSNING, dy=config.DTM_OPPLOSNING)
    skygge = np.where(np.isfinite(z), skygge, np.nan)
    h.imshow(skygge, cmap="gray", extent=utstrekning, interpolation="nearest")
    egne.boundary.plot(ax=h, color="red", linewidth=1.2)
    h.set_title(f"{rad.omrade}: hillshade DTM 25 m (høyde {np.nanmin(z):.0f}–{np.nanmax(z):.0f} m)")

    for ax in (v, h):
        ax.set_xlim(rad.minx, rad.maxx)
        ax.set_ylim(rad.miny, rad.maxy)
        ax.set_aspect("equal")
        ax.tick_params(labelsize=7)
    fig.suptitle("EPSG:25833 · studieområde = takseringspolygonenes bbox + 5 km", fontsize=9)
    ut = config.QA_DIR / f"{rad.kortnavn}_qa.png"
    fig.savefig(ut, dpi=130)
    plt.close(fig)
    print(f"  skrev {ut.relative_to(config.ROOT)}")


def polygonandel_per_klasse(polygoner, ar50) -> pd.DataFrame:
    """Share of each area's survey-polygon area per AR50 class (own area's AR50 only)."""
    deler = []
    for omrade in config.OMRADER:
        egne = polygoner.loc[polygoner["omrade"] == omrade, ["geometry"]]
        flater = ar50[ar50["omrade"] == omrade].copy()
        flater["klasse"] = klasser(flater)
        snitt = gpd.overlay(flater[["klasse", "geometry"]], egne, how="intersection")
        a = snitt.assign(areal=snitt.area).groupby("klasse")["areal"].sum()
        deler.append((a / egne.area.sum()).rename(omrade))
    return pd.concat(deler, axis=1).fillna(0.0)


def main() -> None:
    config.sikre_mapper()
    studie = gpd.read_file(config.GPKG, layer="studieomrade")
    polygoner = gpd.read_file(config.GPKG, layer="takseringsomrader")
    ar50 = gpd.read_file(config.GPKG, layer="ar50")
    rutenett = gpd.read_file(config.GPKG, layer="rutenett", ignore_geometry=True)

    print("QA-kart:")
    for rad in studie.itertuples():
        kart(rad, ar50, polygoner)

    print("\nCeller per område:")
    g = rutenett.groupby("omrade")
    celler = pd.DataFrame({
        "celler": g.size(),
        "celler_i_taksering": g["andel_i_takseringsomrade"].apply(lambda s: (s > 0).sum()),
        "ekvivalent_km2_i_taksering": g["andel_i_takseringsomrade"].sum() * config.CELLE**2 / 1e6,
        "celler_uten_dtm": g["andel_dtm_gyldig"].apply(lambda s: (s == 0).sum()),
        "celler_ar50_sum_under_0_99": g["andel_ar50_sum"].apply(lambda s: (s < 0.99).sum()),
    })
    print(celler.round(1).to_string())

    print("\nHøydespenn (cellemiddel, m):")
    inne = rutenett[rutenett["andel_i_takseringsomrade"] > 0]
    hoyde = pd.DataFrame({
        "studieomrade_min": g["hoyde_middel"].min(),
        "studieomrade_maks": g["hoyde_middel"].max(),
        "taksering_min": inne.groupby("omrade")["hoyde_middel"].min(),
        "taksering_median": inne.groupby("omrade")["hoyde_middel"].median(),
        "taksering_maks": inne.groupby("omrade")["hoyde_middel"].max(),
    })
    print(hoyde.round(0).to_string())

    print("\nAndel av takseringspolygonenes areal per AR50-klasse:")
    andel = polygonandel_per_klasse(polygoner, ar50)
    andel.loc["SUM"] = andel.sum()
    print((andel * 100).round(1).to_string())
    andel.to_csv(config.QA_DIR / "takseringsareal_per_ar50_klasse.csv")


if __name__ == "__main__":
    main()
