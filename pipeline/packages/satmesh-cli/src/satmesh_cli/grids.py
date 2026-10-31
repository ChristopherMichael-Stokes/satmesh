"""PROJ datum grids each region needs, and their download into the user's PROJ data directory."""

import subprocess
import sys
from enum import StrEnum


class Region(StrEnum):
    """Areas whose height sources need PROJ grids."""

    GB = "gb"
    GLOBAL = "global"
    US = "us"


# gb: OSTN15 (BNG to ETRS89) and OSGM15 (ODN height). global: EGM2008, the geoid of the GLO-30
# source. us: GEOID18 CONUS, the only grid on the NAD83(2011)+NAVD88 -> NAD83(2011) step (EPSG:6349
# -> 6319); NAD83(2011) -> WGS84 is a null shift.
GRIDS_BY_REGION: dict[Region, tuple[str, ...]] = {
    Region.GB: ("uk_os_OSTN15_NTv2_OSGBtoETRS.tif", "uk_os_OSGM15_GB.tif"),
    Region.GLOBAL: ("us_nga_egm08_25.tif",),
    Region.US: ("us_noaa_g2018u0.tif",),
}


def grid_files(regions: list[Region]) -> list[str]:
    """Grid files for the regions, in table order without repeats; no regions means all."""
    chosen = regions or list(Region)
    return list(dict.fromkeys(name for region in chosen for name in GRIDS_BY_REGION[region]))


def install_grids(files: list[str]) -> None:
    """Install the files into the user's PROJ data directory; `pyproj sync` skips present ones.

    Raises:
        subprocess.CalledProcessError: pyproj could not find or fetch a file.
    """
    for name in files:
        subprocess.run([sys.executable, "-m", "pyproj", "sync", "--file", name], check=True)  # noqa: S603 (fixed argv)
