"""Tests for units in Cystemas-style TSV headers."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from csv_plotter_units import read_tsv, split_tsv_header, write_tsv


class TsvUnitTests(unittest.TestCase):
    def test_split_cystemas_headers(self):
        examples = {
            "time[s]": ("time", "s"),
            "Q [kg/s]": ("Q", "kg/s"),
            "boiler.temperature [ K ] ": ("boiler.temperature", "K"),
            "ref.Q[m^3/s]": ("ref.Q", "m^3/s"),
            "x[old][m]": ("x[old]", "m"),
            "p": ("p", ""),
            "pressure [not closed": ("pressure [not closed", ""),
            "A [ ]": ("A", ""),
        }
        for raw, expected in examples.items():
            with self.subTest(header=raw):
                self.assertEqual(split_tsv_header(raw), expected)

    def test_load_and_save_preserve_units(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.tsv"
            saved = Path(directory) / "saved.tsv"
            original.write_text(
                "time[s]\tQ [kg/s]\tboiler.temperature [K]\tpressure\n"
                "0\t1.5\t320\t100\n"
                "1\t2.5\t321\t101\n", encoding="utf-8")

            frame, units = read_tsv(original)
            self.assertEqual(
                list(frame.columns),
                ["time", "Q", "boiler.temperature", "pressure"])
            self.assertEqual(units, {
                "time": "s", "Q": "kg/s", "boiler.temperature": "K",
                "pressure": "",
            })

            frame.rename(columns={"Q": "flow"}, inplace=True)
            units["flow"] = units.pop("Q")
            frame["calculated"] = frame["flow"] * 2
            units["calculated"] = ""
            write_tsv(saved, frame, units)

            self.assertEqual(saved.read_text(encoding="utf-8").splitlines()[0],
                             "time[s]\tflow[kg/s]\tboiler.temperature[K]"
                             "\tpressure\tcalculated")
            reloaded, reloaded_units = read_tsv(saved)
            pd.testing.assert_frame_equal(reloaded, frame)
            self.assertEqual(reloaded_units, units)

    def test_duplicate_names_after_splitting_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.tsv"
            path.write_text("Q[m]\tQ[cm]\n1\t2\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate.*Q"):
                read_tsv(path)

    def test_empty_column_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.tsv"
            path.write_text("time[s]\t[K]\n1\t2\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "empty column name"):
                read_tsv(path)


if __name__ == "__main__":
    unittest.main()
