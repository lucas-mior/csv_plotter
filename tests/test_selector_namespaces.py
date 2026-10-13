"""Namespace selector tests that do not require a graphical GTK session."""

import ast
import itertools
import keyword
from pathlib import Path
import re
import unittest

import numpy as np
import pandas as pd
from csv_plotter_units import ColumnRegistry, split_tsv_header


class Widget:
    @staticmethod
    def set_tooltip_text(widget, text):
        widget.tooltip = text

    def __init__(self):
        self.parent = None
        self.children = []

    @staticmethod
    def get_parent(widget):
        return widget.parent

    @staticmethod
    def get_first_child(widget):
        return widget.children[0] if widget.children else None

    @staticmethod
    def get_next_sibling(widget):
        siblings = widget.parent.children
        index = siblings.index(widget) + 1
        return siblings[index] if index < len(siblings) else None


class Box(Widget):
    def __init__(self, orientation=None):
        super().__init__()

    @staticmethod
    def append(parent, child):
        assert child.parent is None
        parent.children.append(child)
        child.parent = parent

    @staticmethod
    def remove(parent, child):
        parent.children.remove(child)
        child.parent = None


class Expander(Widget):
    def __init__(self, label):
        super().__init__()
        self.label = label

    @staticmethod
    def set_expanded(expander, expanded):
        expander.expanded = expanded

    @staticmethod
    def set_child(expander, child):
        Box.append(expander, child)

    @staticmethod
    def get_label(expander):
        return expander.label

    @staticmethod
    def get_child(expander):
        return expander.children[0]


class ScrolledWindow:
    @staticmethod
    def set_child(scroll, child):
        scroll.child = child

    @staticmethod
    def get_child(scroll):
        return scroll.child


class Viewport:
    @staticmethod
    def get_child(viewport):
        return viewport.child


class EditableLabel:
    @staticmethod
    def set_text(label, text):
        label.text = text

    @staticmethod
    def get_editing(label):
        return False

    @staticmethod
    def get_text(label):
        return label.text


class Entry:
    @staticmethod
    def get_buffer(entry):
        return entry

    @staticmethod
    def set_text(entry, text):
        entry.text = text


class EntryBuffer:
    @staticmethod
    def get_text(buffer):
        return buffer.text


class CheckButton:
    @staticmethod
    def get_active(button):
        return button.active


class Axes:
    @staticmethod
    def set_xlabel(axes, label, fontsize):
        axes.xlabel = label


class Gtk:
    Box = Box
    Widget = Widget
    Expander = Expander
    ScrolledWindow = ScrolledWindow
    Viewport = Viewport
    EditableLabel = EditableLabel
    Entry = Entry
    EntryBuffer = EntryBuffer
    CheckButton = CheckButton
    Button = Widget
    Orientation = type('Orientation', (), {'VERTICAL': 'vertical'})


class Item(Widget):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.y_button_left = type('Button', (), {'active': False})()
        self.y_button_right = type('Button', (), {'active': False})()


def load_selector_functions():
    source = Path(__file__).resolve().parents[1] / 'csv_plotter.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    functions = {
        'selector_parent_box', 'reconfigure_plots_and_buttons',
        'on_entry_activate', 'on_item_label_notify_editing',
        'on_delete_button_click', 'add_expression_name',
    }
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in functions]
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    code = compile(module, str(source), 'exec')
    return code


SELECTOR_FUNCTIONS = load_selector_functions()


