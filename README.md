# b3d-validate

Lightweight validation toolkit for [build123d](https://github.com/gumyr/build123d) CAD shapes. Runs geometry and 3D-printability checks against OCCT BRep data, returning compact reports designed for LLM feedback loops.

## Install

```bash
uv add b3d-validate
```

Requires `build123d` (and its bundled OCP/OCCT bindings). Optional: `trimesh` + `numpy` for mesh-level checks.

## Usage

```python
from build123d import *
from b3d_validate import validate_geometry, validate_printability, full_check

part = Box(20, 20, 10) - Cylinder(3, 20)

# Individual checks
print(validate_geometry(part))
print(validate_printability(part, process="fdm"))

# Or everything at once
print(full_check(part))
```

### Example output

```
GEOMETRY: PASS (12ms)
  vol=11086.73mm3 area=2953.10mm2 bbox=20.0x20.0x10.0mm
  solids=1 shells=1 faces=8 edges=14 verts=8
  brep:OK bop:OK watertight:OK

PRINTABILITY (FDM): PASS (0 issues, 45ms)
  overhangs: none
  min_wall: OK (all above threshold)
  mesh: watertight:OK winding:OK

VERDICT: READY TO PRINT
```

## Checks

### Geometry (three tiers)

| Tier | Speed | Checks |
|------|-------|--------|
| 1 | Fast | Null/empty, `is_valid`, volume/area/bbox sanity |
| 2 | Medium | Topology counts (solids, shells, faces, edges), structural integrity |
| 3 | Deep | BRepAlgoAPI_Check (self-intersection, small edges), watertight test, per-sub-shape defect enumeration |

```python
report = validate_geometry(part, tier=2)  # skip deep checks
```

### Printability

- **Overhang detection** -- BRep face normals vs build direction
- **Wall thickness** -- min distance between non-adjacent face pairs (BRepExtrema)
- **Small features** -- short edges and tiny faces below print threshold
- **Mesh checks** (optional, requires trimesh) -- watertight, winding consistency, degenerate triangles

```python
report = validate_printability(part, process="sla", min_wall_mm=0.5)
```

Supports `"fdm"` and `"sla"` presets with sensible defaults.

## Programmatic access

Reports are dataclasses with structured fields:

```python
geo = validate_geometry(part)
geo.ok          # bool
geo.volume      # float (mm3)
geo.n_faces     # int
geo.errors      # list[str]
geo.warnings    # list[str]

prn = validate_printability(part)
prn.ok                  # bool
prn.min_wall_mm         # float
prn.overhang_face_count # int
prn.worst_overhangs     # list[OverhangInfo]
prn.thin_walls          # list[ThinWallInfo]
```

## Development

```bash
uv sync
uv run poe check    # lint + typecheck + security + tests
uv run poe fix      # auto-format
uv run poe test     # tests only
```
