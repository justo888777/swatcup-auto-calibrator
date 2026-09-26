import shutil
import unittest
from pathlib import Path

from swatcup_auto.runner import (
    INTEGER_PIPE_PARAMETERS,
    ReservoirScope,
    apply_class_weights,
    clear_sufi2_out,
    clear_swat_outputs,
    conservative_res_parameter_rows,
    copy_worker_project,
    parse_par_inf,
    reservoir_scope,
    select_best_row,
)


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path("tests") / "_runtime" / self._testMethodName
        if self.directory.exists():
            shutil.rmtree(self.directory)
        self.directory.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.directory.exists():
            shutil.rmtree(self.directory)
        runtime_root = self.directory.parent
        if runtime_root.exists() and not any(runtime_root.iterdir()):
            runtime_root.rmdir()

    def test_par_inf_declared_count_must_match_rows(self) -> None:
        path = self.directory / "par_inf.txt"
        path.write_text(
            "2 : Number of Parameters\n10 : number of simulations\n\n"
            "v__CN2.mgt 0.0 1.0\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "declares 2 parameters"):
            parse_par_inf(path)

    def test_par_inf_ignores_inactive_examples_after_declared_rows(self) -> None:
        path = self.directory / "par_inf.txt"
        path.write_text(
            "2 : Number of Parameters\n8 : number of simulations\n\n"
            "r__CN2.mgt -0.2 0.2\n"
            "v__ALPHA_BF.gw 0.0 1.0\n"
            "-----------------\n"
            "v__GW_DELAY.gw 30.0 450.0\n",
            encoding="utf-8",
        )

        rows = parse_par_inf(path)

        self.assertEqual([row[0] for row in rows], ["r__CN2.mgt", "v__ALPHA_BF.gw"])

    def test_integer_parameter_compatibility_is_preserved(self) -> None:
        self.assertTrue(
            {"CH_EQN", "SUBD_CHSED", "ICFAC", "ICN", "IRESCO", "IFLOD1R", "IFLOD2R", "NDTARGR"}
            <= INTEGER_PIPE_PARAMETERS
        )

    def test_worker_directory_cannot_be_inside_source_project(self) -> None:
        project = self.directory / "project"
        project.mkdir()
        with self.assertRaisesRegex(ValueError, "outside the source project"):
            copy_worker_project(project, project / "results" / "workers", 1, False)

    def test_swat_outputs_are_removed_before_each_run(self) -> None:
        removable = (
            "output.rch", "input.std", "fin.fin", "watout.dat", "hyd.out",
            "chan.deg", "bmp-ri.out", "septic.out", "swat_output.txt",
        )
        for name in removable:
            (self.directory / name).write_text("stale", encoding="utf-8")
        control = self.directory / "file.cio"
        control.write_text("keep", encoding="utf-8")

        clear_swat_outputs(self.directory)

        self.assertTrue(control.exists())
        self.assertFalse(any((self.directory / name).exists() for name in removable))

    def test_extracted_series_are_cleared_before_each_run(self) -> None:
        out_dir = self.directory / "SUFI2.OUT"
        out_dir.mkdir()
        (out_dir / "FLOW_OUT_1.txt").write_text("old", encoding="utf-8")

        clear_sufi2_out(self.directory)

        self.assertEqual(list(out_dir.iterdir()), [])

    def test_class_weights_preserve_within_class_ratios(self) -> None:
        names = ["FLOW_OUT_1", "FLOW_OUT_2", "SED_OUT_1"]
        weights = {"FLOW_OUT_1": 1.0, "FLOW_OUT_2": 3.0, "SED_OUT_1": 1.0}

        weighted = apply_class_weights("FLOW=0.4,SEDIMENT=0.6", names, weights)

        self.assertAlmostEqual(weighted["FLOW_OUT_1"], 0.1)
        self.assertAlmostEqual(weighted["FLOW_OUT_2"], 0.3)
        self.assertAlmostEqual(weighted["SED_OUT_1"], 0.6)

    def test_clipped_run_is_not_selected_by_default(self) -> None:
        rows = [
            {"run": 1, "status": "ok", "score": 0.9, "clip_count": 1},
            {"run": 2, "status": "ok", "score": 0.7, "clip_count": 0},
        ]

        selected, feasible_count = select_best_row(rows, [], {}, None, None, {}, False)

        self.assertEqual(selected["run"], 2)
        self.assertEqual(feasible_count, 1)

    def test_reservoir_ranges_keep_months_and_editor_limits(self) -> None:
        project = self.directory
        res_name = "000170000.res"
        (project / res_name).write_text(
            "500 | RES_RR\n"
            "120 | NDTARGR\n"
            "0.7 | EVRSV\n"
            "0.1 | RES_K\n"
            "1000 | RES_PVOL\n"
            "2000 | RES_EVOL\n"
            "STARG:\n 1000 1100 1200 1300 1400 1500 1600 1700 1800 1900 2000 2100\n"
            "WURESN:\n 1 2 3 4 5 6 7 8 9 10 11 12\n"
            "OFLOWMN:\n 10 10 10 10 10 10 10 10 10 10 10 10\n"
            "OFLOWMX:\n 20 20 20 20 20 20 20 20 20 20 20 20\n",
            encoding="utf-8",
        )
        scope = ReservoirScope(17, "local", res_name, 17, 17, 5, 4)
        rows = conservative_res_parameter_rows(project, [scope])
        by_name = {name: (lower, upper) for name, lower, upper in rows}

        self.assertIn("v__STARG(1).res________17", by_name)
        self.assertIn("v__STARG(12).res________17", by_name)
        self.assertNotIn("v__STARG.res________17", by_name)
        self.assertEqual(by_name["v__RES_RR.res________17"][1], 500.0)
        for month in range(1, 13):
            min_range = by_name[f"v__OFLOWMN({month}).res________17"]
            max_range = by_name[f"v__OFLOWMX({month}).res________17"]
            self.assertLessEqual(min_range[1], max_range[0])

    def test_reservoir_scope_excludes_same_subbasin_downstream_reservoir(self) -> None:
        project = self.directory
        (project / "fig.fig").write_text(
            "subbasin 0 4 4\n000040000.sub\n"
            "routres 0 5 5 4\n000170000.res\n"
            "route 0 10 17 5\n"
            "routres 0 20 20 10\n000170001.res\n",
            encoding="utf-8",
        )
        (project / "000170000.res").write_text("17 | RES_SUB\n", encoding="utf-8")
        (project / "000170001.res").write_text("17 | RES_SUB\n", encoding="utf-8")

        scopes = reservoir_scope(project, [17])

        self.assertEqual([scope.res_file for scope in scopes], ["000170000.res"])
        self.assertEqual(scopes[0].relation, "local")


if __name__ == "__main__":
    unittest.main()
