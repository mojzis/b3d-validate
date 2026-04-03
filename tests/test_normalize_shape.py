"""Test that validate_geometry, validate_printability, and full_check accept ShapeLists."""

from build123d import Box, ShapeList

from b3d_validate import full_check, validate_geometry, validate_printability


def _make_shapelist():
    """Create a ShapeList containing a single solid box."""
    box = Box(20, 30, 10)
    return ShapeList([box])


class TestValidateGeometryWithShapeList:
    def test_shapelist_passes(self):
        sl = _make_shapelist()
        r = validate_geometry(sl, tier=3)
        assert r.ok
        assert r.volume > 0
        assert r.is_valid

    def test_shapelist_volume_matches_box(self):
        sl = _make_shapelist()
        r = validate_geometry(sl, tier=1)
        assert abs(r.volume - 6000) < 1

    def test_shapelist_topology(self):
        sl = _make_shapelist()
        r = validate_geometry(sl, tier=2)
        assert r.n_solids >= 1
        assert r.n_faces >= 6


class TestValidatePrintabilityWithShapeList:
    def test_shapelist_passes(self):
        sl = _make_shapelist()
        r = validate_printability(sl, process="fdm", check_mesh=False)
        assert r.ok

    def test_shapelist_has_volume(self):
        sl = _make_shapelist()
        # Should not error with "non-positive volume"
        r = validate_printability(sl, process="fdm", check_mesh=False)
        assert not any("non-positive volume" in e for e in r.errors)


class TestFullCheckWithShapeList:
    def test_shapelist_ready_to_print(self):
        sl = _make_shapelist()
        result = full_check(sl, check_mesh=False)
        assert "GEOMETRY: PASS" in result
        assert "VERDICT:" in result
