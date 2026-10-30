PREK = uvx prek@0.5.7

.PHONY: setup check test test-contract update-hooks gdal-ecw-image eval-slice

SLICE_STORE ?= $(CURDIR)/uncommitted/eval-slice
CONTRACT_DIR ?= $(CURDIR)/uncommitted/contract-test
SLICE_AREA = --nw "53.922751, -2.004535" --se "53.921852, -2.003013"

setup:
	uv sync --project pipeline --all-packages --locked
	uv sync --project ml --all-packages --locked
	uv run --project pipeline pyproj sync --file uk_os_OSTN15_NTv2_OSGBtoETRS.tif
	uv run --project pipeline pyproj sync --file uk_os_OSGM15_GB.tif
	$(PREK) install

check:
	$(PREK) run --all-files

test:
	cd pipeline && uv run --frozen pytest packages
	cd ml && uv run --frozen pytest packages

# pipeline writes inputs, ml refines them, pipeline reads the outputs, through $(CONTRACT_DIR)
test-contract:
	cd pipeline && SATMESH_CONTRACT_DIR=$(CONTRACT_DIR) uv run --frozen pytest packages/satmesh-cli/tests/test_ml_contract.py -k write
	cd ml && SATMESH_CONTRACT_DIR=$(CONTRACT_DIR) uv run --frozen pytest packages/satmesh-height/tests/test_contract_roundtrip.py
	cd pipeline && SATMESH_CONTRACT_DIR=$(CONTRACT_DIR) uv run --frozen pytest packages/satmesh-cli/tests/test_ml_contract.py -k read

# rewrites agent-docs/INDEX.md from the doc headers
docs-index:
	uv run --no-project --python 3.13 python scripts/agent_docs.py index

update-hooks:
	$(PREK) update --cooldown-days 7

gdal-ecw-image:
	docker build -t satmesh-gdal-ecw docker/gdal-ecw

# 100 m box at Upper Aire: builds a store, then runs every store-based eval check on it
eval-slice:
	cd pipeline && uv run --frozen satmesh build $(SLICE_AREA) --store $(SLICE_STORE)
	cd pipeline && uv run --frozen satmesh eval heights $(SLICE_AREA) --store $(SLICE_STORE)
	cd pipeline && uv run --frozen satmesh eval smoothness $(SLICE_AREA) --store $(SLICE_STORE)
	cd pipeline && uv run --frozen satmesh eval visibility --cameras 10 --range-m 40 $(SLICE_AREA) --store $(SLICE_STORE)
