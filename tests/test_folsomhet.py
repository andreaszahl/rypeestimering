import numpy as np

from conftest import krever_lag
from rypekart import habitat, lagring, parametere
from rypekart.folsomhet import kjor_trekk


@krever_lag("rutenett")
def test_samme_frø_gir_samme_resultat():
    par = parametere.les()
    kolonner = ["celle_id", "omrade", "andel_i_takseringsomrade", "hoyde_middel",
                "helning_middel", "tregrense_moh", *habitat.klassekolonner()]
    df = lagring.les_rutenett(kolonner, where="andel_i_takseringsomrade > 0")
    d = habitat.lag_data(df, par)
    tetthet = {"Helgeland 1": 10.0, "Helgeland 2": 20.0, "Helgeland 3": 30.0}

    h1, d1, t1 = kjor_trekk(d, par, tetthet, n=4, seed=123)
    h2, d2, t2 = kjor_trekk(d, par, tetthet, n=4, seed=123)
    h3, _, _ = kjor_trekk(d, par, tetthet, n=4, seed=124)

    np.testing.assert_array_equal(h1, h2)
    np.testing.assert_array_equal(d1, d2)
    assert t1.equals(t2)
    assert not np.array_equal(h1, h3, equal_nan=True)
