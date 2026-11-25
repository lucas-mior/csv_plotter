"""Format-independent metadata, HDF5 adapter, and scalar plotting tests."""

import ast
import json
import math
from pathlib import Path
import unittest

import h5py
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from csv_plotter_metadata import (
    METADATA_FIELDS, metadata_views, normalize_metadata_rows,
    read_hdf5_metadata,
)
import test_hdf5_colors


FIXTURES = Path(__file__).parent / "fixtures" / "tsv_v1"


def rows_by_key(rows):
    return {(row["kind"], row["name"]): row for row in rows}


def write_group(handle, prefix, names, values, units=None, **optional):
    handle[f"{prefix}_names"] = np.asarray(names, dtype="S")
    if units is None:
        units = [""] * len(names)
    handle[f"{prefix}_units"] = np.asarray(units, dtype="S")
    handle[f"{prefix}_values"] = np.asarray(values, dtype=float)
    for name, value in optional.items():
        handle[f"{prefix}_{name}"] = np.asarray(value)


class ResultMetadataTests(unittest.TestCase):
    def test_all_hdf5_reference_pairs_match_normalized_metadata(self):
        manifest = json.loads((FIXTURES / "manifest.json").read_text())
        expected = json.loads((FIXTURES / "expected_metadata.json").read_text())
        for pair in manifest["equivalence_pairs"]:
            with self.subTest(pair=pair):
                with h5py.File(FIXTURES / pair["hdf5"], "r") as handle:
                    actual = rows_by_key(read_hdf5_metadata(handle))
                reference = rows_by_key(expected[pair["tsv"]])
                self.assertEqual(actual.keys(), reference.keys())
                for key, row in reference.items():
                    self.assertEqual(set(actual[key]), set(METADATA_FIELDS))
                    for field, value in row.items():
                        if (field in METADATA_FIELDS[4:]
                                or field == "value" and key[0] not in
                                ("fit", "simulation")):
                            if value in ("nan", "inf", "-inf"):
                                value = float(value)
                        if isinstance(value, float) and math.isnan(value):
                            self.assertTrue(math.isnan(actual[key][field]))
                        else:
                            self.assertEqual(actual[key][field], value,
                                             (key, field))
                            if isinstance(value, float) and value == 0:
                                self.assertEqual(math.copysign(1, actual[key][field]),
                                                 math.copysign(1, value))

    def test_equivalent_alias_groups_are_order_independent(self):
        with h5py.File("aliases", "w", driver="core", backing_store=False) as h:
            write_group(h, "param", ["a", "b"], [float("nan"), -0.0],
                        ["kg", "s"], default_values=[1., 2.])
            write_group(h, "parameter", ["b", "a"], [-0.0, float("nan")],
                        ["s", "kg"], default_values=[2., 1.])
            rows = read_hdf5_metadata(h)
            self.assertEqual([row["name"] for row in rows], ["a", "b"])
            self.assertTrue(math.isnan(rows[0]["value"]))
            self.assertEqual(math.copysign(1, rows[1]["value"]), -1.)
            self.assertEqual(rows[1]["default_value"], 2.)
            h["parameter_values"][0] = 0.0
            with self.assertRaisesRegex(ValueError, "Conflicting.*parameter"):
                read_hdf5_metadata(h)
            h["parameter_values"][0] = -0.0
            del h["parameter_default_values"]
            with self.assertRaisesRegex(ValueError, "Conflicting.*parameter"):
                read_hdf5_metadata(h)

    def test_incomplete_alias_not_merged_with_canonical_group(self):
        with h5py.File("partial", "w", driver="core", backing_store=False) as h:
            write_group(h, "fit_param", ["a"], [1.], optimized=[1])
            h["fit_parameter_initial_values"] = [2.]
            with self.assertRaisesRegex(ValueError, "incomplete /fit_parameter"):
                read_hdf5_metadata(h)

    def test_optional_vector_length_and_flag_validation(self):
        with h5py.File("invalid", "w", driver="core", backing_store=False) as h:
            write_group(h, "fit_param", ["a"], [1.], optimized=[2])
            with self.assertRaisesRegex(ValueError, "Invalid optimized flag"):
                read_hdf5_metadata(h)
            h["fit_param_optimized"][0] = 1
            h["fit_param_lower_bounds"] = [0., 1.]
            with self.assertRaisesRegex(ValueError, "expected 1"):
                read_hdf5_metadata(h)

    def test_incomplete_legacy_fit_keeps_original_state_only(self):
        with h5py.File("old_fit", "w", driver="core", backing_store=False) as h:
            write_group(h, "initial_state", ["x"], [1.], ["m"])
            h["fit_metadata_names"] = [b"fit_date"]
            h["fit_metadata_values"] = [b"2026-11-25"]
            row = rows_by_key(read_hdf5_metadata(h))["initial_state", "x"]
            self.assertIsNone(row["value"])
            self.assertEqual(row["initial_value"], 1.)
            h["initial_state_fitted_values"] = [3.]
            row = rows_by_key(read_hdf5_metadata(h))["initial_state", "x"]
            self.assertEqual(row["value"], 3.)
            self.assertEqual(row["initial_value"], 1.)

    def test_duplicate_metadata_keys_rejected(self):
        row = {"kind": "parameter", "name": "a", "value": 1.}
        with self.assertRaisesRegex(ValueError, "Duplicate metadata key"):
            normalize_metadata_rows([row, row])
        with h5py.File("duplicates", "w", driver="core", backing_store=False) as h:
            write_group(h, "param", ["a", "a"], [1., 2.])
            with self.assertRaisesRegex(ValueError, "Duplicate metadata name"):
                read_hdf5_metadata(h)

    def test_format_independent_views_preserve_unknown_and_missing_fields(self):
        rows = normalize_metadata_rows([
            {"kind": "simulation", "name": "elapsed_seconds", "value": "0.05"},
            {"kind": "parameter", "name": "a", "value": 1., "unit": "m"},
            {"kind": "fit_parameter", "name": "a", "value": 2., "optimized": 0},
            {"kind": "fit_input", "name": "u", "value": 0.5, "unit": "s"},
            {"kind": "future", "name": "unknown", "value": "42", "lower_bound": 0.},
        ])
        named, simulation, fit, inputs = metadata_views(rows)
        self.assertEqual([row["display_name"] for row in named],
                         ["parameters.a", "fit_parameters.a"])
        self.assertNotIn("default_value", named[0])
        self.assertEqual(named[1]["optimized"], 0)
        self.assertEqual(simulation, [{"name": "elapsed_seconds", "value": "0.05"}])
        self.assertEqual(fit, [])
        self.assertEqual(inputs, [{"name": "u", "knot_interval": 0.5}])
        self.assertEqual(rows[-1]["value"], "42")
        self.assertEqual(rows[-1]["lower_bound"], 0.)
        self.assertIsNone(rows[1]["default_value"])
        self.assertNotIn("display_name", rows[1])

    def test_selector_collisions_are_deterministic(self):
        rows = normalize_metadata_rows([
            {"kind": "parameter", "name": "a", "value": 1.},
            {"kind": "parameter", "name": "a_2", "value": 2.},
        ])
        columns = ["parameters.a", "parameters.a_3"]
        for values in (rows, rows[::-1]):
            named, *_ = metadata_views(values, columns)
            self.assertEqual({row["name"]: row["display_name"] for row in named},
                             {"a": "parameters.a_4", "a_2": "parameters.a_2"})

    def test_metadata_adapter_does_not_require_timeseries(self):
        with h5py.File("metadata_only", "w", driver="core", backing_store=False) as h:
            write_group(h, "param", ["a"], [2.])
            self.assertEqual(read_hdf5_metadata(h)[0]["value"], 2.)

    def test_reload_clears_metadata_between_file_types(self):
        state = test_hdf5_colors.ColorsHdf5Tests().state_for(FIXTURES / "fit.h5")
        state["reload_file_contents"]()
        self.assertTrue(state["metadata_rows"])
        self.assertTrue(state["named_values"])
        self.assertTrue(state["fit_metadata"])
        self.assertTrue(state["fit_inputs"])
        state["filename"] = str(FIXTURES / "legacy_timeseries.tsv")
        state["reload_file_contents"]()
        for field in ("metadata_rows", "named_values", "fit_metadata",
                      "simulation_metadata", "fit_inputs"):
            self.assertEqual(state[field], [])
        self.assertEqual(state["named_value_by_display_name"], {})
        self.assertEqual(state["file_type"], "tsv")
        state["filename"] = str(FIXTURES / "simulation.h5")
        state["reload_file_contents"]()
        self.assertTrue(state["simulation_metadata"])
        self.assertEqual(state["fit_metadata"], [])
        self.assertEqual(state["fit_inputs"], [])

    def test_scalar_plot_and_spectrum_use_shared_views_without_columns(self):
        state = test_hdf5_colors.ColorsHdf5Tests().state_for(FIXTURES / "simulation.h5")
        state["reload_file_contents"]()
        state["Axes"] = Axes
        name = "parameters.motor.J"
        state["styles"] = {name: "solid"}
        state["colors"] = {name: "blue"}
        source = Path(__file__).resolve().parents[1] / "csv_plotter.py"
        tree = ast.parse(source.read_text())
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in ("spectrum_signal_values", "selector_unit")]
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                     str(source), "exec"), state)
        frame = state["data_frame"].copy()
        axes = Figure().add_subplot(111)
        state["add_plot"](name, axes)
        expected = np.full(len(frame), state["named_value_by_display_name"][name]["value"])
        np.testing.assert_array_equal(axes.lines[0].get_ydata(), expected)
        np.testing.assert_array_equal(state["spectrum_signal_values"](name), expected)
        self.assertEqual(state["selector_unit"](name), "kg*m^2")
        pd.testing.assert_frame_equal(state["data_frame"], frame)


if __name__ == "__main__":
    unittest.main()
