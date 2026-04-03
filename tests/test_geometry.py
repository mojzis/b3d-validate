"""Test geometry validation against real build123d shapes."""

from b3d_validate import validate_geometry


class TestTier1:
    def test_none_shape(self):
        r = validate_geometry(None, tier=1)
        assert not r.ok
        assert any("None" in e for e in r.errors)

    def test_clean_box_valid(self, clean_box):
        r = validate_geometry(clean_box, tier=1)
        assert r.ok
        assert r.is_valid
        assert r.volume > 0
        assert r.area > 0
        assert all(d > 0 for d in r.bbox)

    def test_clean_box_dimensions(self, clean_box):
        r = validate_geometry(clean_box, tier=1)
        bx, by, bz = r.bbox
        assert abs(bx - 20) < 0.1
        assert abs(by - 30) < 0.1
        assert abs(bz - 10) < 0.1

    def test_clean_box_volume(self, clean_box):
        r = validate_geometry(clean_box, tier=1)
        assert abs(r.volume - 6000) < 1


class TestTier2:
    def test_clean_box_topology(self, clean_box):
        r = validate_geometry(clean_box, tier=2)
        assert r.ok
        assert r.n_solids == 1
        assert r.n_shells == 1
        assert r.n_faces == 6
        assert r.n_edges == 12
        assert r.n_vertices == 8

    def test_box_with_hole_topology(self, box_with_hole):
        r = validate_geometry(box_with_hole, tier=2)
        assert r.ok
        assert r.n_solids == 1
        assert r.n_faces > 6  # extra faces from the hole

    def test_multi_solid_warns(self, multi_solid):
        r = validate_geometry(multi_solid, tier=2)
        assert r.n_solids > 1
        assert any("solids" in w for w in r.warnings)


class TestTier3:
    def test_clean_box_deep(self, clean_box):
        r = validate_geometry(clean_box, tier=3)
        assert r.ok
        assert r.bop_valid
        assert r.watertight
        assert r.defects == []

    def test_box_with_hole_deep(self, box_with_hole):
        r = validate_geometry(box_with_hole, tier=3)
        assert r.watertight

    def test_thin_walled_deep(self, thin_walled):
        r = validate_geometry(thin_walled, tier=3)
        assert r.watertight


class TestTierSelection:
    def test_tier1_skips_topology(self, clean_box):
        r = validate_geometry(clean_box, tier=1)
        assert r.n_solids == 0  # not populated at tier 1

    def test_tier2_skips_bop(self, clean_box):
        r = validate_geometry(clean_box, tier=2)
        assert r.bop_valid is False  # not populated at tier 2

    def test_higher_tier_includes_lower(self, clean_box):
        r = validate_geometry(clean_box, tier=3)
        # tier 1 fields
        assert r.volume > 0
        # tier 2 fields
        assert r.n_solids == 1
        # tier 3 fields
        assert r.bop_valid

    def test_elapsed_ms_populated(self, clean_box):
        r = validate_geometry(clean_box)
        assert r.elapsed_ms > 0
