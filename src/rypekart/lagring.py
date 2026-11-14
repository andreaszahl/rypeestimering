"""Read/write helpers for the `rutenett` layer, which later steps extend with extra columns."""

import geopandas as gpd
import pandas as pd
import pyogrio

from rypekart import config

LAG = "rutenett"


def les_rutenett(kolonner: list[str] | None = None, geometri: bool = False,
                 where: str | None = None) -> pd.DataFrame:
    """Read `rutenett` (optionally a subset of columns) sorted as written (celle order)."""
    return pyogrio.read_dataframe(config.GPKG, layer=LAG, columns=kolonner,
                                  read_geometry=geometri, where=where)


def kolonner_i_rutenett() -> list[str]:
    return list(pyogrio.read_info(config.GPKG, layer=LAG)["fields"])


def oppdater_kolonner(nye: pd.DataFrame) -> None:
    """Replace/add columns in `rutenett`. `nye` must have `celle_id` plus the new columns."""
    gdf = gpd.read_file(config.GPKG, layer=LAG)
    nye_kol = [k for k in nye.columns if k != "celle_id"]
    gdf = gdf.drop(columns=[k for k in nye_kol if k in gdf.columns])
    gdf = gdf.merge(nye, on="celle_id", how="left", validate="one_to_one")
    gdf.to_file(config.GPKG, layer=LAG, driver="GPKG")
