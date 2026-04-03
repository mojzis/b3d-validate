"""
Printability validation for build123d shapes.

Checks geometry against 3D printing constraints (FDM or SLA):
  - Overhang detection (BRep face normals)
  - Wall thickness estimation (BRep face-pair distance)
  - Small feature detection (thin edges, tiny faces)
  - Mesh-level checks via trimesh (optional, if installed)
    - manifold / watertight after tessellation
    - degenerate triangles
    - winding consistency

All BRep checks use only OCCT (bundled with build123d).
Trimesh checks are skipped gracefully if trimesh is not installed.

Returns a compact, token-efficient report with locations so Claude can fix issues.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Literal

from OCP.BRep import BRep_Tool
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS

# ---------------------------------------------------------------------------
# Default thresholds
# ---------------------------------------------------------------------------
FDM_DEFAULTS = {
    "min_wall_mm": 0.8,
    "overhang_deg": 45.0,
    "min_feature_mm": 0.4,
    "min_hole_mm": 1.0,
}

SLA_DEFAULTS = {
    "min_wall_mm": 0.6,
    "overhang_deg": 30.0,
    "min_feature_mm": 0.3,
    "min_hole_mm": 0.5,
}


def _vec3_str(v) -> str:
    """Format a Vector or tuple as compact (x,y,z) string."""
    try:
        return f"({v.X:.1f},{v.Y:.1f},{v.Z:.1f})"
    except AttributeError:
        return f"({v[0]:.1f},{v[1]:.1f},{v[2]:.1f})"


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
@dataclass
class OverhangInfo:
    face_idx: int
    angle_deg: float
    area: float
    center: str  # compact "(x,y,z)"


@dataclass
class ThinWallInfo:
    thickness_mm: float
    location: str  # compact "(x,y,z)"
    face_a_idx: int
    face_b_idx: int


@dataclass
class PrintabilityReport:
    ok: bool = True
    process: str = "fdm"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Overhang summary
    overhang_face_count: int = 0
    overhang_area_pct: float = 0.0
    worst_overhangs: list[OverhangInfo] = field(default_factory=list)

    # Wall thickness
    min_wall_mm: float = float("inf")
    thin_walls: list[ThinWallInfo] = field(default_factory=list)

    # Small features
    small_edges: int = 0
    small_faces: int = 0

    # Mesh checks (trimesh, optional)
    mesh_checked: bool = False
    mesh_watertight: bool | None = None
    mesh_winding_ok: bool | None = None
    mesh_degenerate_faces: int = 0

    elapsed_ms: float = 0.0

    def _err(self, msg: str):
        self.errors.append(msg)
        self.ok = False

    def _warn(self, msg: str):
        self.warnings.append(msg)

    def __str__(self) -> str:
        lines: list[str] = []
        status = "PASS" if self.ok else "FAIL"
        n_issues = len(self.errors) + len(self.warnings)
        lines.append(
            f"PRINTABILITY ({self.process.upper()}): {status} "
            f"({n_issues} issues, {self.elapsed_ms:.0f}ms)"
        )

        # Overhangs
        if self.overhang_face_count > 0:
            lines.append(
                f"  overhangs: {self.overhang_face_count} faces "
                f"({self.overhang_area_pct:.1f}% of surface area)"
            )
            for oh in self.worst_overhangs[:5]:
                lines.append(
                    f"    face#{oh.face_idx} {oh.angle_deg:.0f}° "
                    f"area={oh.area:.1f}mm² at {oh.center}"
                )
        else:
            lines.append("  overhangs: none")

        # Wall thickness
        if self.min_wall_mm < float("inf"):
            lines.append(f"  min_wall: {self.min_wall_mm:.2f}mm")
            for tw in self.thin_walls[:5]:
                lines.append(
                    f"    {tw.thickness_mm:.2f}mm between "
                    f"face#{tw.face_a_idx}↔face#{tw.face_b_idx} "
                    f"at {tw.location}"
                )
            if len(self.thin_walls) > 5:
                lines.append(f"    ... +{len(self.thin_walls) - 5} more thin regions")
        else:
            lines.append("  min_wall: OK (all above threshold)")

        # Small features
        if self.small_edges or self.small_faces:
            lines.append(
                f"  small_features: {self.small_edges} short edges, "
                f"{self.small_faces} tiny faces"
            )

        # Mesh checks
        if self.mesh_checked:
            m_parts = []
            m_parts.append(f"watertight:{'OK' if self.mesh_watertight else 'FAIL'}")
            m_parts.append(f"winding:{'OK' if self.mesh_winding_ok else 'FAIL'}")
            if self.mesh_degenerate_faces > 0:
                m_parts.append(f"degenerate_tris:{self.mesh_degenerate_faces}")
            lines.append(f"  mesh: {' '.join(m_parts)}")
        else:
            lines.append("  mesh: skipped (trimesh not available)")

        # Errors and warnings
        for e in self.errors:
            lines.append(f"  [ERR] {e}")
        for w in self.warnings:
            lines.append(f"  [WARN] {w}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Overhang detection (BRep level)
# ---------------------------------------------------------------------------


def _check_overhangs(
    shape, report: PrintabilityReport, threshold_deg: float, build_dir=(0, 0, 1)
):
    """Flag faces whose outward normal exceeds the overhang threshold.
    Skips faces resting on the build plate (lowest Z)."""
    from build123d import Vector

    build = Vector(*build_dir).normalized()
    threshold_rad = math.radians(threshold_deg)
    faces = shape.faces()
    total_area = shape.area if shape.area > 0 else 1.0
    overhang_area = 0.0
    overhangs: list[OverhangInfo] = []

    # Find model's lowest Z to identify build-plate faces
    bb = shape.bounding_box()
    z_min = bb.min.Z
    plate_tol = 0.1  # mm — faces within this of z_min are "on the plate"

    for idx, face in enumerate(faces):
        try:
            normal = face.normal_at().normalized()
        except Exception:  # nosec B112
            continue

        # Angle between outward normal and build direction
        dot = max(-1.0, min(1.0, normal.dot(build)))
        angle_from_up = math.acos(dot)

        # Overhang = normal points significantly downward
        if angle_from_up > math.pi / 2 + threshold_rad:
            # Skip if this face is on the build plate
            face_bb = face.bounding_box()
            if z_min + plate_tol > face_bb.min.Z and abs(normal.Z + 1) < 0.1:
                continue  # flat bottom face on the plate

            overhang_deg = math.degrees(angle_from_up) - 90
            face_area = face.area
            overhang_area += face_area
            overhangs.append(
                OverhangInfo(
                    face_idx=idx,
                    angle_deg=overhang_deg,
                    area=face_area,
                    center=_vec3_str(face.center()),
                )
            )

    report.overhang_face_count = len(overhangs)
    report.overhang_area_pct = (overhang_area / total_area) * 100

    # Sort by angle (worst first), keep top entries
    overhangs.sort(key=lambda o: o.angle_deg, reverse=True)
    report.worst_overhangs = overhangs[:10]

    if report.overhang_area_pct > 30:
        report._warn(
            f"{report.overhang_area_pct:.0f}% overhang area — consider "
            "reorienting the part or adding support-friendly features"
        )


# ---------------------------------------------------------------------------
# Wall thickness (BRep level — face-pair distance)
# ---------------------------------------------------------------------------


def _check_wall_thickness(
    shape, report: PrintabilityReport, min_wall_mm: float, max_face_pairs: int = 500
):
    """
    Estimate wall thickness via min distance between non-adjacent face pairs.

    Uses bounding-box pre-filter + BRepExtrema for accuracy.
    Caps the number of pairs checked for speed on complex models.
    """
    faces = list(shape.faces())
    n = len(faces)
    if n < 2:
        return

    # Build adjacency set via shared edges
    edge_to_faces: dict[int, list[int]] = {}
    for i, face in enumerate(faces):
        for edge in face.edges():
            eid = id(edge.wrapped)
            edge_to_faces.setdefault(eid, []).append(i)

    adjacent: set[tuple[int, int]] = set()
    for face_list in edge_to_faces.values():
        for a in face_list:
            for b in face_list:
                if a < b:
                    adjacent.add((a, b))

    # Pre-compute bounding boxes for fast rejection
    bboxes = []
    for face in faces:
        bb = face.bounding_box()
        bboxes.append(bb)

    # Check non-adjacent pairs, with bbox pre-filter
    pairs_checked = 0
    for i in range(n):
        for j in range(i + 1, n):
            if (i, j) in adjacent:
                continue
            if pairs_checked >= max_face_pairs:
                break

            # Bbox distance heuristic: skip if far apart
            bb_i, bb_j = bboxes[i], bboxes[j]
            # Quick axis-aligned gap check
            gap_x = max(0, bb_i.min.X - bb_j.max.X, bb_j.min.X - bb_i.max.X)
            gap_y = max(0, bb_i.min.Y - bb_j.max.Y, bb_j.min.Y - bb_i.max.Y)
            gap_z = max(0, bb_i.min.Z - bb_j.max.Z, bb_j.min.Z - bb_i.max.Z)
            if gap_x + gap_y + gap_z > min_wall_mm * 3:
                continue

            try:
                dist_calc = BRepExtrema_DistShapeShape(
                    faces[i].wrapped, faces[j].wrapped
                )
                if dist_calc.IsDone() and dist_calc.NbSolution() > 0:
                    d = dist_calc.Value()
                    if 0 < d < report.min_wall_mm:
                        report.min_wall_mm = d
                    if 0 < d < min_wall_mm:
                        # Get the location of the closest point
                        pt = dist_calc.PointOnShape1(1)
                        loc_str = f"({pt.X():.1f},{pt.Y():.1f},{pt.Z():.1f})"
                        report.thin_walls.append(
                            ThinWallInfo(
                                thickness_mm=d,
                                face_a_idx=i,
                                face_b_idx=j,
                                location=loc_str,
                            )
                        )
                pairs_checked += 1
            except Exception:
                pairs_checked += 1
                continue

    # Sort thinnest first
    report.thin_walls.sort(key=lambda t: t.thickness_mm)

    if report.thin_walls:
        thinnest = report.thin_walls[0]
        report._warn(
            f"min wall {thinnest.thickness_mm:.2f}mm < {min_wall_mm}mm "
            f"at {thinnest.location} — thicken geometry or merge faces"
        )


# ---------------------------------------------------------------------------
# Small feature detection (BRep level)
# ---------------------------------------------------------------------------


def _check_small_features(shape, report: PrintabilityReport, min_feature_mm: float):
    """Flag edges shorter than threshold and faces smaller than threshold²."""
    min_area = min_feature_mm**2

    for edge in shape.edges():
        try:
            if edge.length < min_feature_mm:
                report.small_edges += 1
        except Exception:  # nosec B112
            continue

    for face in shape.faces():
        try:
            if face.area < min_area:
                report.small_faces += 1
        except Exception:  # nosec B112
            continue

    if report.small_edges > 0:
        report._warn(
            f"{report.small_edges} edges shorter than {min_feature_mm}mm — "
            "may vanish in print or cause slicer issues"
        )
    if report.small_faces > 0:
        report._warn(
            f"{report.small_faces} faces smaller than {min_area:.2f}mm² — "
            "may be unprintable detail"
        )


# ---------------------------------------------------------------------------
# Mesh-level checks (requires trimesh — optional)
# ---------------------------------------------------------------------------


def _check_mesh(shape, report: PrintabilityReport, tolerance: float = 0.01):
    """
    Tessellate in-memory and run trimesh checks.
    Gracefully skips if trimesh is not installed.
    """
    try:
        import numpy as np
        import trimesh
    except ImportError:
        report.mesh_checked = False
        return

    # Tessellate via OCCT in-place
    BRepMesh_IncrementalMesh(shape.wrapped, tolerance, False, 0.1, True)

    # Extract triangles from all faces
    all_verts = []
    all_tris = []
    offset = 0

    explorer = TopExp_Explorer(shape.wrapped, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        is_reversed = face.Orientation() == TopAbs_REVERSED
        loc = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, loc)
        if triangulation is not None:
            n_nodes = triangulation.NbNodes()
            n_tris = triangulation.NbTriangles()
            trsf = loc.Transformation()

            for i in range(1, n_nodes + 1):
                pt = triangulation.Node(i)
                pt.Transform(trsf)
                all_verts.append([pt.X(), pt.Y(), pt.Z()])

            for i in range(1, n_tris + 1):
                tri = triangulation.Triangle(i)
                n1, n2, n3 = tri.Get()
                if is_reversed:
                    n1, n2 = n2, n1  # flip winding for outward normals
                all_tris.append([n1 - 1 + offset, n2 - 1 + offset, n3 - 1 + offset])

            offset += n_nodes
        explorer.Next()

    if not all_verts or not all_tris:
        report._warn("tessellation produced no triangles")
        report.mesh_checked = False
        return

    verts = np.array(all_verts, dtype=np.float64)
    faces_arr = np.array(all_tris, dtype=np.int64)

    mesh = trimesh.Trimesh(vertices=verts, faces=faces_arr, process=True)

    report.mesh_checked = True
    report.mesh_watertight = bool(mesh.is_watertight)
    report.mesh_winding_ok = bool(mesh.is_winding_consistent)

    # Degenerate triangles (near-zero area)
    areas = mesh.area_faces
    report.mesh_degenerate_faces = int(np.sum(areas < 1e-10))

    if not report.mesh_watertight:
        report._err(
            "mesh not watertight after tessellation — "
            "check for gaps or self-intersections in the BRep"
        )
    if not report.mesh_winding_ok:
        report._warn("inconsistent face winding — normals may be flipped")
    if report.mesh_degenerate_faces > 0:
        report._warn(
            f"{report.mesh_degenerate_faces} degenerate triangles in mesh — "
            "reduce tessellation tolerance or simplify tangent surfaces"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_printability(
    shape,
    process: Literal["fdm", "sla"] = "fdm",
    *,
    min_wall_mm: float | None = None,
    overhang_deg: float | None = None,
    min_feature_mm: float | None = None,
    build_dir: tuple[float, float, float] = (0, 0, 1),
    check_mesh: bool = True,
    mesh_tolerance: float = 0.01,
    max_face_pairs: int = 500,
) -> PrintabilityReport:
    """
    Validate a build123d shape for 3D printability.

    Args:
        shape:          build123d Shape/Part/Solid
        process:        "fdm" or "sla" — sets default thresholds
        min_wall_mm:    Override minimum wall thickness (mm)
        overhang_deg:   Override max overhang angle before warning (degrees)
        min_feature_mm: Override minimum printable feature size (mm)
        build_dir:      Print orientation as (x, y, z) vector
        check_mesh:     Run trimesh mesh-level checks (requires trimesh)
        mesh_tolerance: STL tessellation tolerance (mm)
        max_face_pairs: Cap on face pairs for wall thickness (speed vs coverage)

    Returns:
        PrintabilityReport with .ok bool and compact str() for LLM output.

    Usage:
        from b3d_validate import validate_printability
        report = validate_printability(my_part, process="fdm")
        print(report)
    """
    t0 = time.perf_counter()

    defaults = FDM_DEFAULTS if process == "fdm" else SLA_DEFAULTS
    _min_wall = min_wall_mm if min_wall_mm is not None else defaults["min_wall_mm"]
    _overhang = overhang_deg if overhang_deg is not None else defaults["overhang_deg"]
    _min_feat = (
        min_feature_mm if min_feature_mm is not None else defaults["min_feature_mm"]
    )

    report = PrintabilityReport(process=process)

    # Basic sanity
    if shape is None or shape.is_null:
        report._err("shape is None or null — cannot validate")
        report.elapsed_ms = (time.perf_counter() - t0) * 1000
        return report

    if shape.volume <= 0:
        report._err(f"non-positive volume ({shape.volume:.6f}) — not a solid")
        report.elapsed_ms = (time.perf_counter() - t0) * 1000
        return report

    # BRep-level checks
    _check_overhangs(shape, report, _overhang, build_dir)
    _check_wall_thickness(shape, report, _min_wall, max_face_pairs)
    _check_small_features(shape, report, _min_feat)

    # Mesh-level checks (optional)
    if check_mesh:
        _check_mesh(shape, report, mesh_tolerance)

    report.elapsed_ms = (time.perf_counter() - t0) * 1000
    return report
