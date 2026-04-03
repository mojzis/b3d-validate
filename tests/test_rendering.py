"""Tests for b3d_validate.rendering — SVG export safety layer."""

from __future__ import annotations

import svgpathtools

import b3d_validate.rendering  # noqa: F401  # activates the arc patch
from b3d_validate.rendering import (
    patch_degenerate_arcs,
    render_svg,
    render_views,
    safe_add_shape,
)


class TestDegenerateArcPatch:
    def test_degenerate_arc_patched(self):
        """A zero-length arc (start == end) must not raise."""
        arc = svgpathtools.Arc(
            start=0 + 0j,
            radius=1 + 1j,
            rotation=0,
            large_arc=False,
            sweep=True,
            end=0 + 0j,
        )
        assert arc.start == arc.end

    def test_patch_is_idempotent(self):
        """Calling patch_degenerate_arcs() twice must not break anything."""
        patch_degenerate_arcs()
        patch_degenerate_arcs()
        arc = svgpathtools.Arc(
            start=1 + 1j,
            radius=1 + 1j,
            rotation=0,
            large_arc=False,
            sweep=True,
            end=1 + 1j,
        )
        assert arc.start == arc.end

    def test_normal_arc_still_works(self):
        """A valid arc with start != end must work normally."""
        arc = svgpathtools.Arc(
            start=0 + 0j,
            radius=1 + 1j,
            rotation=0,
            large_arc=False,
            sweep=True,
            end=1 + 0j,
        )
        assert arc.start != arc.end
        assert isinstance(arc, svgpathtools.Arc)


class TestSafeAddShape:
    def test_safe_add_shape_good_geometry(self, clean_box):
        from build123d import ExportSVG

        visible, _hidden = clean_box.project_to_viewport(
            (0, -100, 0), viewport_up=(0, 0, 1)
        )
        svg = ExportSVG(scale=1)
        svg.add_layer("Visible", line_weight=0.5)
        result = safe_add_shape(svg, visible, "Visible")
        assert result == 0


class TestRenderSvg:
    def test_render_svg_produces_file(self, clean_box, tmp_path):
        out = tmp_path / "test_front.svg"
        result = render_svg(clean_box, "front", out)
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 0


class TestRenderViews:
    def test_render_views_multiple(self, clean_box, tmp_path):
        results = render_views(
            clean_box,
            views=["front", "iso"],
            output_dir=tmp_path,
            prefix="box",
        )
        assert set(results.keys()) == {"front", "iso"}
        for path in results.values():
            assert path.exists()
            assert path.stat().st_size > 0
