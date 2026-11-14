"""Step 3: DTM from Kartverket's WCS -> one 25 m GeoTIFF per study area + terrain derivatives.

WCS facts (GetCapabilities / DescribeCoverage, 2026-11-03):
- coverage ``nhm_dtm_topo_25833`` (national DTM, native 1 m), WCS 1.0.0 GetCoverage in EPSG:25833.
- max response size 3840 × 2160 px; default interpolation nearest neighbour; no nodata value set
  (sea and voids are delivered as 0 and masked to NaN here).

Outputs:
- data/raw/dtm/<H>_dtm.tif            elevation (m), 25 m, aligned to the 250 m grid
- data/processed/dtm/<H>_terreng.tif  bands: hoyde, helning (deg), nordlighet, ostlighet
"""

import geopandas as gpd
import numpy as np
import rasterio
import requests
from rasterio.merge import merge
from rasterio.transform import from_origin

from rypekart import config, steg

WCS_URL = "https://wcs.geonorge.no/skwms1/wcs.hoyde-dtm-nhm-25833"
COVERAGE = "nhm_dtm_topo_25833"
FLIS_PX = 1600  # tile size in pixels (40 km at 25 m), below the 3840 × 2160 limit
FLAT_GRADER = 1.0  # below this slope, aspect is undefined -> nordlighet = ostlighet = 0
GYLDIG_HOYDE = (-50.0, 2500.0)  # anything outside is treated as nodata

TERRENG_DIR = config.PROCESSED / "dtm"
BAND = ["hoyde", "helning", "nordlighet", "ostlighet"]


def _hent_flis(fil, bbox, bredde, hoyde) -> None:
    if fil.exists():
        return
    params = {
        "SERVICE": "WCS", "VERSION": "1.0.0", "REQUEST": "GetCoverage", "COVERAGE": COVERAGE,
        "CRS": "EPSG:25833", "RESPONSE_CRS": "EPSG:25833", "FORMAT": "GeoTIFF",
        "BBOX": ",".join(str(int(v)) for v in bbox), "WIDTH": bredde, "HEIGHT": hoyde,
    }
    r = requests.get(WCS_URL, params=params, timeout=600)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image/tiff"):
        raise RuntimeError(f"WCS-feil for {fil.name}: {r.text[:1000]}")
    tmp = fil.with_suffix(".tmp")
    tmp.write_bytes(r.content)
    tmp.replace(fil)


