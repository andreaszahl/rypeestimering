import pyogrio
import pytest

from rypekart import config


def _lag() -> set[str]:
    if not config.GPKG.exists():
        return set()
    return {n for n, _ in pyogrio.list_layers(config.GPKG)}


def krever_lag(*lag: str):
    """Skip a data test unless the pipeline has produced the given GeoPackage layers."""
    mangler = set(lag) - _lag()
    return pytest.mark.skipif(bool(mangler), reason=f"mangler lag {sorted(mangler)} – kjør pipelinen")
