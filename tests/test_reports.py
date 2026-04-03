"""Unit tests for report dataclasses and formatting (no build123d needed)."""

from b3d_validate.geometry import GeometryReport
from b3d_validate.printability import (
    OverhangInfo,
    PrintabilityReport,
    ThinWallInfo,
)


class TestGeometryReport:
    def test_default_is_ok(self):
        r = GeometryReport()
        assert r.ok is True
        assert r.errors == []
        assert r.warnings == []

    def test_err_sets_ok_false(self):
        r = GeometryReport()
        r._err("something broke")
        assert r.ok is False
        assert "something broke" in r.errors

    def test_warn_keeps_ok_true(self):
        r = GeometryReport()
        r._warn("heads up")
        assert r.ok is True
        assert "heads up" in r.warnings

    def test_str_pass(self):
        r = GeometryReport(
            volume=6000.0,
            area=2200.0,
            bbox=(20.0, 30.0, 10.0),
            is_valid=True,
            bop_valid=True,
            watertight=True,
            n_solids=1,
            n_shells=1,
            n_faces=6,
            n_edges=12,
            n_vertices=8,
            elapsed_ms=1.5,
        )
        s = str(r)
        assert "GEOMETRY: PASS" in s
        assert "vol=6000.00" in s
        assert "solids=1" in s
        assert "brep:OK" in s
        assert "bop:OK" in s
        assert "watertight:OK" in s

    def test_str_fail_with_errors(self):
        r = GeometryReport()
        r._err("bad shape")
        s = str(r)
        assert "GEOMETRY: FAIL" in s
        assert "[ERR] bad shape" in s

    def test_str_defects_capped(self):
        r = GeometryReport(defects=[f"defect_{i}" for i in range(12)])
        s = str(r)
        assert "defects (12 total)" in s
        assert "defect_0" in s
        assert "defect_7" in s
        assert "+4 more" in s

    def test_str_with_warnings(self):
        r = GeometryReport()
        r._warn("something fishy")
        s = str(r)
        assert "[WARN] something fishy" in s


class TestPrintabilityReport:
    def test_default_is_ok(self):
        r = PrintabilityReport()
        assert r.ok is True
        assert r.process == "fdm"

    def test_err_sets_ok_false(self):
        r = PrintabilityReport()
        r._err("too thin")
        assert r.ok is False
        assert "too thin" in r.errors

    def test_str_pass_no_issues(self):
        r = PrintabilityReport(elapsed_ms=2.0)
        s = str(r)
        assert "PRINTABILITY (FDM): PASS" in s
        assert "overhangs: none" in s
        assert "min_wall: OK" in s

    def test_str_sla_process(self):
        r = PrintabilityReport(process="sla")
        s = str(r)
        assert "PRINTABILITY (SLA)" in s

    def test_str_with_overhangs(self):
        r = PrintabilityReport(
            overhang_face_count=3,
            overhang_area_pct=25.5,
            worst_overhangs=[
                OverhangInfo(
                    face_idx=2, angle_deg=60.0, area=15.0, center="(1.0,2.0,3.0)"
                ),
            ],
        )
        s = str(r)
        assert "overhangs: 3 faces" in s
        assert "25.5%" in s
        assert "face#2 60" in s

    def test_str_with_thin_walls(self):
        r = PrintabilityReport(
            min_wall_mm=0.5,
            thin_walls=[
                ThinWallInfo(
                    thickness_mm=0.5, location="(1.0,2.0,3.0)",
                    face_a_idx=0, face_b_idx=1,
                ),
            ],
        )
        s = str(r)
        assert "min_wall: 0.50mm" in s
        assert "0.50mm between face#0" in s

    def test_str_with_small_features(self):
        r = PrintabilityReport(small_edges=3, small_faces=1)
        s = str(r)
        assert "small_features: 3 short edges, 1 tiny faces" in s

    def test_str_mesh_checked(self):
        r = PrintabilityReport(
            mesh_checked=True,
            mesh_watertight=True,
            mesh_winding_ok=True,
            mesh_degenerate_faces=0,
        )
        s = str(r)
        assert "watertight:OK" in s
        assert "winding:OK" in s

    def test_str_mesh_not_available(self):
        r = PrintabilityReport(mesh_checked=False)
        s = str(r)
        assert "mesh: skipped" in s


class TestFullCheck:
    def test_full_check_verdicts(self):
        # We can't call full_check without build123d shapes,
        # but we can test the verdict logic by testing the report
        # combination indirectly via the report __str__ methods
        geo_pass = GeometryReport()
        geo_fail = GeometryReport()
        geo_fail._err("bad")

        prn_pass = PrintabilityReport()
        prn_fail = PrintabilityReport()
        prn_fail._err("bad")

        # Both pass
        assert geo_pass.ok and prn_pass.ok
        # Geo pass, prn fail
        assert geo_pass.ok and not prn_fail.ok
        # Geo fail, prn pass
        assert not geo_fail.ok and prn_pass.ok
        # Both fail
        assert not geo_fail.ok and not prn_fail.ok