class SelectorNamespaceTests(unittest.TestCase):
    def setUp(self):
        self.axes_left = type('Axis', (), {})()
        self.axes_right = type('Axis', (), {})()
        self.state = {
            'Gtk': Gtk,
            'Axes': Axes,
            'pd': pd,
            'np': np,
            're': re,
            'keyword': keyword,
            'DataFrame': pd.DataFrame,
            'FONTSIZE': 22,
            'colors_cycle': itertools.cycle(['red', 'blue', 'green']),
            'styles': {},
            'colors': {},
            'column_registry': ColumnRegistry(),
            'split_tsv_header': split_tsv_header,
            'display_unit': lambda unit: f' [{unit}]' if unit else '',
            'pre_plots': [],
            'hdf5_named_values': [],
            'axes_left': self.axes_left,
            'axes_right': self.axes_right,
            'metadata_name': lambda name: False,
            'clean_plotted_get_list': lambda: ([], []),
            'configure_y_axis_labels_and_ticks': lambda: None,
            'put_legends': lambda: None,
            'add_plot': lambda name, axis: None,
            'remove_plot': lambda name, axis: None,
            'redraw_plots': lambda **kwargs: None,
        }
        exec(SELECTOR_FUNCTIONS, self.state)

        def add_buttons(name, parent, left=False, right=False):
            item = Item(name)
            item.y_button_left.active = left
            item.y_button_right.active = right
            Box.append(parent, item)
            return item

        self.state['add_buttons'] = add_buttons

    def configure(self, names):
        self.state['data_frame'] = pd.DataFrame({
            name: [1.0, 2.0] for name in names
        })
        self.state['x_data'] = self.state['data_frame'].iloc[:, 0]
        self.state['column_registry'] = ColumnRegistry.from_columns(
            names, [''] * len(names))
        scroll = type('Scroll', (), {})()
        self.state['reconfigure_plots_and_buttons'](scroll)
        return scroll.child

    def test_plain_tsv_headers_are_flat(self):
        from csv_plotter_units import split_tsv_header

        headers = ('time[s] Vwt[m^3] p[bar] ar Vsd[m^3] Q[W] '
                   'qf[kg/s] qs[kg/s] tf[K] pressure[bar] level[m] '
                   'level_percent[%] q_blower[kg/s] qw[kg/s]').split()
        names = [split_tsv_header(header)[0] for header in headers]
        root = self.configure(names)
        self.assertEqual([child.name for child in root.children], names)
        self.assertFalse(any(isinstance(child, Expander)
                             for child in root.children))

    def test_mixed_names_only_group_dotted_columns(self):
        root = self.configure(['plant.pressure', 'time', 'plant.flow',
                               'pressure', 'controller.input.value'])
        self.assertEqual([child.label if isinstance(child, Expander)
                          else child.name for child in root.children],
                         ['plant', 'time', 'pressure', 'controller'])
        self.assertEqual([item.name for item in root.children[0].children[0].children],
                         ['plant.pressure', 'plant.flow'])
        self.assertEqual([item.name for item in root.children[3].children[0].children],
                         ['controller.input.value'])

    def test_expressions_reuse_groups_and_plain_expressions_remain_flat(self):
        root = self.configure(['time', 'plant.flow'])
        entry = type('EntryObject', (), {})()
        entry.text = 'time * 2'
        entry.selection_scroll = type('Scroll', (), {})()
        entry.selection_scroll.child = type('ViewportObject', (), {'child': root})()
        self.state['on_entry_activate'](entry)
        self.assertEqual(root.children[-1].name, 'time * 2')
        self.assertEqual(entry.text, '')

        self.state['add_buttons']('plant.new',
            self.state['selector_parent_box'](root, 'plant.new'))
        self.assertEqual([child.name for child in root.children[1].children[0].children],
                         ['plant.flow', 'plant.new'])
        self.assertEqual(len([child for child in root.children
                              if isinstance(child, Expander)]), 1)

    def test_expression_evaluates_unit_disambiguated_names(self):
        names = ['time', 'pressure_bar', 'pressure_pa']
        root = self.configure(names)
        self.state['column_registry'] = ColumnRegistry.from_columns(
            ['time', 'pressure', 'pressure'], ['s', 'bar', 'Pa'])
        entry = type('EntryObject', (), {})()
        entry.text = 'pressure_bar + pressure_pa'
        entry.selection_scroll = type('Scroll', (), {})()
        entry.selection_scroll.child = type('ViewportObject', (),
                                              {'child': root})()
        self.state['on_entry_activate'](entry)
        self.assertEqual(list(self.state['data_frame'][
            'pressure_bar + pressure_pa']), [2.0, 4.0])

        entry.text = '`pressure [bar]` * 2 + `pressure [Pa]`'
        self.state['on_entry_activate'](entry)
        self.assertEqual(list(self.state['data_frame'][
            '`pressure [bar]` * 2 + `pressure [Pa]`']), [3.0, 6.0])

    def test_rename_moves_items_and_removes_empty_groups(self):
        root = self.configure(['time', 'plant.flow'])
        plant_item = root.children[1].children[0].children[0]
        label = type('Label', (), {'parent': plant_item,
                                   'text': 'flow'})()
        self.state['on_item_label_notify_editing'](label, False)
        self.assertEqual([child.name for child in root.children],
                         ['time', 'flow'])
        self.assertNotIn('plant.flow', self.state['data_frame'].columns)
        self.assertIn('flow', self.state['data_frame'].columns)

        label.text = 'plant.flow'
        self.state['on_item_label_notify_editing'](label, False)
        self.assertEqual([child.label if isinstance(child, Expander)
                          else child.name for child in root.children],
                         ['time', 'plant'])

    def test_editing_display_name_with_unit_updates_metadata(self):
        root = self.configure(['time', 'pressure_bar', 'pressure_pa'])
        self.state['column_registry'] = ColumnRegistry.from_columns(
            ['time', 'pressure', 'pressure'], ['s', 'bar', 'Pa'])
        item = root.children[1]
        label = type('Label', (), {'parent': item, 'text': 'Q[kg/s]'})()
        self.state['on_item_label_notify_editing'](label, False)
        self.assertEqual(item.name, 'Q')
        self.assertEqual(label.text, 'Q')
        self.assertEqual(self.state['column_registry'].get('Q').unit, 'kg/s')
        self.assertIn('Q', self.state['data_frame'].columns)
        self.assertIn('pressure_pa', self.state['data_frame'].columns)
        self.assertNotIn('pressure_bar', self.state['data_frame'].columns)

    def test_delete_last_dotted_column_removes_empty_expander(self):
        root = self.configure(['time', 'plant.flow'])
        item = root.children[1].children[0].children[0]
        button = type('DeleteButton', (), {'parent': item})()
        self.state['on_delete_button_click'](button)
        self.assertEqual([child.name for child in root.children], ['time'])
        self.assertEqual(list(self.state['data_frame'].columns), ['time'])


if __name__ == '__main__':
    unittest.main()
