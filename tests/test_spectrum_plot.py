"""Headless tests of the Spectrum tab's rendering and signal selection."""

import ast
from pathlib import Path
import unittest

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

from csv_plotter_fft import (
    amplitude_spectrum, limit_spectrum_frequencies, select_time_interval,
    spectrum_decibels,
)
from csv_plotter_units import ColumnRegistry


SOURCE = Path(__file__).resolve().parents[1] / "csv_plotter.py"


def load_functions():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {"on_notebook_switch_page", "spectrum_signal_values",
             "spectrum_axis_label", "redraw_spectrum",
             "on_spectrum_setting_changed", "on_spectrum_frequency_apply"}
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    return compile(module, str(SOURCE), "exec")


class Label:
    @staticmethod
    def set_text(label, message):
        label.text = message


class Entry:
    @staticmethod
    def get_text(entry):
        return entry.text


class DropDown:
    @staticmethod
    def get_selected(dropdown):
        return dropdown.selected


class Notebook:
    @staticmethod
    def get_current_page(notebook):
        return notebook.page


class Gtk:
    Label = Label
    Entry = Entry
    DropDown = DropDown
    Notebook = Notebook


class Canvas:
    def __init__(self):
        self.draw_calls = 0

    @staticmethod
    def draw(canvas):
        canvas.draw_calls += 1


