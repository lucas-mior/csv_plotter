"""Headless tests of the Spectrum tab's rendering and signal selection."""

import ast
from pathlib import Path
import unittest

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

from csv_plotter_fft import amplitude_spectrum
from csv_plotter_units import ColumnRegistry


SOURCE = Path(__file__).resolve().parents[1] / "csv_plotter.py"


def load_functions():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {"on_notebook_switch_page", "spectrum_signal_values",
             "spectrum_axis_label", "redraw_spectrum"}
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    return compile(module, str(SOURCE), "exec")


class Label:
    @staticmethod
    def set_text(label, message):
        label.text = message


class Gtk:
    Label = Label


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

    def test_spectrum_page_is_created_in_gtk_notebook(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        activation = next(node for node in tree.body
                          if isinstance(node, ast.FunctionDef)
                          and node.name == "on_have_filename_ready")
        strings = [node.value for node in ast.walk(activation)
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        self.assertIn("Spectrum", strings)
        self.assertIn("switch-page", strings)


if __name__ == "__main__":
    unittest.main()
