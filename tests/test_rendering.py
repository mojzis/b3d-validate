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

    def test_degenerate_arc_has_required_attrs(self):
        """A degenerate arc must expose all attributes svgpathtools reads."""
        arc = svgpathtools.Arc(
            start=0 + 0j,
            radius=1 + 1j,
            rotation=0,
            large_arc=False,
            sweep=True,
            end=0 + 0j,
        )
        # These are what svgpathtools.path.Arc.d() touches.
        for attr in ("radius", "rotation", "large_arc", "sweep", "start", "end"):
            assert hasattr(arc, attr), f"degenerate arc missing '{attr}'"
        # radius must be a complex so .real / .imag work.
        assert hasattr(arc.radius, "real")
        assert hasattr(arc.radius, "imag")

    def test_degenerate_arc_serialises(self):
        """A Path containing a degenerate arc must serialise without raising."""
        arc = svgpathtools.Arc(
            start=0 + 0j,
            radius=1 + 1j,
            rotation=0,
            large_arc=False,
            sweep=True,
            end=0 + 0j,
        )
        path = svgpathtools.Path(arc)
        # This is the call that previously raised:
        #   AttributeError: 'SafeArc' object has no attribute 'radius'
        result = path.d()
        assert isinstance(result, str)


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

    def test_safe_add_shape_isolates_bad_edge(self):
        """A single bad edge must not drop the whole layer."""

        bad = object()
        err = "bad edge"

        class FakeSvg:
            def __init__(self):
                self.added: list[object] = []

            def add_shape(self, edges, layer):
                # Batch path: raise if the bad edge is in the list.
                if isinstance(edges, list):
                    if bad in edges:
                        raise ValueError(err)
                    self.added.extend(edges)
                    return
                # Per-edge fallback path.
                if edges is bad:
                    raise ValueError(err)
                self.added.append(edges)

        svg = FakeSvg()
        good1, good2 = object(), object()
        edges = [good1, bad, good2]

        failed = safe_add_shape(svg, edges, "Visible")

        assert failed == 1
        assert svg.added == [good1, good2]

    def test_safe_add_shape_empty_edges(self):
        err = "should not be called"

        class FakeSvg:
            def add_shape(self, edges, layer):
                raise AssertionError(err)

        assert safe_add_shape(FakeSvg(), [], "Visible") == 0


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