class SpectrumPlotTests(unittest.TestCase):
    def setUp(self):
        count = 400
        timestamps = 10000.0 + np.arange(count, dtype=float)
        phases = np.arange(count, dtype=float) / count
        frame = pd.DataFrame({
            "time": timestamps,
            "pressure": 11.0 + 2.5 * np.sin(2 * np.pi * 20 * phases),
            "level": 58.0 + 0.75 * np.cos(2 * np.pi * 40 * phases),
        })
        self.registry = ColumnRegistry.from_columns(
            list(frame.columns), ["s", "bar", "%"])
        self.original = frame.copy(deep=True)
        source_figure = Figure()
        time_left = source_figure.add_subplot(111)
        time_right = time_left.twinx()
        time_left.plot(timestamps, frame["pressure"], label="pressure")
        time_right.plot(timestamps, frame["level"], label="level")
        spectrum_figure = Figure()
        spectrum_left = spectrum_figure.add_subplot(111)
        spectrum_right = spectrum_left.twinx()
        self.canvas = Canvas()
        self.status = type("Status", (), {"text": ""})()
        self.state = {
            "np": np,
            "spectrum_settings": {
                "window": "hann", "detrend": "mean", "scale": "linear",
                "time_range": "full", "frequency_min": 0.0,
                "frequency_max": None,
            },
            "select_time_interval": select_time_interval,
            "limit_spectrum_frequencies": limit_spectrum_frequencies,
            "spectrum_decibels": spectrum_decibels,
            "spectrum_min_entry": type("EntryState", (), {"text": "0"})(),
            "spectrum_max_entry": type("EntryState", (), {"text": ""})(),
            "plot_notebook": None,
            "Gtk": Gtk,
            "Axes": Axes,
            "Line2D": Line2D,
            "FigureCanvas": Canvas,
            "FONTSIZE": 16,
            "amplitude_spectrum": amplitude_spectrum,
            "data_frame": frame,
            "column_registry": self.registry,
            "hdf5_named_value_by_display_name": {},
            "selector_unit": lambda name: self.registry.get(name).unit,
            "x_data": frame["time"],
            "axes_left": time_left,
            "axes_right": time_right,
            "spectrum_axes_left": spectrum_left,
            "spectrum_axes_right": spectrum_right,
            "spectrum_canvas": self.canvas,
            "spectrum_status": self.status,
            "styles": {"pressure": "solid", "level": "dashed"},
            "colors": {"pressure": "red", "level": "blue"},
            "spectrum_page_index": 1,
        }
        exec(load_functions(), self.state)

    def test_selected_signals_render_on_their_respective_axes(self):
        self.state["redraw_spectrum"]()
        left = self.state["spectrum_axes_left"]
        right = self.state["spectrum_axes_right"]
        self.assertEqual(len(left.lines), 1)
        self.assertEqual(len(right.lines), 1)
        self.assertEqual(left.lines[0].get_label(), "pressure")
        self.assertEqual(right.lines[0].get_label(), "level")
        self.assertEqual(left.lines[0].get_color(), "red")
        self.assertEqual(right.lines[0].get_linestyle(), "--")
        self.assertEqual(left.get_xlabel(), "Frequency [Hz]")
        self.assertEqual(left.get_ylabel(), "Amplitude [bar]")
        self.assertEqual(right.get_ylabel(), "Amplitude [%]")
        self.assertAlmostEqual(left.lines[0].get_xdata()[20], 0.05)
        self.assertAlmostEqual(left.lines[0].get_ydata()[20], 2.5, places=9)
        self.assertAlmostEqual(right.lines[0].get_ydata()[40], 0.75, places=9)
        self.assertIn("Hann", self.status.text)
        self.assertEqual(self.canvas.draw_calls, 1)
        pd.testing.assert_frame_equal(self.state["data_frame"], self.original)
        self.assertEqual(len(self.state["axes_left"].lines), 1)

    def test_refresh_replaces_lines_and_observes_selection(self):
        self.state["redraw_spectrum"]()
        self.state["axes_left"].lines[0].remove()
        self.state["redraw_spectrum"]()
        self.assertFalse(self.state["spectrum_axes_left"].lines)
        self.assertEqual(len(self.state["spectrum_axes_right"].lines), 1)
        self.assertEqual(self.canvas.draw_calls, 2)

    def test_nonuniform_x_axis_is_reported_without_crashing(self):
        changed = self.state["data_frame"].copy()
        changed.loc[8, "time"] += 0.5
        self.state["x_data"] = changed["time"]
        self.state["redraw_spectrum"]()
        self.assertFalse(self.state["spectrum_axes_left"].lines)
        self.assertFalse(self.state["spectrum_axes_right"].lines)
        self.assertIn("not uniformly spaced", self.status.text)

    def test_invalid_signal_does_not_hide_a_valid_signal(self):
        self.state["data_frame"].loc[100, "level"] = np.nan
        self.state["redraw_spectrum"]()
        self.assertEqual(len(self.state["spectrum_axes_left"].lines), 1)
        self.assertFalse(self.state["spectrum_axes_right"].lines)
        self.assertIn("level: signal contains missing samples", self.status.text)

    def test_unrecognized_time_units_are_rejected(self):
        self.state["selector_unit"] = lambda name: "ms" if name == "time" else "bar"
        self.state["redraw_spectrum"]()
        self.assertFalse(self.state["spectrum_axes_left"].lines)
        self.assertIn("select time in seconds", self.status.text)

    def test_unlabeled_time_axis_is_explicitly_assumed_seconds(self):
        self.state["selector_unit"] = lambda name: "" if name == "time" else "bar"
        self.state["redraw_spectrum"]()
        self.assertEqual(len(self.state["spectrum_axes_left"].lines), 1)
        self.assertIn("assumed to be in seconds", self.status.text)

    def test_no_selection_reports_instruction(self):
        self.state["axes_left"].lines[0].remove()
        self.state["axes_right"].lines[0].remove()
        self.state["redraw_spectrum"]()
        self.assertIn("Select one or more Y signals", self.status.text)

    def test_page_switch_triggers_only_spectrum_page(self):
        calls = []
        self.state["redraw_spectrum"] = lambda: calls.append(True)
        self.state["on_notebook_switch_page"](None, None, 0)
        self.state["on_notebook_switch_page"](None, None, 2)
        self.assertFalse(calls)
        self.state["on_notebook_switch_page"](None, None, 1)
        self.assertEqual(len(calls), 1)

    def test_window_and_detrend_controls_change_fft(self):
        self.state["spectrum_settings"]["window"] = "rectangular"
        self.state["spectrum_settings"]["detrend"] = "none"
        self.state["redraw_spectrum"]()
        left = self.state["spectrum_axes_left"]
        self.assertAlmostEqual(left.lines[0].get_ydata()[0], 11.0,
                               places=9)
        self.assertIn("Rectangular", self.status.text)
        self.assertIn("mean retained", self.status.text)
        self.assertEqual(self.canvas.draw_calls, 1)

    def test_db_scale_is_relative_to_each_signal_peak(self):
        self.state["spectrum_settings"]["scale"] = "db"
        self.state["redraw_spectrum"]()
        left = self.state["spectrum_axes_left"]
        right = self.state["spectrum_axes_right"]
        self.assertAlmostEqual(left.lines[0].get_ydata()[20], 0.0, places=8)
        self.assertAlmostEqual(right.lines[0].get_ydata()[40], 0.0, places=8)
        self.assertTrue(np.isfinite(left.lines[0].get_ydata()).all())
        self.assertEqual(left.get_ylabel(), "Relative amplitude [dB re peak]")
        self.assertIn("-120 dB", self.status.text)

    def test_visible_plot_time_interval(self):
        self.state["spectrum_settings"]["time_range"] = "visible"
        self.state["axes_left"].set_xlim(10000.0, 10199.0)
        self.state["redraw_spectrum"]()
        left = self.state["spectrum_axes_left"]
        self.assertEqual(len(left.lines[0].get_xdata()), 101)
        self.assertAlmostEqual(left.lines[0].get_xdata()[1], 1 / 200)
        self.assertIn("Plot visible time interval", self.status.text)
        pd.testing.assert_frame_equal(self.state["data_frame"], self.original)

    def test_visible_plot_range_with_few_samples(self):
        self.state["spectrum_settings"]["time_range"] = "visible"
        self.state["axes_left"].set_xlim(10000.0, 10001.0)
        self.state["redraw_spectrum"]()
        self.assertFalse(self.state["spectrum_axes_left"].lines)
        self.assertIn("fewer than three", self.status.text)

    def test_frequency_limits_crop_display_not_original_data(self):
        self.state["spectrum_settings"]["frequency_min"] = 0.045
        self.state["spectrum_settings"]["frequency_max"] = 0.055
        self.state["redraw_spectrum"]()
        frequency = self.state["spectrum_axes_left"].lines[0].get_xdata()
        self.assertTrue((frequency >= 0.045).all())
        self.assertTrue((frequency <= 0.055).all())
        self.assertAlmostEqual(frequency[2], 0.05)
        pd.testing.assert_frame_equal(self.state["data_frame"], self.original)

    def test_invalid_frequency_range_does_not_replace_prior_settings(self):
        self.state["spectrum_min_entry"].text = "0.1"
        self.state["spectrum_max_entry"].text = "0.05"
        self.state["on_spectrum_frequency_apply"](None)
        self.assertIn("Invalid frequency range", self.status.text)
        self.assertEqual(self.state["spectrum_settings"]["frequency_min"], 0)
        self.assertIsNone(self.state["spectrum_settings"]["frequency_max"])
        self.assertEqual(self.canvas.draw_calls, 0)

    def test_frequency_apply_refreshes_current_spectrum(self):
        self.state["plot_notebook"] = type("NotebookState", (),
                                           {"page": 1})()
        self.state["spectrum_min_entry"].text = "0.04"
        self.state["spectrum_max_entry"].text = "0.06"
        self.state["on_spectrum_frequency_apply"](None)
        self.assertEqual(self.canvas.draw_calls, 1)
        self.assertAlmostEqual(self.state["spectrum_settings"]["frequency_max"], 0.06)
        self.assertEqual(len(self.state["spectrum_axes_left"].lines[0].get_xdata()), 9)

    def test_dropdown_changes_live_spectrum(self):
        self.state["plot_notebook"] = type("NotebookState", (),
                                           {"page": 1})()
        menu = type("Menu", (), {"spectrum_setting": "scale",
                                 "spectrum_values": ("linear", "db"),
                                 "selected": 1})()
        self.state["on_spectrum_setting_changed"](menu)
        self.assertEqual(self.state["spectrum_settings"]["scale"], "db")
        self.assertEqual(self.canvas.draw_calls, 1)

    def test_spectrum_page_is_created_in_gtk_notebook(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        activation = next(node for node in tree.body
                          if isinstance(node, ast.FunctionDef)
                          and node.name == "on_have_filename_ready")
        strings = [node.value for node in ast.walk(activation)
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        self.assertIn("Spectrum", strings)
        self.assertIn("switch-page", strings)
        self.assertIn("Visible Plot range", strings)
        self.assertIn("Apply Hz", strings)
        self.assertIn("dB (relative to peak)", strings)


if __name__ == "__main__":
    unittest.main()
