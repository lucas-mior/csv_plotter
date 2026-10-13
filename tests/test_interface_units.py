"""Headless checks for the actual selector widget construction."""

import ast
from pathlib import Path
import unittest

import pandas as pd

from csv_plotter_units import ColumnRegistry


class Widget:
    def __init__(self, **kwargs):
        self.children = []
        self.attributes = kwargs
        self.text = kwargs.get("label", "")

    @staticmethod
    def set_tooltip_text(widget, text):
        widget.tooltip = text

    @staticmethod
    def set_hexpand(widget, flag):
        widget.hexpand = flag

    @staticmethod
    def set_halign(widget, align):
        widget.halign = align


class Box(Widget):
    @staticmethod
    def append(widget, child):
        widget.children.append(child)


class CheckButton(Widget):
    @staticmethod
    def set_active(widget, active):
        widget.active = active

    @staticmethod
    def connect(widget, *args):
        pass


class Label(Widget):
    @staticmethod
    def set_text(widget, text):
        widget.text = text


class EditableLabel(Label):
    @staticmethod
    def new(label):
        return EditableLabel(label=label)

    @staticmethod
    def connect(widget, *args):
        pass


class Button(Widget):
    @staticmethod
    def new_from_icon_name(icon):
        return Button()

    @staticmethod
    def connect(widget, *args):
        pass

    @staticmethod
    def set_tooltip_text(widget, text):
        widget.tooltip = text

    @staticmethod
    def set_sensitive(widget, active):
        widget.sensitive = active

    @staticmethod
    def set_margin_end(widget, value):
        pass

    @staticmethod
    def set_margin_start(widget, value):
        pass


class Gtk:
    Widget = Widget
    Box = Box
    CheckButton = CheckButton
    Label = Label
    EditableLabel = EditableLabel
    Button = Button
    Orientation = type("Orientation", (), {"HORIZONTAL": "horizontal"})
    Align = type("Align", (), {"END": "end"})


def load_functions():
    source_path = Path(__file__).resolve().parents[1] / "csv_plotter.py"
    source = ast.parse(source_path.read_text(encoding="utf-8"))
    names = {"selector_unit", "display_unit", "add_buttons"}
    functions = [node for node in source.body if isinstance(node, ast.FunctionDef)
                 and node.name in names]
    return compile(ast.fix_missing_locations(
        ast.Module(body=functions, type_ignores=[])), str(source_path), "exec")


class InterfaceUnitTests(unittest.TestCase):
    def setUp(self):
        registry = ColumnRegistry.from_columns(
            ["time", "pressure", "pressure", "plant.p"],
            ["s", "bar", "Pa", "m^3"])
        state = {
            "Gtk": Gtk,
            "column_registry": registry,
            "hdf5_named_value_by_display_name": {},
            "metadata_name": lambda name: False,
            "x_button_group": None,
            "axes_left": object(),
            "axes_right": object(),
            "on_x_button_toggled": lambda button: None,
            "on_y_button_toggled": lambda button: None,
            "on_item_label_notify_editing": lambda label, editing: None,
            "on_style_button_click": lambda button: None,
            "on_color_button_click": lambda button: None,
            "on_delete_button_click": lambda button: None,
        }
        exec(load_functions(), state)
        self.state = state

    def test_displays_units_beside_names_and_keeps_internal_ids(self):
        root = Box()
        for name in self.state["column_registry"].names():
            self.state["add_buttons"](name, root)

        for item, name, source, unit in zip(
                root.children,
                ["time", "pressure_bar", "pressure_pa", "plant.p"],
                ["time", "pressure", "pressure", "plant.p"],
                [" [s]", " [bar]", " [Pa]", " [m^3]"]):
            self.assertEqual(item.name, name)
            self.assertEqual(item.children[3].text, source)
            self.assertEqual(item.children[4].text, unit)
            self.assertEqual(item.children[3].tooltip,
                             f"Expression name: {name}")

    def test_metadata_units_visible_too(self):
        self.state["hdf5_named_value_by_display_name"] = {
            "parameters.k": {"name": "k", "unit": "1/s"},
        }
        self.state["metadata_name"] = lambda name: name == "parameters.k"
        container = Box()
        self.state["add_buttons"]("parameters.k", container)
        item = container.children[0]
        self.assertEqual(item.children[3].text, "k")
        self.assertEqual(item.children[4].text, " [1/s]")
        self.assertFalse(item.children[0].sensitive)

    def test_units_previously_bracketed_are_not_bracketed_twice(self):
        self.assertEqual(self.state["display_unit"]("[bar]"), " [bar]")


if __name__ == "__main__":
    unittest.main()
