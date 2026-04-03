"""Test b3d_validate on a range of shapes — good, bad, and tricky."""

import sys
sys.path.insert(0, "/home/claude")

from build123d import *
from b3d_validate import validate_geometry, validate_printability, full_check

SEPARATOR = "=" * 60

# ----- Test 1: Clean box (should pass everything) -----
print(SEPARATOR)
print("TEST 1: Simple box (expect: all pass)")
print(SEPARATOR)
box = Box(20, 30, 10)
print(full_check(box))

# ----- Test 2: Box with hole (should pass, may have overhangs) -----
print(f"\n{SEPARATOR}")
print("TEST 2: Box with through-hole (expect: pass, some overhangs)")
print(SEPARATOR)
with BuildPart() as bp:
    Box(30, 30, 10)
    Cylinder(4, 10, mode=Mode.SUBTRACT)
part_with_hole = bp.part
print(full_check(part_with_hole))

# ----- Test 3: Thin-walled box (should flag wall thickness) -----
print(f"\n{SEPARATOR}")
print("TEST 3: Thin-walled shell (expect: thin wall warning)")
print(SEPARATOR)
with BuildPart() as bp:
    Box(20, 20, 10)
    with Locations((0, 0, 0.3)):  # offset inner box to leave 0.3mm floor
        Box(19, 19, 10, mode=Mode.SUBTRACT)
thin_part = bp.part
print(full_check(thin_part))

# ----- Test 4: Very small features -----
print(f"\n{SEPARATOR}")
print("TEST 4: Box with tiny chamfer (expect: small feature warnings)")
print(SEPARATOR)
with BuildPart() as bp:
    Box(20, 20, 10)
    chamfer(bp.edges(), length=0.1)
small_feat = bp.part
print(full_check(small_feat))

# ----- Test 5: Geometry-only (tier 1 vs tier 3 speed comparison) -----
print(f"\n{SEPARATOR}")
print("TEST 5: Complex shape — tier comparison")
print(SEPARATOR)
with BuildPart() as bp:
    Box(50, 50, 20)
    with Locations((10, 10, 0), (-10, -10, 0), (10, -10, 0)):
        Cylinder(5, 20, mode=Mode.SUBTRACT)
    fillet(bp.edges().filter_by(Axis.Z), radius=2)
complex_part = bp.part

for tier in (1, 2, 3):
    geo = validate_geometry(complex_part, tier=tier)
    print(f"  Tier {tier}: {'PASS' if geo.ok else 'FAIL'} ({geo.elapsed_ms:.0f}ms)")

print(f"\nFull check:")
print(full_check(complex_part))

# ----- Test 6: Individual report fields (programmatic access) -----
print(f"\n{SEPARATOR}")
print("TEST 6: Programmatic access to report fields")
print(SEPARATOR)
geo = validate_geometry(box)
prn = validate_printability(box, process="fdm")
print(f"  geo.ok={geo.ok} geo.volume={geo.volume:.1f} geo.n_faces={geo.n_faces}")
print(f"  prn.ok={prn.ok} prn.min_wall_mm={prn.min_wall_mm:.2f} prn.overhang_face_count={prn.overhang_face_count}")
print(f"  prn.mesh_checked={prn.mesh_checked} prn.mesh_watertight={prn.mesh_watertight}")
