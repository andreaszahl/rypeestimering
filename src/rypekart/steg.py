"""Step bookkeeping: a `steglogg` table in the GeoPackage records when each step last finished.

A step is up to date when it has finished after every upstream step it depends on and after the
last change to its input files (including its own source file and config/habitat.toml).
Some steps add columns to `rutenett`, so comparing layer timestamps directly would be circular.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyogrio

from rypekart import config

LAG = "steglogg"


def _les() -> dict[str, float]:
    if not config.GPKG.exists():
        return {}
    lag = [n for n, _ in pyogrio.list_layers(config.GPKG)]
    if LAG not in lag:
        return {}
    df = pyogrio.read_dataframe(config.GPKG, layer=LAG)
    return dict(zip(df["steg"], df["fullfort_unix"]))


def registrer(steg: str) -> None:
    logg = _les()
    logg[steg] = datetime.now(timezone.utc).timestamp()
    df = pd.DataFrame({
        "steg": list(logg),
        "fullfort_unix": list(logg.values()),
        "fullfort": [datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")
                     for t in logg.values()],
    })
    pyogrio.write_dataframe(df, config.GPKG, layer=LAG, driver="GPKG")


def er_oppdatert(steg: str, avhenger_av: list[str], filer: list[Path]) -> bool:
    logg = _les()
    if steg not in logg:
        return False
    sist = logg[steg]
    for a in avhenger_av:
        if a not in logg or logg[a] > sist:
            return False
    return all(Path(f).stat().st_mtime <= sist for f in filer)


def skal_kjore(steg: str, avhenger_av: list[str], filer: list[Path]) -> bool:
    """Parse --force and decide whether the step must run; prints why it is skipped."""
    p = argparse.ArgumentParser(prog=f"rypekart.{steg}")
    p.add_argument("--force", action="store_true", help="kjør steget selv om det er oppdatert")
    args = p.parse_args(sys.argv[1:])
    if args.force:
        return True
    if er_oppdatert(steg, avhenger_av, filer):
        print(f"{steg}: oppdatert – hopper over (bruk --force for å kjøre på nytt)")
        return False
    return True
