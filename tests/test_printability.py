"""Test printability validation against real build123d shapes."""

from b3d_validate import validate_printability


class TestBasicSanity:
    def test_none_shape(self):
        r = validate_printability(None)
        assert not r.ok
        assert any("None" in e or "null" in e for e in r.errors)

    def test_clean_box_passes(self, clean_box):
        r = validate_printability(clean_box, check_mesh=False)
        assert r.ok

    def test_elapsed_ms_populated(self, clean_box):
        r = validate_printability(clean_box, check_mesh=False)
        assert r.elapsed_ms > 0


class TestOverhangs:
    def test_box_no_overhangs(self, clean_box):
        r = validate_printability(clean_box, check_mesh=False)
        assert r.overhang_face_count == 0

    def test_hole_has_overhangs(self, box_with_hole):
        r = validate_printability(box_with_hole, check_mesh=False)
        assert r.overhang_face_count > 0
        assert len(r.worst_overhangs) > 0
        # overhang angles should be positive
        for oh in r.worst_overhangs:
            assert oh.angle_deg > 0


class TestWallThickness:
    def test_clean_box_no_thin_walls(self, clean_box):
        r = validate_printability(clean_box, check_mesh=False)
        assert r.thin_walls == []

    def test_thin_walled_detected(self, thin_walled):
        r = validate_printability(thin_walled, check_mesh=False, min_wall_mm=1.0)
        assert r.min_wall_mm < 1.0
        assert len(r.thin_walls) > 0
        # each thin wall should have a location string
        for tw in r.thin_walls:
            assert tw.location.startswith("(")


class TestSmallFeatures:
    def test_clean_box_no_small_features(self, clean_box):
        r = validate_printability(clean_box, check_mesh=False)
        assert r.small_edges == 0
        assert r.small_faces == 0

    def test_tiny_chamfer_detected(self, tiny_chamfer):
        r = validate_printability(tiny_chamfer, check_mesh=False, min_feature_mm=0.5)
        assert r.small_edges > 0 or r.small_faces > 0


class TestProcessPresets:
    def test_fdm_defaults(self, clean_box):
        r = validate_printability(clean_box, process="fdm", check_mesh=False)
        assert r.process == "fdm"

    def test_sla_defaults(self, clean_box):
        r = validate_printability(clean_box, process="sla", check_mesh=False)
        assert r.process == "sla"


class TestMeshChecks:
    def test_clean_box_mesh(self, clean_box):
        r = validate_printability(clean_box, check_mesh=True)
        if r.mesh_checked:
            assert r.mesh_watertight
            assert r.mesh_winding_ok

    def test_mesh_skip(self, clean_box):
        r = validate_printability(clean_box, check_mesh=False)
        assert not r.mesh_checked
