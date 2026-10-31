PREK = uvx prek@0.5.7

.PHONY: setup grids check test test-contract update-hooks gdal-ecw-image eval-slice smoke-regions

REGIONS ?=
SLICE_STORE ?= $(CURDIR)/uncommitted/eval-slice
CONTRACT_DIR ?= $(CURDIR)/uncommitted/contract-test
SLICE_AREA = --nw "53.922751, -2.004535" --se "53.921852, -2.003013"
SMOKE_DIR ?= $(CURDIR)/uncommitted/smoke-regions
DENVER_AREA = --nw "39.74845, -104.99559" --se "39.74755, -104.99441"
SANAA_AREA = --nw "15.35545, 44.20654" --se "15.35455, 44.20746"

setup:
	git submodule update --init
	uv sync --project pipeline --all-packages --locked
	uv sync --project ml --all-packages --locked
	$(MAKE) grids
	$(PREK) install

grids:
	uv run --project pipeline satmesh grids $(addprefix --region ,$(REGIONS))

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

# 100 m boxes outside England (3DEP lidar at Denver, GLO-30 and FABDEM at Sana'a): build, then export a GLB each; own cache, so the run is cold
smoke-regions:
	cd pipeline && uv run --frozen satmesh build $(DENVER_AREA) --store $(SMOKE_DIR)/denver --cache-dir $(SMOKE_DIR)/cache
	cd pipeline && uv run --frozen satmesh export glb --store $(SMOKE_DIR)/denver --out $(SMOKE_DIR)/denver.glb
	cd pipeline && uv run --frozen satmesh build $(SANAA_AREA) --store $(SMOKE_DIR)/sanaa --cache-dir $(SMOKE_DIR)/cache
	cd pipeline && uv run --frozen satmesh export glb --store $(SMOKE_DIR)/sanaa --out $(SMOKE_DIR)/sanaa.glb
