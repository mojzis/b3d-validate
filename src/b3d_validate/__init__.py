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

from importlib.metadata import version
from typing import Literal

from b3d_validate.geometry import GeometryReport, validate_geometry
from b3d_validate.printability import PrintabilityReport, validate_printability
from b3d_validate.rendering import render_svg, render_views

__version__ = version("b3d-validate")


def full_check(
    shape,
    process: Literal["fdm", "sla"] = "fdm",
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
    "GeometryReport",
    "PrintabilityReport",
    "full_check",
    "render_svg",
    "render_views",
    "validate_geometry",
    "validate_printability",
]
