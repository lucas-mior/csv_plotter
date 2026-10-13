"""HDF5 duplicate-column/name/unit round-trip without GTK."""

import ast
from pathlib import Path
import tempfile
import unittest

try:
    import h5py
except ImportError:
    h5py = None
import numpy as np
import pandas as pd

from csv_plotter_units import ColumnRegistry, read_csv, read_tsv, write_csv, write_tsv


FUNCTIONS = {
    "filename_has_hdf5_extension", "read_hdf5_strings",
    "hdf5_dataset_exists", "read_hdf5_float_vector",
    "read_hdf5_named_values", "read_hdf5_text_metadata",
    "fixed_hdf5_strings", "write_hdf5_named_values",
    "configure_hdf5_named_values", "configure_hdf5_simulation_metadata",
    "configure_hdf5_fit_metadata", "configure_hdf5_fit_inputs",
    "reload_file_contents", "on_save_button_clicked",
}


def load_hdf5_functions():
    path = Path(__file__).resolve().parents[1] / "csv_plotter.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in FUNCTIONS]
    return compile(ast.fix_missing_locations(
        ast.Module(body=nodes, type_ignores=[])), str(path), "exec")


class Hdf5ColumnTests(unittest.TestCase):
    @unittest.skipIf(h5py is None, "h5py is not installed")
    def test_duplicate_columns_keep_original_names_after_save(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "sample.h5"
            with h5py.File(original, "w") as file:
                file["data"] = np.array([[0., 2., 200000., 14.],
                                         [1., 3., 300000., 15.]])
                file["names"] = np.array([b"time", b"pressure",
                                          b"pressure", b"pressure_bar"])
                file["units"] = np.array([b"s", b"bar", b"Pa", b""])

            state = {
                "filename": str(original),
                "h5py": h5py,
                "np": np,
                "pd": pd,
                "DataFrame": pd.DataFrame,
                "ColumnRegistry": ColumnRegistry,
                "read_csv": read_csv,
                "read_tsv": read_tsv,
                "write_csv": write_csv,
                "write_tsv": write_tsv,
                "hdf5_named_values": [],
                "hdf5_named_value_by_display_name": {},
                "hdf5_simulation_metadata": [],
                "hdf5_fit_metadata": [],
                "hdf5_fit_inputs": [],
                "HDF5_EXTENSIONS": (".h5", ".hdf5"),
                "os": __import__("os"),
                "sys": __import__("sys"),
            }
            exec(load_hdf5_functions(), state)
            state["reload_file_contents"]()

            self.assertEqual(state["file_type"], "hdf5")
            self.assertEqual(list(state["data_frame"].columns),
                             ["time", "pressure_bar_2", "pressure_pa",
                              "pressure_bar"])
            self.assertEqual(state["column_registry"].get(
                "pressure_bar_2").display_label, "pressure [bar]")
            self.assertEqual(state["column_registry"].get(
                "pressure_pa").display_label, "pressure [Pa]")

            state["on_save_button_clicked"](None)
            saved = Path(directory) / "sample_new.h5"
            with h5py.File(saved, "r") as file:
                self.assertEqual([s.decode() for s in file["names"][:]],
                                 ["time", "pressure", "pressure",
                                  "pressure_bar"])
                self.assertEqual([s.decode() for s in file["units"][:]],
                                 ["s", "bar", "Pa", ""])
                np.testing.assert_array_equal(file["data"][:],
                                              state["data_frame"].to_numpy())


if __name__ == "__main__":
    unittest.main()
