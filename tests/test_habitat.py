import numpy as np
import pytest

from conftest import krever_lag
from rypekart import habitat, lagring, parametere
from rypekart.rutenett import AR50_KLASSER

PAR = parametere.les()


def test_klassekoblingen_er_komplett():
    parametere.sjekk_klassekobling(PAR, AR50_KLASSER)
    m = parametere.gruppematrise(PAR, AR50_KLASSER)
    ekskludert = [AR50_KLASSER.index(k) for k in PAR.ekskludert]
    assert (np.delete(m, ekskludert, axis=0).sum(axis=1) == 1).all()


def test_manglende_klasse_stopper():
    with pytest.raises(ValueError, match="ikke koblet"):
        parametere.sjekk_klassekobling(PAR, [*AR50_KLASSER, "ny_klasse"])


def test_faktor_t():
    assert habitat.faktor_t(PAR.mu, PAR.mu, PAR.sigma, PAR.t_min) == pytest.approx(1.0)
    assert habitat.faktor_t(5000, PAR.mu, PAR.sigma, PAR.t_min) == pytest.approx(PAR.t_min)


def test_faktor_s():
    s = habitat.faktor_s(np.array([0, 25, 35, 45, 80]), 25, 45, 0.3)
    assert s == pytest.approx([1.0, 1.0, 0.65, 0.3, 0.3])


def test_faktor_m():
    assert habitat.faktor_m(0.0, 0.2) == pytest.approx(1 / 1.2)
    assert habitat.faktor_m(1.0, 0.2) == pytest.approx(1.0)


@krever_lag("rutenett")
def test_faktorene_ligger_i_forventet_omrade():
    df = lagring.les_rutenett(["K", "T", "S", "M", "H"])
    eps = 1e-9

    def innenfor(kol, lav, hoy):
        v = df[kol].dropna().to_numpy()
        assert v.size > 0
        assert ((v >= lav - eps) & (v <= hoy + eps)).all(), kol

    innenfor("K", 0, 1)
    innenfor("T", PAR.t_min, 1)
    innenfor("S", PAR.s_min, 1)
    innenfor("M", 1 / (1 + PAR.beta), 1)
    innenfor("H", 0, 1)
    assert df["H"].isna().sum() < len(df)
