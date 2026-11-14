"""Shared paths and constants for all pipeline steps."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"
QA_DIR = OUTPUTS / "qa"

GPKG = PROCESSED / "rypekart.gpkg"
OMRADER_GEOJSON = RAW / "helgeland_takseringsomrader.geojson"
ESTIMATER_CSV = RAW / "helgeland_lirype_estimater.csv"
AR50_RAW = RAW / "ar50"
DTM_RAW = RAW / "dtm"
HABITAT_TOML = ROOT / "config" / "habitat.toml"

ANALYSE_CRS = "EPSG:25833"
WEB_CRS = "EPSG:4326"

CELLE = 250  # grid cell size (m)
BUFFER = 5000  # buffer around survey polygons for the study area (m)
DTM_OPPLOSNING = 25  # m; CELLE must be a multiple of this

OMRADER = ["Helgeland 1", "Helgeland 2", "Helgeland 3"]


def kortnavn(omrade: str) -> str:
    """'Helgeland 1' -> 'H1' (used in file names and cell ids)."""
    return "H" + omrade.split()[-1]


def sikre_mapper() -> None:
    for d in (RAW, PROCESSED, QA_DIR, AR50_RAW, DTM_RAW):
        d.mkdir(parents=True, exist_ok=True)
