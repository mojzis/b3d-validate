"""
b3d_validate — lightweight validation toolkit for build123d shapes.

Designed for Claude Code's feedback loop: fast checks, compact reports,
actionable error messages with locations and fix suggestions.

Usage in a model script:

    from build123d import *
    from b3d_validate import validate_geometry, validate_printability, full_check

    part = Box(20, 20, 10) - Cylinder(3, 20)

    # Individual checks
    geo = validate_geometry(part)
    print(geo)

    prn = validate_printability(part, process="fdm")
    print(prn)

    # Or everything at once
    print(full_check(part))

Dependencies:
    Required:  build123d (includes OCP/OCCT bindings)
    Optional:  trimesh (for mesh-level printability checks)
"""

from b3d_validate.geometry import validate_geometry, GeometryReport
from b3d_validate.printability import validate_printability, PrintabilityReport


def full_check(
    shape,
    process: str = "fdm",
    tier: int = 3,
    **printability_kwargs,
) -> str:
    """
    Run geometry + printability validation, return a single compact report.

    This is the one-liner for the feedback loop:
        print(full_check(my_part))

    Returns a single string suitable for LLM consumption.
    """
    geo = validate_geometry(shape, tier=tier)
    prn = validate_printability(shape, process=process, **printability_kwargs)

    parts = [str(geo), str(prn)]

    # Overall verdict
    if geo.ok and prn.ok:
        parts.append("VERDICT: READY TO PRINT")
    elif geo.ok and not prn.ok:
        parts.append("VERDICT: GEOMETRY OK, FIX PRINTABILITY ISSUES")
    elif not geo.ok and prn.ok:
        parts.append("VERDICT: FIX GEOMETRY ERRORS FIRST")
    else:
        parts.append("VERDICT: FIX GEOMETRY AND PRINTABILITY ISSUES")

    return "\n\n".join(parts)


__all__ = [
    "validate_geometry",
    "validate_printability",
    "full_check",
    "GeometryReport",
    "PrintabilityReport",
]
