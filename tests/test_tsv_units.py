"""Tests for column identity, unit metadata, and CSV/TSV round trips."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from csv_plotter_units import (
    ColumnRegistry, read_csv, read_tsv, split_tsv_header, unit_suffix,
    write_csv, write_tsv,
)


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

    def test_load_and_save_preserve_units_after_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.tsv"
            saved = Path(directory) / "saved.tsv"
            original.write_text(
                "time[s]\tQ [kg/s]\tboiler.temperature [K]\tpressure\n"
                "0\t1.5\t320\t100\n"
                "1\t2.5\t321\t101\n", encoding="utf-8")

            frame, registry = read_tsv(original)
            self.assertEqual(list(frame.columns),
                             ["time", "Q", "boiler.temperature", "pressure"])
            self.assertEqual(registry.units(), {
                "time": "s", "Q": "kg/s", "boiler.temperature": "K",
                "pressure": "",
            })

            info = registry.rename("Q", "flow")
            frame.rename(columns={"Q": info.internal_name}, inplace=True)
            info = registry.add("calculated")
            frame[info.internal_name] = frame["flow"] * 2
            write_tsv(saved, frame, registry)

            self.assertEqual(saved.read_text(encoding="utf-8").splitlines()[0],
                             "time[s]\tflow[kg/s]\tboiler.temperature[K]"
                             "\tpressure\tcalculated")
            reloaded, new_registry = read_tsv(saved)
            pd.testing.assert_frame_equal(reloaded, frame)
            self.assertEqual(new_registry.units(), registry.units())

    def test_duplicate_names_with_different_units_are_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.tsv"
            saved = Path(directory) / "saved.tsv"
            original.write_text(
                "time[s]\tpressure[bar]\tpressure[Pa]\tplant.p[m^3]"
                "\tplant.p[kg/s]\n0\t1\t2\t3\t4\n",
                encoding="utf-8")

            frame, registry = read_tsv(original)
            self.assertEqual(list(frame.columns), [
                "time", "pressure_bar", "pressure_pa", "plant.p_m3",
                "plant.p_kg_s",
            ])
            self.assertEqual(registry.get("pressure_bar").display_label,
                             "pressure [bar]")
            self.assertEqual(registry.get("pressure_pa").display_label,
                             "pressure [Pa]")
            write_tsv(saved, frame, registry)
            self.assertEqual(original.read_text(), saved.read_text())
            round_trip, new_registry = read_tsv(saved)
            pd.testing.assert_frame_equal(round_trip, frame)
            self.assertEqual(new_registry.units(), registry.units())

    def test_existing_suffixed_name_is_never_overwritten(self):
        registry = ColumnRegistry.from_columns(
            ["pressure", "pressure", "pressure_bar", "pressure"],
            ["bar", "Pa", "", "Pa"])
        self.assertEqual(registry.names(), [
            "pressure_bar_2", "pressure_pa", "pressure_bar", "pressure_pa_2"
        ])
        self.assertEqual(registry.get("pressure_pa_2").source_name,
                         "pressure")
        with self.assertRaisesRegex(ValueError, "Ambiguous variable"):
            registry.resolve_reference("pressure")
        self.assertEqual(registry.resolve_reference("pressure [bar]"),
                         "pressure_bar_2")
        self.assertEqual(registry.resolve_reference("pressure_pa"),
                         "pressure_pa")

    def test_collision_resolution_independent_of_distinct_unit_order(self):
        first = ColumnRegistry.from_columns(["p", "p"], ["Pa", "bar"])
        second = ColumnRegistry.from_columns(["p", "p"], ["bar", "Pa"])
        self.assertEqual(set(first.names()), set(second.names()))
        self.assertEqual(set(first.names()), {"p_bar", "p_pa"})

    def test_sanitize_units(self):
        self.assertEqual(unit_suffix("kg/s"), "kg_s")
        self.assertEqual(unit_suffix("m^3"), "m3")
        self.assertEqual(unit_suffix("%"), "percent")
        self.assertEqual(unit_suffix("°C"), "degc")
        self.assertEqual(unit_suffix("Pa"), "pa")
        self.assertEqual(unit_suffix(""), "unit")

    def test_rename_to_existing_name_does_not_overwrite(self):
        registry = ColumnRegistry.from_columns(["p", "q"], ["Pa", "bar"])
        result = registry.rename("q", "p")
        self.assertEqual(result.internal_name, "p_bar")
        self.assertEqual(result.source_name, "p")
        self.assertEqual(registry.get("p").unit, "Pa")
        self.assertEqual(registry.get("p_bar").unit, "bar")
        registry.remove("p_bar")
        self.assertIsNone(registry.get("p_bar"))

    def test_edit_unit_of_duplicated_name_stays_disambiguated(self):
        registry = ColumnRegistry.from_columns(
            ["pressure", "pressure"], ["bar", "Pa"])
        renamed = registry.rename("pressure_bar", "pressure", "kPa")
        self.assertEqual(renamed.internal_name, "pressure_kpa")
        self.assertEqual(renamed.unit, "kPa")
        self.assertEqual(registry.get("pressure_pa").unit, "Pa")

    def test_csv_units_and_duplicate_names_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "data.csv"
            saved = Path(directory) / "saved.csv"
            original.write_text(
                "time [s],pressure [bar],pressure [Pa]\n0,2,200000\n",
                encoding="utf-8")
            frame, registry = read_csv(original)
            self.assertEqual(list(frame.columns),
                             ["time", "pressure_bar", "pressure_pa"])
            write_csv(saved, frame, registry)
            self.assertEqual(saved.read_text(),
                             "time[s],pressure[bar],pressure[Pa]\n0,2,200000\n")
            reloaded, second = read_csv(saved)
            pd.testing.assert_frame_equal(reloaded, frame)
            self.assertEqual(second.units(), registry.units())

    def test_empty_column_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.tsv"
            path.write_text("time[s]\t[K]\n1\t2\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "empty column name"):
                read_tsv(path)


if __name__ == "__main__":
    unittest.main()
