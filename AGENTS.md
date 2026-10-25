# AGENTS.md: satmesh

Research tool that builds textured 3D terrain meshes from Esri World Imagery tiles and DEMs, at the
finest ground sample distance the sources support, enhanced by classical processing and ML.

## Layout

| Path          | uv workspace | Holds                                                              |
| ------------- | ------------ | ------------------------------------------------------------------ |
| `pipeline/`   | yes          | `satmesh-core` (AOI, metric CRS, tile geometry, GSD), `satmesh-data` (Esri tiles, EA DTM and DSM, tile mosaic), `satmesh-mesh` (grid TIN, skirts, GLB), `satmesh-tiles` (georeferenced node store, tiler, 3D Tiles, Gazebo and area GLB exporters), `satmesh-eval` (height scores, pipeline check; imagery offset and camera visibility to come), `satmesh-cli` (`satmesh` command) |
| `agent-docs/` | no           | Docs written by and for agents: briefs, plans, research reports    |
| `docs/`       | no           | Human-facing docs                                                  |
| `docker/`     | no           | Images for tools no wheel ships: `gdal-ecw` converts ECW to GeoTIFF |
| root          | no           | Shared checks (`prek.toml`), `ruff.toml`, `Makefile`, `TODO.md`    |

- Each workspace has its own `uv.lock` and `.venv`. Members live at
  `<workspace>/packages/<dist-name>/src/<module>/` and are picked up by the `packages/*` glob.
- An `ml/` workspace is added when a model's dependencies conflict with `pipeline/`. Workspaces meet
  through exported model files, with a contract test.

## Agent docs

- `agent-docs/` holds session briefs, plans and research reports for agents. Human-facing docs
  (`README.md`, any `docs/`) never link into it, and agent material never goes in them.
- A brief is self-contained: a fresh session runs it with no access to the conversation that
  wrote it.
- Plans and reports a session produces land in `agent-docs/` beside the brief that asked for
  them.
- `TODO.md` is the concise task list; `agent-docs/implementation-plan.md` holds the detail.
- `agent-docs/status.md` is the running log of state, decisions with reasons and open risks; update
  it at every checkpoint, and write a `<feature>-results.md` with measurements and traps found.

## Hard constraints

- **Fetched tiles, DEMs, exported models and generated meshes are build outputs.** Never commit
  them (`.gitignore` covers the usual formats).
- **Esri tile etiquette:** cache every tile by (z, y, x), throttle requests with backoff, send a
  descriptive User-Agent, and never request past the source's `MaxMapLevel`.
- **Python:** 3.13 is the baseline (`.python-version`). `requires-python` stays open-ended
  (`>=3.13`) with no upper bound.

## Commands

Run from the repo root unless a workspace is named.

| What                         | Command                                                 |
| ---------------------------- | ------------------------------------------------------- |
| Install prek (once)          | `uv tool install prek@0.5.7`                            |
| Sync workspace, hooks        | `make setup`                                            |
| All checks                   | `make check`                                            |
| Checks for one workspace     | `prek run --all-files pipeline/`                        |
| Update hook revisions        | `make update-hooks` (skips releases under 7 days old)   |
| Types in one workspace       | `uv run --frozen ty check` from `pipeline/`             |
| Add a dependency to a member | `uv add --package <dist-name> <dep>` from the workspace |
| All tests                    | `make test`                                             |
| Build the GDAL ECW image     | `make gdal-ecw-image` (about 3 min, 552 MB)             |
| Build a tile store           | `uv run satmesh build --bbox W S E N [--crs EPSG:27700] --store DIR` from `pipeline/` |
| Export a store               | `uv run satmesh export {3dtiles,gazebo,glb} --store DIR ...` from `pipeline/` |

## Checks

- prek is the whole CI apart from builds and tests. A new tool or file type in the repo gets its
  hook in `prek.toml` in the same change.
- Root `prek.toml` covers file hygiene, secrets (gitleaks), spelling (typos), ruff, notebook
  stripping (nbstripout), `pyproject.toml` validation, TOML (tombi), YAML (yamllint), Markdown
  (rumdl), Makefiles (mbake, checkmake), shell (shellcheck, shfmt) and Dockerfiles (hadolint).
- Each workspace's `prek.toml` adds `uv-lock`, `uv-audit` and ty, run inside that workspace.
- checkmake requires `setup` and `check` targets in every Makefile (`checkmake.ini`).
- ruff selects every rule; the ignores in `ruff.toml` each carry their reason. ty raises every rule
  to error and does not honor `# type: ignore`.
- Done means `make check` passes and the behavior has been exercised, not only tested.

## Notebooks

Committed notebooks are clean (nbstripout enforces it) and run from their inputs. Executed runs
worth keeping go to a gitignored `uncommitted/` directory beside the notebook, under a timestamped
name with the outputs they wrote.
