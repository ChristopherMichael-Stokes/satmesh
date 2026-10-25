# satmesh

Textured 3D terrain meshes from Esri World Imagery tiles and DEMs, enhanced with classical processing
and ML. Research use.

- `pipeline/`: tile and DEM fetching, meshing, texture draping and export, without PyTorch.

## Setup

Needs [uv](https://docs.astral.sh/uv/) and [prek](https://prek.j178.dev/).

```sh
uv tool install prek@0.5.7
make setup
```

## Checks

```sh
make check
```