def hent_dtm(rad):
    """Download tiles and merge into one GeoTIFF for the study area (cached)."""
    ut = config.DTM_RAW / f"{rad.kortnavn}_dtm.tif"
    if ut.exists():
        return ut
    res = config.DTM_OPPLOSNING
    flis_m = FLIS_PX * res
    filer = []
    for x0 in range(int(rad.minx), int(rad.maxx), flis_m):
        for y0 in range(int(rad.miny), int(rad.maxy), flis_m):
            x1, y1 = min(x0 + flis_m, int(rad.maxx)), min(y0 + flis_m, int(rad.maxy))
            fil = config.DTM_RAW / f"{rad.kortnavn}_flis_{x0}_{y0}.tif"
            print(f"  {rad.kortnavn}: flis {x0},{y0} ({(x1 - x0) // res}×{(y1 - y0) // res} px)")
            _hent_flis(fil, (x0, y0, x1, y1), (x1 - x0) // res, (y1 - y0) // res)
            filer.append(fil)

    kilder = [rasterio.open(f) for f in filer]
    try:
        mosaikk, transform = merge(kilder, bounds=(rad.minx, rad.miny, rad.maxx, rad.maxy),
                                   res=res, nodata=np.nan)
    finally:
        for k in kilder:
            k.close()
    a = mosaikk[0].astype("float32")
    # The service has no nodata value: sea and data voids (e.g. a rectangular block at the
    # Swedish border in H3) come back as exactly 0. Exact 0 on land is practically impossible
    # for a float DTM, so treat it as nodata.
    a[~np.isfinite(a) | (a == 0) | (a < GYLDIG_HOYDE[0]) | (a > GYLDIG_HOYDE[1])] = np.nan

    profil = {"driver": "GTiff", "dtype": "float32", "count": 1, "crs": config.ANALYSE_CRS,
              "transform": transform, "width": a.shape[1], "height": a.shape[0],
              "nodata": np.nan, "tiled": True, "compress": "deflate", "predictor": 3}
    with rasterio.open(ut, "w", **profil) as dst:
        dst.write(a, 1)
        dst.set_band_description(1, "hoyde")
    return ut


def terrengderivater(z: np.ndarray, res: float):
    """Horn (1981) slope in degrees plus northness/eastness = cos/sin of aspect.

    Aspect is the azimuth of the downslope direction, clockwise from north, so a slope facing
    north gives nordlighet = 1 and one facing east gives ostlighet = 1.
    """
    p = np.pad(z, 1, mode="edge")
    a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    d, f = p[1:-1, :-2], p[1:-1, 2:]
    g, h, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    dz_ost = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * res)
    dz_nord = ((a + 2 * b + c) - (g + 2 * h + i)) / (8 * res)  # row 0 is north
    gradient = np.hypot(dz_ost, dz_nord)
    helning = np.degrees(np.arctan(gradient))
    with np.errstate(invalid="ignore", divide="ignore"):
        nordlighet = np.where(helning >= FLAT_GRADER, -dz_nord / gradient, 0.0)
        ostlighet = np.where(helning >= FLAT_GRADER, -dz_ost / gradient, 0.0)
    ugyldig = ~np.isfinite(helning)
    nordlighet[ugyldig] = np.nan
    ostlighet[ugyldig] = np.nan
    return helning.astype("float32"), nordlighet.astype("float32"), ostlighet.astype("float32")


def lag_terreng(rad, dtm_fil):
    ut = TERRENG_DIR / f"{rad.kortnavn}_terreng.tif"
    if ut.exists() and ut.stat().st_mtime > dtm_fil.stat().st_mtime:
        return ut
    with rasterio.open(dtm_fil) as src:
        z = src.read(1)
        profil = src.profile
    helning, nord, ost = terrengderivater(z, config.DTM_OPPLOSNING)
    profil.update(count=len(BAND))
    with rasterio.open(ut, "w", **profil) as dst:
        for i, (navn, lag) in enumerate(zip(BAND, [z, helning, nord, ost]), start=1):
            dst.write(lag, i)
            dst.set_band_description(i, navn)
    return ut


def sjekk_justering(rad, fil) -> None:
    with rasterio.open(fil) as src:
        forventet = from_origin(rad.minx, rad.maxy, config.DTM_OPPLOSNING, config.DTM_OPPLOSNING)
        assert src.transform.almost_equals(forventet), f"{fil.name}: {src.transform} != {forventet}"
        assert src.width == rad.kolonner * config.CELLE // config.DTM_OPPLOSNING
        assert src.height == rad.rader * config.CELLE // config.DTM_OPPLOSNING


def main() -> None:
    config.sikre_mapper()
    TERRENG_DIR.mkdir(parents=True, exist_ok=True)
    studie = gpd.read_file(config.GPKG, layer="studieomrade")
    for rad in studie.itertuples():
        dtm_fil = hent_dtm(rad)
        sjekk_justering(rad, dtm_fil)
        terreng = lag_terreng(rad, dtm_fil)
        with rasterio.open(terreng) as src:
            z, helning = src.read(1), src.read(2)
        gyldig = np.isfinite(z)
        print(f"{rad.omrade}: {z.shape[1]}×{z.shape[0]} px, gyldig {gyldig.mean():.1%}, "
              f"høyde {np.nanmin(z):.0f}–{np.nanmax(z):.0f} m, "
              f"andel ≤0 m {np.mean(z[gyldig] <= 0):.1%}, "
              f"helning snitt {np.nanmean(helning):.1f}°, maks {np.nanmax(helning):.1f}°")
    steg.registrer("dtm")


if __name__ == "__main__":
    main()
