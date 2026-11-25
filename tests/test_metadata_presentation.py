"""Metadata pane and scalar plotting parity without a graphical GTK session."""

import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

import h5py
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from csv_plotter_metadata import normalize_metadata_rows
import test_hdf5_colors
from test_result_metadata import write_group
from test_tf_identification_metadata import load_metadata_functions


FIXTURES = Path(__file__).parent / "fixtures" / "tsv_v1"
PAIRS = json.loads((FIXTURES / "manifest.json").read_text())["equivalence_pairs"]


def load_presentation(path):
    state = test_hdf5_colors.ColorsHdf5Tests().state_for(path)
    state["reload_file_contents"]()
    exec(load_metadata_functions(), state)
    source = Path(__file__).resolve().parents[1] / "csv_plotter.py"
    tree = ast.parse(source.read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in ("selector_unit", "spectrum_signal_values")]
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                 str(source), "exec"), state)
    state["Axes"] = Axes
    state["Gtk"] = MagicMock()
    return state


def pane_text(state):
    # Ignore only the displayed filename, not any metadata content.
    state["filename"] = "equivalent-result"
    state["reconfigure_metadata_tab"](MagicMock())
    return state["Gtk"].TextBuffer.set_text.call_args.args[1]


class MetadataPresentationTests(unittest.TestCase):
    def test_all_shared_pairs_render_identical_metadata_text(self):
        for pair in PAIRS:
            with self.subTest(pair=pair):
                hdf5 = load_presentation(FIXTURES / pair["hdf5"])
                tsv = load_presentation(FIXTURES / pair["tsv"])
                self.assertEqual(pane_text(hdf5), pane_text(tsv))
                # Row ordering from the original file cannot change the pane.
                original = pane_text(tsv)
                tsv["configure_metadata"](tsv["metadata_rows"][::-1],
                                          tsv["data_frame"].columns)
                self.assertEqual(pane_text(tsv), original)

    def test_all_scalar_selectors_and_plot_values_match(self):
        for pair in PAIRS:
            with self.subTest(pair=pair):
                hdf5 = load_presentation(FIXTURES / pair["hdf5"])
                tsv = load_presentation(FIXTURES / pair["tsv"])
                names = set(hdf5["named_value_by_display_name"])
                self.assertEqual(names, set(tsv["named_value_by_display_name"]))
                self.assertIn("initial_states.motor.w", names)
                if pair["hdf5"].startswith("fit"):
                    self.assertIn("fit_initial_states.motor.w", names)
                frames = [state["data_frame"].copy() for state in (hdf5, tsv)]
                for name in names:
                    expected = hdf5["named_value_by_display_name"][name]["value"]
                    self.assertEqual(hdf5["selector_unit"](name), tsv["selector_unit"](name))
                    for state in (hdf5, tsv):
                        state["styles"] = {name: "solid"}
                        state["colors"] = {name: "blue"}
                        axes = Figure().add_subplot(111)
                        state["add_plot"](name, axes)
                        values = np.full(len(state["data_frame"]), expected)
                        np.testing.assert_array_equal(axes.lines[0].get_ydata(), values)
                        np.testing.assert_array_equal(axes.lines[0].get_xdata(), state["x_data"])
                        np.testing.assert_array_equal(state["spectrum_signal_values"](name), values)
                for frame, state in zip(frames, (hdf5, tsv)):
                    pd.testing.assert_frame_equal(frame, state["data_frame"])

    def test_fit_pane_displays_defaults_snapshots_and_decisions(self):
        state = load_presentation(FIXTURES / "fit_complete.tsv")
        text = pane_text(state)
        for heading in ("Fitted values committed", "Default", "Initial states",
                        "Fitted initial states", "Original initial", "Optimized",
                        "initial_states.motor.theta", "fit_initial_states.motor.w"):
            self.assertIn(heading, text)
        rows = state["metadata_rows_for_kind"]("fit_parameter", (
            "name", "value", "initial_value", "original_initial_value",
            "lower_bound", "upper_bound", "optimized"))
        self.assertEqual(rows, [["motor.B", .1, .1, .1, .1, .1, "No"],
                                ["motor.J", 3.125, 2.25, 2.5, .01, float("inf"), "Yes"]])
        self.assertEqual(state["metadata_rows_for_kind"]("initial_state", (
            "name", "value", "initial_value")),
            [["motor.theta", .25, .25], ["motor.w", .75, 0.]])

    def test_incomplete_legacy_state_is_visible_but_not_plottable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old_fit.h5"
            with h5py.File(path, "w") as handle:
                write_group(handle, "initial_state", ["x"], [1.], ["m"])
                handle["fit_metadata_names"] = [b"fit_date"]
                handle["fit_metadata_values"] = [b"2026-11-25"]
            state = load_presentation(path)
            self.assertIn("Initial states", pane_text(state))
            self.assertEqual(state["metadata_rows_for_kind"]("initial_state", (
                "name", "value", "initial_value", "display_name")), [["x", None, 1., None]])
            self.assertNotIn("initial_states.x", state["named_value_by_display_name"])
            self.assertIn("—", pane_text(state))

    def test_unknown_metadata_and_escaped_text_remain_visible(self):
        state = load_presentation(FIXTURES / "edge_metadata.tsv")
        text = pane_text(state)
        for expected in ("Other metadata (future_kind)", r"null\tvalue",
                         r"a\\b\tµ", "-0.0", "5e-324", "nan", "-inf", "No"):
            self.assertIn(expected, text)
        self.assertNotIn("extra", state["named_value_by_display_name"])
        state["configure_metadata"](normalize_metadata_rows([
            {"kind": "future_kind", "name": "only", "value": "text"}]))
        text = pane_text(state)
        self.assertIn("Other metadata (future_kind)", text)
        self.assertNotIn("does not contain recognized metadata", text)


if __name__ == "__main__":
    unittest.main()
