import geopandas as gpd
import numpy as np
import pytest

from conftest import krever_lag
from rypekart import config, lagring
from rypekart.rutenett import AR50_KLASSER


@krever_lag("rutenett")
def test_klasseandelene_summerer_til_1():
    df = lagring.les_rutenett([f"andel_{k}" for k in AR50_KLASSER])
    s = df.sum(axis=1).to_numpy()
    assert np.abs(s - 1).max() < 1e-3


@krever_lag("takseringsomrade_union")
def test_unionsarealene():
    union = gpd.read_file(config.GPKG, layer="takseringsomrade_union").set_index("omrade")
    forventet = {"Helgeland 1": 138.7, "Helgeland 2": 190.1, "Helgeland 3": 671.0}
    for omrade, km2 in forventet.items():
        assert union.loc[omrade, "areal_km2"] == pytest.approx(km2, abs=0.1)


@krever_lag("rutenett", "takseringsomrade_union")
def test_cellene_dekker_hele_unionen():
    union = gpd.read_file(config.GPKG, layer="takseringsomrade_union").set_index("omrade")
    df = lagring.les_rutenett(["omrade", "andel_i_takseringsomrade"])
    km2 = df.groupby("omrade")["andel_i_takseringsomrade"].sum() * config.CELLE**2 / 1e6
    for omrade in config.OMRADER:
        assert km2[omrade] == pytest.approx(union.loc[omrade, "areal_km2"], rel=1e-6)
