"""Load and validate config/habitat.toml (class weights and model parameters)."""

import tomllib
from dataclasses import dataclass, field, replace

import numpy as np

from rypekart import config

MOSAIKKGRUPPER = ("skog", "snaumark", "myr")


@dataclass(frozen=True)
class Gruppe:
    id: str
    navn: str
    w: float
    klasser: tuple[str, ...]
    mosaikk: str | None = None
    antakelse: bool = False


@dataclass(frozen=True)
class Parametere:
    grupper: tuple[Gruppe, ...]
    ekskludert: tuple[str, ...]
    maks_ikke_kartlagt: float
    tregrense: dict
    mu: float
    sigma: float
    t_min: float
    helning_full_til: float
    helning_min_ved: float
    s_min: float
    beta: float
    kartaar: int
    folsomhet: dict = field(repr=False)

    @property
    def vekter(self) -> np.ndarray:
        return np.array([g.w for g in self.grupper])

    def med_vekter(self, w: np.ndarray) -> "Parametere":
        grupper = tuple(replace(g, w=float(v)) for g, v in zip(self.grupper, w))
        return replace(self, grupper=grupper)

    def grupper_i_mosaikk(self, navn: str) -> list[int]:
        return [i for i, g in enumerate(self.grupper) if g.mosaikk == navn]


def les(sti=config.HABITAT_TOML) -> Parametere:
    with open(sti, "rb") as f:
        d = tomllib.load(f)
    grupper = tuple(
        Gruppe(id=k, navn=v["navn"], w=float(v["w"]), klasser=tuple(v["klasser"]),
               mosaikk=v.get("mosaikk"), antakelse=v.get("antakelse", False))
        for k, v in d["grupper"].items()
    )
    for g in grupper:
        if not 0 <= g.w <= 1:
            raise ValueError(f"Gruppe {g.id}: w={g.w} er utenfor [0, 1]")
        if g.mosaikk not in (None, *MOSAIKKGRUPPER):
            raise ValueError(f"Gruppe {g.id}: ukjent mosaikkgruppe {g.mosaikk!r}")
    return Parametere(
        grupper=grupper,
        ekskludert=tuple(d["ekskludert"]["klasser"]),
        maks_ikke_kartlagt=float(d["ekskludert"]["maks_ikke_kartlagt"]),
        tregrense=d["tregrense"],
        mu=float(d["tregrensefaktor"]["mu"]),
        sigma=float(d["tregrensefaktor"]["sigma"]),
        t_min=float(d["tregrensefaktor"]["t_min"]),
        helning_full_til=float(d["helning"]["full_til"]),
        helning_min_ved=float(d["helning"]["min_ved"]),
        s_min=float(d["helning"]["s_min"]),
        beta=float(d["mosaikk"]["beta"]),
        kartaar=int(d["kalibrering"]["kartaar"]),
        folsomhet=d["folsomhet"],
    )


def sjekk_klassekobling(par: Parametere, klasser_i_rutenett: list[str]) -> None:
    """Every grid class must belong to exactly one group or be excluded – never guess."""
    tildelt: dict[str, list[str]] = {}
    for g in par.grupper:
        for k in g.klasser:
            tildelt.setdefault(k, []).append(g.id)
    for k in par.ekskludert:
        tildelt.setdefault(k, []).append("ekskludert")

    feil = []
    for k in klasser_i_rutenett:
        if k not in tildelt:
            feil.append(f"  {k}: ikke koblet til noen gruppe")
        elif len(tildelt[k]) > 1:
            feil.append(f"  {k}: koblet til flere grupper {tildelt[k]}")
    ukjente = sorted(set(tildelt) - set(klasser_i_rutenett))
    if ukjente:
        feil.append(f"  klasser i habitat.toml som ikke finnes i rutenett: {ukjente}")
    if feil:
        raise ValueError("Klassekoblingen i habitat.toml er ufullstendig – avklar med bruker:\n"
                         + "\n".join(feil))


def gruppematrise(par: Parametere, klasser_i_rutenett: list[str]) -> np.ndarray:
    """(n_klasser × n_grupper) 0/1-matrix mapping grid classes to groups (excluded rows are 0)."""
    m = np.zeros((len(klasser_i_rutenett), len(par.grupper)))
    for j, g in enumerate(par.grupper):
        for k in g.klasser:
            m[klasser_i_rutenett.index(k), j] = 1.0
    return m
