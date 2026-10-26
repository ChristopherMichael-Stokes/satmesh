.PHONY: setup check test update-hooks gdal-ecw-image eval-slice

SLICE_STORE ?= $(CURDIR)/uncommitted/eval-slice
SLICE_AREA = --nw "53.922751, -2.004535" --se "53.921852, -2.003013"

setup:
	uv sync --project pipeline --all-packages --locked
	uv run --project pipeline pyproj sync --file uk_os_OSTN15_NTv2_OSGBtoETRS.tif
	uv run --project pipeline pyproj sync --file uk_os_OSGM15_GB.tif
	prek install

check:
	prek run --all-files

test:
	cd pipeline && uv run --frozen pytest packages

update-hooks:
	prek update --cooldown-days 7

gdal-ecw-image:
	docker build -t satmesh-gdal-ecw docker/gdal-ecw

# 100 m box at Upper Aire: builds a store, then runs every store-based eval check on it
eval-slice:
	cd pipeline && uv run --frozen satmesh build $(SLICE_AREA) --store $(SLICE_STORE)
	cd pipeline && uv run --frozen satmesh eval heights $(SLICE_AREA) --store $(SLICE_STORE)
	cd pipeline && uv run --frozen satmesh eval smoothness $(SLICE_AREA) --store $(SLICE_STORE)
	cd pipeline && uv run --frozen satmesh eval visibility --cameras 10 --range-m 40 $(SLICE_AREA) --store $(SLICE_STORE)
