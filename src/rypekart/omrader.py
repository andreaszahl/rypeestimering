"""Step 1: survey polygons, study-area rectangles and NINA estimates -> GeoPackage.

Layers written to data/processed/rypekart.gpkg:
- takseringsomrader        (26 polygons, EPSG:25833)
- takseringsomrade_union   (one dissolved (multi)polygon per area; the polygons overlap in H1/H3)
- studieomrade             (one rectangle per area: bbox + 5 km, snapped outward to 250 m)
- estimater                (non-spatial table from the CSV)
"""

import math

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry import box

from rypekart import config, steg

FORVENTET_POLYGONER = {"Helgeland 1": 12, "Helgeland 2": 7, "Helgeland 3": 7}
FORVENTET_AREAL_KM2 = {"Helgeland 1": 142, "Helgeland 2": 190, "Helgeland 3": 674}
FORVENTET_UNION_KM2 = {"Helgeland 1": 138.7, "Helgeland 2": 190.1, "Helgeland 3": 671.0}
FORVENTET_ESTIMATRADER = 42


def les_takseringsomrader() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(config.OMRADER_GEOJSON).to_crs(config.ANALYSE_CRS)
    gdf = gdf.rename(columns={"areal_km2": "areal_km2_kilde"})
    gdf["areal_km2"] = gdf.geometry.area / 1e6
    return gdf


def lag_union(polygoner: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    union = polygoner.dissolve(by="omrade", as_index=False)[["omrade", "geometry"]]
    union["kortnavn"] = union["omrade"].map(config.kortnavn)
    union["areal_km2"] = union.geometry.area / 1e6
    for rad in union.itertuples():
        forventet = FORVENTET_UNION_KM2[rad.omrade]
        assert abs(rad.areal_km2 - forventet) < 0.1, f"{rad.omrade}: union {rad.areal_km2:.2f} km²"
    return union


def lag_studieomrader(polygoner: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    c = config.CELLE
    rader = []
    for omrade, grp in polygoner.groupby("omrade"):
        minx, miny, maxx, maxy = grp.total_bounds
        minx = math.floor((minx - config.BUFFER) / c) * c
        miny = math.floor((miny - config.BUFFER) / c) * c
        maxx = math.ceil((maxx + config.BUFFER) / c) * c
        maxy = math.ceil((maxy + config.BUFFER) / c) * c
        rader.append(
            {
                "omrade": omrade,
                "kortnavn": config.kortnavn(omrade),
                "minx": minx,
                "miny": miny,
                "maxx": maxx,
                "maxy": maxy,
                "kolonner": int((maxx - minx) // c),
                "rader": int((maxy - miny) // c),
                "geometry": box(minx, miny, maxx, maxy),
            }
        )
    gdf = gpd.GeoDataFrame(rader, crs=config.ANALYSE_CRS)
    gdf["areal_km2"] = gdf.geometry.area / 1e6
    return gdf


def sjekk(polygoner: gpd.GeoDataFrame, estimater: pd.DataFrame) -> None:
    antall = polygoner["omrade"].value_counts().to_dict()
    assert len(polygoner) == 26, f"Forventet 26 polygoner, fikk {len(polygoner)}"
    assert antall == FORVENTET_POLYGONER, f"Polygoner per område: {antall}"
    assert len(estimater) == FORVENTET_ESTIMATRADER, f"Estimatrader: {len(estimater)}"

    areal = polygoner.groupby("omrade")["areal_km2"].sum()
    for omrade, forventet in FORVENTET_AREAL_KM2.items():
        avvik = abs(areal[omrade] - forventet) / forventet
        assert avvik < 0.03, f"{omrade}: areal {areal[omrade]:.1f} km² vs forventet ~{forventet}"


def main() -> None:
    config.sikre_mapper()
    polygoner = les_takseringsomrader()
    estimater = pd.read_csv(config.ESTIMATER_CSV)
    sjekk(polygoner, estimater)
    studie = lag_studieomrader(polygoner)
    union = lag_union(polygoner)

    polygoner.to_file(config.GPKG, layer="takseringsomrader", driver="GPKG")
    union.to_file(config.GPKG, layer="takseringsomrade_union", driver="GPKG",
                  promote_to_multi=True)
    studie.to_file(config.GPKG, layer="studieomrade", driver="GPKG")
    pyogrio.write_dataframe(estimater, config.GPKG, layer="estimater", driver="GPKG")
    steg.registrer("omrader")

    print("Takseringsområder (EPSG:25833):")
    oppsummering = polygoner.groupby("omrade").agg(
        polygoner=("polygon_id", "size"),
        areal_km2=("areal_km2", "sum"),
        areal_km2_kilde=("areal_km2_kilde", "sum"),
    )
    oppsummering["areal_km2_union"] = union.set_index("omrade")["areal_km2"]
    print(oppsummering.round(1).to_string())
    print("\nStudieområder (bbox + 5 km, justert til 250 m):")
    print(studie.drop(columns="geometry").round(1).to_string(index=False))
    aar = estimater.groupby("omrade")["aar"].agg(["min", "max", "size"])
    print(f"\nEstimater: {len(estimater)} rader\n{aar.to_string()}")
    print(f"\nSkrevet til {config.GPKG}")


if __name__ == "__main__":
    main()
