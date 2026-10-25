.PHONY: setup check test update-hooks gdal-ecw-image

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
