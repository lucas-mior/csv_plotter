"""Headless checks for time-domain Y limits after navigation."""

import ast
import unittest
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D


def load_rescale_visible_y():
    source_path = Path(__file__).resolve().parents[1] / "csv_plotter.py"
    source = source_path.read_text()
    module = ast.parse(source)
    node = next(node for node in module.body
                if isinstance(node, ast.FunctionDef)
                and node.name == "rescale_visible_y")
    namespace = {"Axes": Axes, "Line2D": Line2D, "np": np}
    exec(compile(ast.Module(body=[node], type_ignores=[]),
                 str(source_path), "exec"), namespace)
    return namespace["rescale_visible_y"]


rescale_visible_y = load_rescale_visible_y()


class VisibleYLimitsTests(unittest.TestCase):
    def setUp(self):
        figure = Figure()
        self.left = figure.add_subplot(111)
        self.right = self.left.twinx()
        self.left.set_ymargin(0.02)
        self.right.set_ymargin(0.2)

    def test_each_axis_uses_only_values_in_visible_x_range(self):
        self.left.plot([0, 1, 2, 3, 4], [-1000, 10, 12, 11, 1000])
        self.right.plot([0, 1, 2, 3, 4], [-5000, 100, 120, 110, 5000])

        rescale_visible_y((self.left, self.right), (1, 3))

        left_min, left_max = self.left.get_ylim()
        right_min, right_max = self.right.get_ylim()
        self.assertLess(left_min, 10)
        self.assertGreater(left_max, 12)
        self.assertGreater(left_min, 0)
        self.assertLess(left_max, 20)
        self.assertLess(right_min, 100)
        self.assertGreater(right_max, 120)
        self.assertGreater(right_min, 50)
        self.assertLess(right_max, 150)

    def test_nonfinite_and_hidden_values_do_not_affect_limits(self):
        self.left.plot([0, 1, 2, 3], [np.nan, 4, 6, np.inf])
        hidden, = self.left.plot([1, 2], [-1000, 1000])
        hidden.set_visible(False)

        rescale_visible_y((self.left,), (0, 3))

        y_min, y_max = self.left.get_ylim()
        self.assertGreater(y_min, 0)
        self.assertLess(y_max, 10)

    def test_axis_without_samples_in_window_keeps_its_limits(self):
        self.left.plot([0, 1], [10, 20])
        self.left.set_ylim(-2, 2)

        rescale_visible_y((self.left,), (3, 4))

        self.assertEqual(self.left.get_ylim(), (-2, 2))


if __name__ == "__main__":
    unittest.main()
