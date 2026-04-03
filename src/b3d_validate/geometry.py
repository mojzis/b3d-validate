"""
Geometry validation for build123d shapes — three tiers.

Tier 1 (fast):  Null/empty, is_valid, volume/area/bbox sanity
Tier 2 (structural): Topology counts, solid/shell integrity
Tier 3 (deep):  BRepAlgoAPI_Check (self-intersection + small edges),
                watertight test, per-sub-shape defect enumeration

Returns a compact, token-efficient report string designed for LLM consumption.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# OCCT imports (always available alongside build123d)
# ---------------------------------------------------------------------------
from build123d import Compound, ShapeList
from OCP.BRepAlgoAPI import BRepAlgoAPI_Check
from OCP.BRepCheck import BRepCheck_Analyzer, BRepCheck_Status
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.Precision import Precision
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_OUT, TopAbs_VERTEX, TopAbs_WIRE
from OCP.TopExp import TopExp_Explorer

# Map BRepCheck_Status enum values to short human-readable names.
# We only list the ones that matter most — the enum has 37+ members.
_STATUS_NAMES = {
    BRepCheck_Status.BRepCheck_InvalidPointOnCurve: "bad_pt_on_curve",
    BRepCheck_Status.BRepCheck_InvalidPointOnCurveOnSurface: "bad_pt_curve_surf",
    BRepCheck_Status.BRepCheck_InvalidPointOnSurface: "bad_pt_on_surface",
    BRepCheck_Status.BRepCheck_SelfIntersectingWire: "self_intersecting_wire",
    BRepCheck_Status.BRepCheck_NoSurface: "no_surface",
    BRepCheck_Status.BRepCheck_BadOrientation: "bad_orientation",
    BRepCheck_Status.BRepCheck_NotClosed: "not_closed",
    BRepCheck_Status.BRepCheck_NotConnected: "not_connected",
    BRepCheck_Status.BRepCheck_FreeEdge: "free_edge",
    BRepCheck_Status.BRepCheck_EmptyWire: "empty_wire",
    BRepCheck_Status.BRepCheck_EmptyShell: "empty_shell",
    BRepCheck_Status.BRepCheck_UnorientableShape: "unorientable",
    BRepCheck_Status.BRepCheck_EnclosedRegion: "enclosed_region",
}

_TYPE_NAMES = {
    TopAbs_VERTEX: "vertex",
    TopAbs_EDGE: "edge",
    TopAbs_WIRE: "wire",
    TopAbs_FACE: "face",
}


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------
@dataclass
class GeometryReport:
    """Structured geometry validation results."""

    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Tier 1 stats
    volume: float = 0.0
    area: float = 0.0
    bbox: tuple[float, float, float] = (0.0, 0.0, 0.0)
    is_valid: bool = False

    # Tier 2 stats
    n_solids: int = 0
    n_shells: int = 0
    n_faces: int = 0
    n_edges: int = 0
    n_vertices: int = 0

    # Tier 3 stats
    bop_valid: bool = False
    watertight: bool = False
    defects: list[str] = field(default_factory=list)

    elapsed_ms: float = 0.0

    def _err(self, msg: str):
        self.errors.append(msg)
        self.ok = False

    def _warn(self, msg: str):
        self.warnings.append(msg)

    def __str__(self) -> str:
        """Compact, token-efficient report for LLM consumption."""
        lines: list[str] = []
        status = "PASS" if self.ok else "FAIL"
        lines.append(f"GEOMETRY: {status} ({self.elapsed_ms:.0f}ms)")

        # Stats line
        bx, by, bz = self.bbox
        lines.append(
            f"  vol={self.volume:.2f}mm³ area={self.area:.2f}mm² "
            f"bbox={bx:.1f}×{by:.1f}×{bz:.1f}mm"
        )

        # Topology line
        lines.append(
            f"  solids={self.n_solids} shells={self.n_shells} "
            f"faces={self.n_faces} edges={self.n_edges} verts={self.n_vertices}"
        )

        # Tier 3 summary
        checks = []
        checks.append(f"brep:{'OK' if self.is_valid else 'FAIL'}")
        checks.append(f"bop:{'OK' if self.bop_valid else 'FAIL'}")
        checks.append(f"watertight:{'OK' if self.watertight else 'FAIL'}")
        lines.append(f"  {' '.join(checks)}")

        # Errors
        for e in self.errors:
            lines.append(f"  [ERR] {e}")

        # Warnings
        for w in self.warnings:
            lines.append(f"  [WARN] {w}")

        # Defect details (tier 3) — cap to avoid token bloat
        if self.defects:
            shown = self.defects[:8]
            lines.append(f"  defects ({len(self.defects)} total):")
            for d in shown:
                lines.append(f"    - {d}")
            if len(self.defects) > 8:
                lines.append(f"    ... +{len(self.defects) - 8} more")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validation tiers
# ---------------------------------------------------------------------------


def _tier1(shape, report: GeometryReport):
    """Null, is_valid, volume, area, bounding box."""
    if shape is None:
        report._err("shape is None — construction likely failed")
        return False  # abort further tiers

    if shape.is_null:
        report._err("shape is null (empty OCCT TopoDS_Shape)")
        return False

    report.is_valid = shape.is_valid
    if not report.is_valid:
        report._err("BRepCheck_Analyzer: invalid shape")

    report.volume = shape.volume
    report.area = shape.area

    if report.volume <= 0:
        report._err(f"non-positive volume ({report.volume:.6f})")
    elif report.volume < 1e-6:
        report._warn(f"near-zero volume ({report.volume:.6f}) — degenerate?")

    if report.area <= 0:
        report._err(f"non-positive surface area ({report.area:.6f})")

    bb = shape.bounding_box()
    dims = (bb.size.X, bb.size.Y, bb.size.Z)
    report.bbox = dims
    for axis, val in zip("XYZ", dims):
        if val < 1e-6:
            report._err(f"bbox collapsed on {axis} axis ({val:.6f}mm)")

    return True  # continue to next tier


def _tier2(shape, report: GeometryReport):
    """Topology counting — structural integrity."""
    report.n_solids = len(shape.solids())
    report.n_shells = len(shape.shells())
    report.n_faces = len(shape.faces())
    report.n_edges = len(shape.edges())
    report.n_vertices = len(shape.vertices())

    if report.n_solids == 0:
        report._err("no solids — shape may be a shell/wire, not a printable body")
    elif report.n_solids > 1:
        report._warn(
            f"{report.n_solids} separate solids — boolean may have fragmented; "
            "use Compound or fix the operation"
        )

    if report.n_solids == 1 and report.n_shells != 1:
        report._warn(f"single solid but {report.n_shells} shells — expected 1")

    if report.n_faces < 4:
        report._warn(f"only {report.n_faces} faces — minimum for a closed solid is 4")


def _tier3(shape, report: GeometryReport):
    """Deep OCCT checks: BOP validity, watertight, per-sub-shape defects."""

    # --- BRepAlgoAPI_Check (self-intersection + small edges) ---
    try:
        checker = BRepAlgoAPI_Check(shape.wrapped, True, True)
        checker.Perform()
        report.bop_valid = checker.IsValid()
        if not report.bop_valid:
            report._err(
                "BRepAlgoAPI_Check failed — possible self-intersection or "
                "degenerate edges; split self-intersecting features into "
                "separate bodies or increase fillet radii"
            )
    except Exception as exc:
        report._warn(f"BRepAlgoAPI_Check threw: {exc}")
        report.bop_valid = False

    # --- Watertight check via SolidClassifier ---
    try:
        sc = BRepClass3d_SolidClassifier(shape.wrapped)
        sc.PerformInfinitePoint(Precision.Confusion_s())
        report.watertight = sc.State() == TopAbs_OUT
        if not report.watertight:
            report._err(
                "not watertight — infinity classifies as inside; "
                "shell has gaps or inverted faces"
            )
    except Exception as exc:
        report._warn(f"watertight check threw: {exc}")
        report.watertight = False

    # --- Per-sub-shape defect enumeration ---
    try:
        analyzer = BRepCheck_Analyzer(shape.wrapped, True)
        if not analyzer.IsValid():
            for shape_type, type_name in _TYPE_NAMES.items():
                explorer = TopExp_Explorer(shape.wrapped, shape_type)
                while explorer.More():
                    sub = explorer.Current()
                    result = analyzer.Result(sub)
                    if not result.IsNull():
                        status_iter = result.Status()
                        for status in status_iter:
                            if status != BRepCheck_Status.BRepCheck_NoError:
                                name = _STATUS_NAMES.get(status, str(status))
                                report.defects.append(f"{type_name}: {name}")
                    explorer.Next()
    except Exception as exc:
        report._warn(f"defect enumeration threw: {exc}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_geometry(shape, tier: int = 3) -> GeometryReport:
    """
    Validate a build123d Shape/Part/Solid.

    Args:
        shape:  Any build123d shape (Part, Solid, Compound, etc.)
        tier:   Validation depth — 1 (fast), 2 (structural), 3 (deep).
                Higher tiers include all lower tiers.

    Returns:
        GeometryReport with .ok bool, compact str() for LLM output,
        and structured fields for programmatic use.

    Usage in a model script:
        from b3d_validate import validate_geometry
        report = validate_geometry(my_part)
        print(report)          # compact LLM-friendly output
        assert report.ok       # or handle report.errors
    """
    t0 = time.perf_counter()
    report = GeometryReport()

    if isinstance(shape, ShapeList):
        shape = Compound(children=shape.copy())  # ty: ignore[invalid-argument-type]

    if not _tier1(shape, report):
        report.elapsed_ms = (time.perf_counter() - t0) * 1000
        return report

    if tier >= 2:
        _tier2(shape, report)

    if tier >= 3:
        _tier3(shape, report)

    report.elapsed_ms = (time.perf_counter() - t0) * 1000
    return report
