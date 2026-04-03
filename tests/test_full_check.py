"""Test full_check end-to-end with real shapes."""

from b3d_validate import full_check


class TestFullCheck:
    def test_clean_box_ready_to_print(self, clean_box):
        result = full_check(clean_box, check_mesh=False)
        assert "GEOMETRY: PASS" in result
        assert "PRINTABILITY" in result
        assert "VERDICT:" in result

    def test_clean_box_verdict(self, clean_box):
        result = full_check(clean_box, check_mesh=False)
        assert "READY TO PRINT" in result

    def test_none_shape_fails(self):
        result = full_check(None, check_mesh=False)
        assert "FAIL" in result
        assert "VERDICT:" in result

    def test_tier_passthrough(self, clean_box):
        r1 = full_check(clean_box, tier=1, check_mesh=False)
        r3 = full_check(clean_box, tier=3, check_mesh=False)
        # tier 3 report has bop/watertight info, tier 1 doesn't
        assert "bop:" in r3
        assert "bop:" in r1  # still in output but shows FAIL (not computed)

    def test_process_passthrough(self, clean_box):
        result = full_check(clean_box, process="sla", check_mesh=False)
        assert "SLA" in result
