"""
Defensive SVG rendering for build123d shapes.

Extracts and hardens the projection-to-SVG pipeline so that degenerate
geometry (zero-length arcs, collapsed edges) no longer crashes
``ExportSVG.add_shape()``.

Importing this module automatically patches ``svgpathtools.path.Arc``
to tolerate ``start == end`` (the root cause of assertion failures on
organic surfaces projected edge-on).
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# View definitions
# ---------------------------------------------------------------------------

VIEWS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float], str]] = {
    "front": ((0, -1, 0), (0, 0, 1), "Front"),
    "back": ((0, 1, 0), (0, 0, 1), "Back"),
    "right": ((1, 0, 0), (0, 0, 1), "Right"),
    "left": ((-1, 0, 0), (0, 0, 1), "Left"),
    "top": ((0, 0, 1), (0, 1, 0), "Top"),
    "bottom": ((0, 0, -1), (0, -1, 0), "Bottom"),
    "iso": ((-1, -1, 0.8), (0, 0, 1), "Iso"),
}

DEFAULT_VIEWS = ["front", "top", "right", "iso"]

# ---------------------------------------------------------------------------
# Monkey-patch: degenerate-arc safety
# ---------------------------------------------------------------------------

_PATCH_APPLIED = False


def patch_degenerate_arcs() -> None:
    """Replace ``svgpathtools.path.Arc`` with a subclass that survives
    ``start == end``.

    When a curved edge projects to a zero-length arc, the upstream
    ``Arc.__init__`` raises ``AssertionError`` (``assert start != end``).
    The patched version catches this and degrades the arc to a zero-length
    ``Line(start, start)``, which is geometrically harmless in SVG output.

    This function is idempotent — calling it more than once is safe.
    """
    global _PATCH_APPLIED  # noqa: PLW0603
    if _PATCH_APPLIED:
        return

    import svgpathtools.path as _mod

    _OrigArc = _mod.Arc

    # Guard against double-patching if someone reloads the module.
    if getattr(_OrigArc, "_b3d_patched", False):
        _PATCH_APPLIED = True
        return

    class SafeArc(_OrigArc):  # type: ignore[misc]
        """Arc subclass that degrades to a zero-length Line on bad geometry."""

        _b3d_patched = True

        def __init__(self, *args, **kwargs):
            try:
                super().__init__(*args, **kwargs)
            except AssertionError:
                # Degrade: become a zero-length Line(start, start).
                start = args[0] if args else kwargs.get("start", 0j)
                from svgpathtools import Line

                self._degenerate_line = Line(start, start)
                # Copy essential attributes so callers don't crash.
                self.start = start
                self.end = start

    _mod.Arc = SafeArc  # ty: ignore[invalid-assignment]
    # Also patch the module-level import that most callers use.
    import svgpathtools

    svgpathtools.Arc = SafeArc  # ty: ignore[invalid-assignment]

    _PATCH_APPLIED = True


# Apply the patch at import time.
patch_degenerate_arcs()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise(
    v: tuple[float, float, float], scale: float = 100
) -> tuple[float, float, float]:
    """Scale a direction vector to a fixed magnitude."""
    mag = math.sqrt(sum(c * c for c in v))
    if mag < 1e-9:
        return (0.0, 0.0, scale)
    f = 1.0 / mag * scale
    return (v[0] * f, v[1] * f, v[2] * f)


# ---------------------------------------------------------------------------
# safe_add_shape
# ---------------------------------------------------------------------------


def safe_add_shape(svg, edges, layer_name: str) -> int:
    """Add *edges* to *svg* on *layer_name*, returning a failure count.

    Returns 0 on success.  On any exception the error is logged as a
    warning and 1 is returned (representing the batch of edges that
    could not be added).
    """
    try:
        svg.add_shape(edges, layer=layer_name)
    except Exception:
        n = len(edges) if edges else 0
        log.warning(
            "safe_add_shape: failed to add %d edge(s) to layer '%s'",
            n,
            layer_name,
            exc_info=True,
        )
        return n
    return 0


# ---------------------------------------------------------------------------
# render_svg
# ---------------------------------------------------------------------------


def render_svg(
    part,
    view_name: str,
    output_path: Path | str,
    *,
    line_weight_visible: float = 0.5,
    line_weight_hidden: float = 0.2,
) -> Path:
    """Project *part* from *view_name* and write an SVG file.

    Parameters
    ----------
    part:
        A build123d ``Shape`` (or ``Compound``/``Part``).
    view_name:
        Key into :data:`VIEWS`.
    output_path:
        Destination SVG file.
    line_weight_visible:
        Stroke width for visible edges.
    line_weight_hidden:
        Stroke width for hidden edges.

    Returns
    -------
    Path
        The written SVG file path.
    """
    from build123d import Compound, ExportSVG, LineType
    from build123d.exporters import RGB

    output_path = Path(output_path)
    origin_dir, up, _label = VIEWS[view_name]
    origin = _normalise(origin_dir, scale=500)

    visible, hidden = part.project_to_viewport(origin, viewport_up=up)

    all_edges = visible + hidden
    if not all_edges:
        msg = f"No edges produced for view '{view_name}' — model may be empty"
        raise RuntimeError(msg)

    bb = Compound(children=all_edges).bounding_box()
    max_dim = max(bb.size.X, bb.size.Y)
    if max_dim < 1e-9:
        max_dim = 1.0

    svg = ExportSVG(scale=90 / max_dim, precision=2)
    svg.add_layer("Visible", line_weight=line_weight_visible)
    svg.add_layer(
        "Hidden",
        line_color=RGB(180, 180, 180),
        line_type=LineType.ISO_DOT,
        line_weight=line_weight_hidden,
    )

    warnings = 0
    warnings += safe_add_shape(svg, visible, "Visible")
    warnings += safe_add_shape(svg, hidden, "Hidden")

    if warnings:
        log.warning(
            "render_svg(%s): %d edge(s) could not be added", view_name, warnings
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    svg.write(str(output_path))
    return output_path


# ---------------------------------------------------------------------------
# render_views
# ---------------------------------------------------------------------------


def render_views(
    part,
    views: list[str] | None = None,
    output_dir: Path | str = Path(),
    prefix: str = "view",
    *,
    line_weight_visible: float = 0.5,
    line_weight_hidden: float = 0.2,
) -> dict[str, Path]:
    """Render multiple SVG views of *part*.

    Parameters
    ----------
    part:
        A build123d ``Shape``.
    views:
        List of view names (keys of :data:`VIEWS`).
        Defaults to :data:`DEFAULT_VIEWS`.
    output_dir:
        Directory for the SVG files.
    prefix:
        Filename prefix (``{prefix}_{view}.svg``).
    line_weight_visible / line_weight_hidden:
        Passed through to :func:`render_svg`.

    Returns
    -------
    dict[str, Path]
        Mapping of view name to written SVG path.
    """
    if views is None:
        views = list(DEFAULT_VIEWS)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, Path] = {}
    total_warnings = 0

    for view_name in views:
        svg_path = output_dir / f"{prefix}_{view_name}.svg"
        try:
            path = render_svg(
                part,
                view_name,
                svg_path,
                line_weight_visible=line_weight_visible,
                line_weight_hidden=line_weight_hidden,
            )
            results[view_name] = path
        except Exception:
            log.warning("render_views: view '%s' failed", view_name, exc_info=True)
            total_warnings += 1

    if total_warnings:
        log.warning("render_views: %d/%d views had issues", total_warnings, len(views))

    return results
