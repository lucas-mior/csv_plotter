"""Extended TSV contract, shared metadata, GUI load/save and empty-file tests."""

import ast
import io
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

import h5py
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.axes import Axes

from csv_plotter_metadata import (
    METADATA_FIELDS, TSV_AUX_FIELDS, TSV_TEXT_KINDS, TsvFormatError,
    read_result_tsv, scan_tsv_sections, serialize_tsv_metadata, write_result_tsv,
)
from csv_plotter_units import read_tsv
import test_hdf5_colors
import test_selector_namespaces
import test_tf_identification_metadata

FIXTURES = Path(__file__).parent / "fixtures" / "tsv_v1"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())
REFERENCE = json.loads((FIXTURES / "expected_metadata.json").read_text())


class ExtendedTsvTests(unittest.TestCase):
    def assert_metadata_equal(self, actual, expected):
        def indexed(rows):
            return {(row["kind"], row["name"]): row for row in rows}
        actual, expected = indexed(actual), indexed(expected)
        self.assertEqual(actual.keys(), expected.keys())
        for key, row in expected.items():
            self.assertEqual(set(actual[key]), set(METADATA_FIELDS))
            for field, value in row.items():
                if (field in METADATA_FIELDS[4:] or field == "value"
                        and key[0] in TSV_AUX_FIELDS and key[0] not in TSV_TEXT_KINDS):
                    if value in ("nan", "inf", "-inf"):
                        value = float(value)
                other = actual[key][field]
                if isinstance(value, float) and math.isnan(value):
                    self.assertTrue(math.isnan(other), (key, field))
                else:
                    self.assertEqual(other, value, (key, field))
                    if isinstance(value, float) and value == 0:
                        self.assertEqual(math.copysign(1, other), math.copysign(1, value))

    def assert_tables_equal(self, left, right):
        frame, registry = left
        other, other_registry = right
        pd.testing.assert_frame_equal(frame, other, check_dtype=False)
        self.assertEqual(registry.source_names(frame.columns),
                         other_registry.source_names(other.columns))
        self.assertEqual(registry.units(), other_registry.units())
        self.assertEqual(registry.colors(frame.columns), other_registry.colors(other.columns))

    def test_all_shared_format_classifications(self):
        for name, expected in MANIFEST["files"].items():
            with self.subTest(name=name), (FIXTURES / name).open("rb") as stream:
                if expected["classification"] == "error":
                    with self.assertRaises(TsvFormatError) as error:
                        scan_tsv_sections(stream)
                    self.assertEqual(error.exception.code, expected["error"])
                    self.assertEqual(error.exception.line, expected["line"])
                else:
                    variant, rows, _ = scan_tsv_sections(stream)
                    self.assertEqual(variant, expected["classification"])
                    if name in REFERENCE:
                        self.assert_metadata_equal(rows, REFERENCE[name])

    def test_all_valid_extended_fixtures_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saved.tsv"
            for name, expected in MANIFEST["files"].items():
                if expected["classification"] not in ("metadata_only", "combined"):
                    continue
                with self.subTest(name=name):
                    variant, rows, frame, registry = read_result_tsv(FIXTURES / name)
                    write_result_tsv(path, variant, rows, frame, registry)
                    raw = path.read_bytes()
                    self.assertTrue(raw.startswith(b"# cystemas-tsv:1\n"))
                    self.assertTrue(raw.endswith(b"\n"))
                    self.assertNotIn(b"\r", raw)
                    new_variant, new_rows, new_frame, new_registry = read_result_tsv(path)
                    self.assertEqual(variant, new_variant)
                    self.assert_metadata_equal(new_rows, rows)
                    self.assert_tables_equal((frame, registry), (new_frame, new_registry))

    def test_equivalent_hdf5_tsv_and_legacy_tables(self):
        for pair in MANIFEST["equivalence_pairs"]:
            with self.subTest(pair=pair):
                tsv_path = FIXTURES / pair["tsv"]
                tsv = test_hdf5_colors.ColorsHdf5Tests().state_for(tsv_path)
                hdf5 = test_hdf5_colors.ColorsHdf5Tests().state_for(FIXTURES / pair["hdf5"])
                for state in (tsv, hdf5):
                    state["reload_file_contents"]()
                self.assertEqual(tsv["tsv_variant"], "combined")
                self.assert_metadata_equal(tsv["metadata_rows"], hdf5["metadata_rows"])
                self.assert_tables_equal((tsv["data_frame"], tsv["column_registry"]),
                                         (hdf5["data_frame"], hdf5["column_registry"]))
                self.assert_tables_equal(read_tsv(tsv_path),
                                         read_tsv(FIXTURES / pair["timeseries_only"]))
                self.assertEqual(tsv["named_value_by_display_name"],
                                 hdf5["named_value_by_display_name"])

    def test_scalar_plot_from_combined_tsv_without_synthetic_column(self):
        state = test_hdf5_colors.ColorsHdf5Tests().state_for(FIXTURES / "simulation_complete.tsv")
        state["h5py"] = None
        state["reload_file_contents"]()
        frame = state["data_frame"].copy()
        name = "parameters.motor.J"
        state["Axes"] = Axes
        state["styles"] = {name: "solid"}
        state["colors"] = {name: "blue"}
        axes = Figure().add_subplot(111)
        state["add_plot"](name, axes)
        np.testing.assert_array_equal(axes.lines[0].get_ydata(), [2.5] * len(frame))
        np.testing.assert_array_equal(axes.lines[0].get_xdata(), frame["time"])
        pd.testing.assert_frame_equal(state["data_frame"], frame)

    def test_gui_save_combined_keeps_metadata_when_signals_edited(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.tsv"
            shutil.copyfile(FIXTURES / "simulation_complete.tsv", path)
            state = test_hdf5_colors.ColorsHdf5Tests().state_for(path)
            state["reload_file_contents"]()
            state["data_frame"]["motor.w"] += 10
            state["column_registry"].get("motor.w").color = "red"
            state["on_save_button_clicked"](None)
            variant, rows, frame, registry = read_result_tsv(path.with_name("result_new.tsv"))
            self.assertEqual(variant, "combined")
            self.assert_metadata_equal(rows, state["metadata_rows"])
            self.assert_tables_equal((frame, registry), (state["data_frame"], state["column_registry"]))

    def test_gui_metadata_only_and_reload_transitions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meta.tsv"
            shutil.copyfile(FIXTURES / "edge_metadata.tsv", path)
            state = test_hdf5_colors.ColorsHdf5Tests().state_for(path)
            state["reload_file_contents"]()
            self.assertFalse(state["has_timeseries"])
            self.assertIsNone(state["x_data"])
            self.assertEqual(state["data_frame"].shape, (0, 0))
            state["on_save_button_clicked"](None)
            variant, rows, frame, registry = read_result_tsv(path.with_name("meta_new.tsv"))
            self.assertEqual(variant, "metadata_only")
            self.assert_metadata_equal(rows, state["metadata_rows"])
            for file, variant, has_data in (("simulation_complete.tsv", "combined", True),
                                            ("empty_metadata.tsv", "metadata_only", False),
                                            ("legacy_timeseries.tsv", "legacy", True)):
                state["filename"] = str(FIXTURES / file)
                state["reload_file_contents"]()
                self.assertEqual(state["tsv_variant"], variant)
                self.assertEqual(state["has_timeseries"], has_data)
                self.assertEqual(state["x_data"] is not None, has_data)
                if variant != "combined":
                    self.assertEqual(state["metadata_rows"], [])
            with self.assertRaisesRegex(ValueError, "no time-series"):
                read_tsv(path)

    def test_metadata_only_hdf5_save_keeps_no_table(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meta.h5"
            with h5py.File(path, "w") as handle:
                handle["param_names"] = [b"a"]
                handle["param_units"] = [b"kg"]
                handle["param_values"] = [2.5]
                handle["opaque"] = [1, 2]
                handle.attrs["future"] = "preserve"
            state = test_hdf5_colors.ColorsHdf5Tests().state_for(path)
            state["reload_file_contents"]()
            self.assertFalse(state["has_timeseries"])
            self.assertIsNone(state["x_data"])
            self.assertEqual(state["data_frame"].shape, (0, 0))
            state["on_save_button_clicked"](None)
            saved = path.with_name("meta_new.h5")
            with h5py.File(saved, "r") as handle:
                self.assertEqual(set(handle), {"param_names", "param_units", "param_values", "opaque"})
                self.assertEqual(handle.attrs["future"], "preserve")
                np.testing.assert_array_equal(handle["opaque"][:], [1, 2])
            reloaded = test_hdf5_colors.ColorsHdf5Tests().state_for(saved)
            reloaded["reload_file_contents"]()
            self.assert_metadata_equal(reloaded["metadata_rows"], state["metadata_rows"])

    def test_empty_table_ui_clears_selector_and_disables_plot_pages(self):
        selector = test_selector_namespaces.SelectorNamespaceTests()
        selector.setUp()
        state = selector.state
        state["data_frame"] = pd.DataFrame()
        state["pre_plots"] = ["old"]
        state["named_values"] = [{"display_name": "parameters.a", "value": 1.}]
        state["clean_plotted_get_list"] = MagicMock(return_value=([], []))
        scroll = type("Scroll", (), {})()
        state["reconfigure_plots_and_buttons"](scroll)
        self.assertEqual(scroll.child.children, [])
        self.assertEqual(state["pre_plots"], [])
        state["clean_plotted_get_list"].assert_called_once()
        source = Path(__file__).resolve().parents[1] / "csv_plotter.py"
        tree = ast.parse(source.read_text())
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name == "update_plot_availability"]
        state["Gtk"] = MagicMock()
        state["plot_notebook"] = object()
        state["spectrum_page_index"] = 1
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), state)
        state["update_plot_availability"]()
        self.assertEqual([call.args[1] for call in state["Gtk"].Widget.set_sensitive.call_args_list], [False, False])
        state["Gtk"].Notebook.set_current_page.assert_called_once_with(state["plot_notebook"], 2)
        state["Gtk"].reset_mock()
        state["data_frame"] = pd.DataFrame({"time": [0., 1.]})
        state["update_plot_availability"]()
        self.assertEqual([call.args[1] for call in state["Gtk"].Widget.set_sensitive.call_args_list], [True, True])

    def test_run_text_not_assumed_to_be_numeric(self):
        state = {"np": np}
        exec(test_tf_identification_metadata.load_metadata_functions(), state)
        for value in ("", "not recorded", "inf", "nan", "1e308", "-1"):
            with self.subTest(value=value):
                self.assertEqual(state["run_metadata_rows"](
                    [{"name": "elapsed_seconds", "value": value}], str),
                    [["elapsed_seconds", value]])

    def test_invalid_metadata_does_not_truncate_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meta.tsv"
            path.write_text("keep me")
            _, rows, frame, registry = read_result_tsv(FIXTURES / "simulation_metadata.tsv")
            rows.append({"kind": "constant", "name": "invalid", "value": 1., "default_value": 2.})
            with self.assertRaises(ValueError):
                write_result_tsv(path, "metadata_only", rows, frame, registry)
            self.assertEqual(path.read_text(), "keep me")

    def test_run_key_order_on_save(self):
        rows = [dict(kind="simulation", name=key, value="text")
                for key in ("unknown_b", "integration_method", "unknown_a", "simulation_date")]
        raw = serialize_tsv_metadata(rows).encode()
        _, parsed, _ = scan_tsv_sections(io.BytesIO(raw))
        self.assertEqual([row["name"] for row in parsed],
                         ["simulation_date", "integration_method", "unknown_b", "unknown_a"])

    def test_unterminated_and_mixed_line_endings(self):
        raw = serialize_tsv_metadata([{"kind": "parameter", "name": "a", "value": -0.0}])
        raw = raw.replace("\n", "\r\n", 1).rstrip("\n").encode()
        variant, rows, _ = scan_tsv_sections(io.BytesIO(raw))
        self.assertEqual(variant, "metadata_only")
        self.assertEqual(math.copysign(1, rows[0]["value"]), -1.)


if __name__ == "__main__":
    unittest.main()
