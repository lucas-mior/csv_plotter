"""Cystemas transfer-function HDF5 metadata loading and round-trip tests."""

import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

import h5py
import numpy as np
import pandas as pd

from csv_plotter_units import (
    ColumnRegistry, read_csv, read_tsv, write_csv, write_tsv
)
from test_hdf5_columns import load_hdf5_functions
from csv_plotter_metadata import read_hdf5_named_values


TF_VALUES = [
    ("tf.mode", "", 1.0),
    ("tf.ninputs", "", 1.0),
    ("tf.noutputs", "", 1.0),
    ("tf.output.0.validation_rmse", "", 0.0277),
    ("tf.output.0.validation_fit", "%", 99.6),
    ("tf.path.0.0.gain", "", 28.62),
    ("tf.path.0.0.numerator.0", "", 28.62),
    ("tf.path.0.0.denominator.0", "", 9.759),
    ("tf.path.0.0.denominator.1", "", 0.7487),
    ("tf.path.0.0.denominator.2", "", 1.0),
]

METADATA_FUNCTIONS = {
    "run_metadata_display_name", "simulation_metadata_display_name",
    "fit_metadata_display_name", "metadata_values_for_kind",
    "append_metadata_text_section", "run_metadata_rows",
    "metadata_rows_for_kind", "metadata_pane_text", "reconfigure_metadata_tab",
}


def load_metadata_functions():
    path = Path(__file__).resolve().parents[1] / "csv_plotter.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in METADATA_FUNCTIONS]
    return compile(ast.fix_missing_locations(
        ast.Module(body=nodes, type_ignores=[])), str(path), "exec")


class TfIdentificationMetadataTests(unittest.TestCase):
    def create_file(self, path):
        with h5py.File(path, "w") as handle:
            handle["data"] = np.array([[0., 1.], [1., 2.]])
            handle["names"] = np.array([b"time", b"theta"])
            handle["units"] = np.array([b"s", b"deg"])
            handle["tf_parameter_names"] = np.array(
                [row[0].encode() for row in TF_VALUES])
            handle["tf_parameter_units"] = np.array(
                [row[1].encode() for row in TF_VALUES])
            handle["tf_parameter_values"] = np.array(
                [row[2] for row in TF_VALUES], dtype=np.float64)
            handle["fit_parameter_names"] = np.array([b"damping"])
            handle["fit_parameter_units"] = np.array([b"kg/s"])
            handle["fit_parameter_values"] = np.array([0.75])
            handle.attrs["schema_version"] = "unknown-v3"
            handle["data"].attrs["signal_source"] = "simulation"
            extra = handle.create_group("future_metadata")
            extra.attrs["description"] = "preserve recursively"
            extra.create_dataset("opaque_values", data=[3, 5, 8],
                                 compression="gzip")
            handle.create_dataset("future_scalar", data=42)

    def new_state(self, filename):
        state = {
            "filename": str(filename),
            "h5py": h5py,
            "np": np,
            "pd": pd,
            "DataFrame": pd.DataFrame,
            "ColumnRegistry": ColumnRegistry,
            "read_csv": read_csv,
            "read_tsv": read_tsv,
            "write_csv": write_csv,
            "write_tsv": write_tsv,
            "named_values": [],
            "named_value_by_display_name": {},
            "simulation_metadata": [],
            "fit_metadata": [],
            "fit_inputs": [],
            "HDF5_EXTENSIONS": (".h5", ".hdf5"),
            "os": __import__("os"),
            "sys": __import__("sys"),
        }
        exec(load_hdf5_functions(), state)
        exec(load_metadata_functions(), state)
        return state

    def test_load_shows_tf_metadata_in_separate_tab_section(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fit.h5"
            self.create_file(path)
            state = self.new_state(path)
            state["reload_file_contents"]()
            values = state["metadata_values_for_kind"]("tf_parameter")
            self.assertEqual(len(values), len(TF_VALUES))
            self.assertEqual(values[6]["name"], "tf.path.0.0.numerator.0")
            self.assertEqual(values[6]["value"], 28.62)
            self.assertEqual(values[6]["display_name"],
                             "tf_parameters.tf.path.0.0.numerator.0")
            self.assertEqual(values[4]["unit"], "%")
            self.assertIn(values[6]["display_name"],
                          state["named_value_by_display_name"])

            gtk = MagicMock()
            state["Gtk"] = gtk
            state["reconfigure_metadata_tab"](MagicMock())
            text = gtk.TextBuffer.set_text.call_args.args[1]
            self.assertIn("TF identification", text)
            self.assertIn("tf.path.0.0.numerator.0", text)
            self.assertIn("28.62", text)
            self.assertIn("Fitted parameters", text)

    def test_open_save_preserves_tf_and_unknown_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fit.h5"
            self.create_file(path)
            state = self.new_state(path)
            state["reload_file_contents"]()

            # Simulate a changed signal column, but keep its source metadata.
            state["data_frame"]["theta"] += 10.
            state["on_save_button_clicked"](None)
            saved = Path(directory) / "fit_new.h5"
            with h5py.File(saved, "r") as handle:
                self.assertEqual([s.decode() for s in handle[
                    "tf_parameter_names"][:]], [row[0] for row in TF_VALUES])
                self.assertEqual([s.decode() for s in handle[
                    "tf_parameter_units"][:]], [row[1] for row in TF_VALUES])
                np.testing.assert_array_equal(
                    handle["tf_parameter_values"][:],
                    [row[2] for row in TF_VALUES])
                np.testing.assert_array_equal(
                    handle["fit_parameter_values"][:], [0.75])
                np.testing.assert_array_equal(
                    handle["future_metadata/opaque_values"][:], [3, 5, 8])
                self.assertEqual(handle["future_scalar"][()], 42)
                self.assertEqual(handle.attrs["schema_version"],
                                 "unknown-v3")
                self.assertEqual(handle["data"].attrs["signal_source"],
                                 "simulation")
                self.assertEqual(handle["future_metadata"].attrs[
                    "description"], "preserve recursively")
                self.assertEqual(handle[
                    "future_metadata/opaque_values"].compression, "gzip")
                np.testing.assert_array_equal(
                    handle["data"][:], [[0., 11.], [1., 12.]])

            reloaded = self.new_state(saved)
            reloaded["reload_file_contents"]()
            self.assertEqual(reloaded["metadata_values_for_kind"](
                "tf_parameter"), state["metadata_values_for_kind"](
                    "tf_parameter"))

    def test_changed_column_count_preserves_tf_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fit.h5"
            self.create_file(path)
            state = self.new_state(path)
            state["reload_file_contents"]()
            registry = state["column_registry"]
            registry.add("new_extra_signal")
            state["data_frame"]["new_extra_signal"] = [7., 8.]
            state["on_save_button_clicked"](None)
            with h5py.File(Path(directory) / "fit_new.h5", "r") as handle:
                self.assertEqual(handle["data"].shape, (2, 3))
                self.assertEqual(len(handle["names"][:]), 3)
                np.testing.assert_array_equal(
                    handle["tf_parameter_values"][:],
                    [row[2] for row in TF_VALUES])
                self.assertEqual(handle["data"].attrs["signal_source"],
                                 "simulation")

    def test_incomplete_tf_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.h5"
            with h5py.File(path, "w") as handle:
                handle["tf_parameter_names"] = np.array([b"tf.mode"])
                handle["tf_parameter_values"] = np.array([0.])
                with self.assertRaisesRegex(ValueError,
                                            "incomplete /tf_parameter"):
                    read_hdf5_named_values(
                        handle, "tf_parameter")


if __name__ == "__main__":
    unittest.main()
