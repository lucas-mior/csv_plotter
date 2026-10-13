"""Cystemas /colors compatibility, plotting preferences, and round trips."""

import ast
from contextlib import redirect_stderr
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from io import StringIO
import itertools
from pathlib import Path
import tempfile
import unittest

import h5py
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd

from csv_plotter_units import ColumnRegistry, read_csv, read_tsv, write_csv, write_tsv
from test_hdf5_columns import load_hdf5_functions


class ColorsHdf5Tests(unittest.TestCase):
    def create_file(self, path, colors=None):
        with h5py.File(path, 'w') as handle:
            handle['data'] = np.array([[0, 1, 2, 3, 4],
                                       [1, 2, 3, 4, 5]], dtype=float)
            handle['names'] = np.array([
                b'time', b'pressure', b'pressure', b'plant.flow',
                b'plant.temperature'])
            handle['units'] = np.array([
                b's', b'bar', b'Pa', b'kg/s', b'K'])
            if colors is not None:
                handle['colors'] = np.asarray(colors)

    def state_for(self, path):
        state = {
            'filename': str(path),
            'h5py': h5py,
            'np': np,
            'pd': pd,
            'DataFrame': pd.DataFrame,
            'ColumnRegistry': ColumnRegistry,
            'read_csv': read_csv,
            'read_tsv': read_tsv,
            'write_csv': write_csv,
            'write_tsv': write_tsv,
            'hdf5_named_values': [],
            'hdf5_named_value_by_display_name': {},
            'hdf5_simulation_metadata': [],
            'hdf5_fit_metadata': [],
            'hdf5_fit_inputs': [],
            'HDF5_EXTENSIONS': ('.h5', '.hdf5'),
            'os': __import__('os'),
            'sys': __import__('sys'),
            'mcolors': mcolors,
        }
        exec(load_hdf5_functions(), state)
        path_source = Path(__file__).resolve().parents[1] / 'csv_plotter.py'
        tree = ast.parse(path_source.read_text(encoding='utf-8'))
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in ('configured_plot_color',
                                   'on_color_button_click', 'add_plot')]
        exec(compile(ast.fix_missing_locations(
            ast.Module(body=nodes, type_ignores=[])), str(path_source),
            'exec'), state)
        return state

    def test_load_colors_and_save_same_order_even_with_duplicate_names(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / 'data.h5'
            self.create_file(original, [b'', b'red', b'#00ff00', b'blue', b''])
            state = self.state_for(original)
            state['reload_file_contents']()
            names = list(state['data_frame'].columns)
            self.assertEqual(names, [
                'time', 'pressure_bar', 'pressure_pa',
                'plant.flow', 'plant.temperature'])
            self.assertEqual(state['column_registry'].colors(names), [
                '', 'red', '#00ff00', 'blue', ''])
            self.assertEqual(state['configured_plot_color'](
                'pressure_bar', 'purple'), 'red')
            self.assertEqual(state['configured_plot_color'](
                'pressure_pa', 'purple'), '#00ff00')
            self.assertEqual(state['configured_plot_color'](
                'plant.temperature', 'purple'), 'purple')
            state['on_save_button_clicked'](None)
            saved = Path(directory) / 'data_new.h5'
            with h5py.File(saved, 'r') as handle:
                self.assertEqual([x.decode() for x in handle['colors'][()]],
                                 ['', 'red', '#00ff00', 'blue', ''])
                self.assertEqual([x.decode() for x in handle['names'][()]],
                                 ['time', 'pressure', 'pressure',
                                  'plant.flow', 'plant.temperature'])
            reloaded = self.state_for(saved)
            reloaded['reload_file_contents']()
            self.assertEqual(reloaded['column_registry'].colors(
                reloaded['data_frame'].columns),
                state['column_registry'].colors(names))

    def test_legacy_file_without_colors_writes_empty_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / 'old.h5'
            self.create_file(original)
            state = self.state_for(original)
            state['reload_file_contents']()
            self.assertEqual(state['column_registry'].colors(
                state['data_frame'].columns), [''] * 5)
            state['on_save_button_clicked'](None)
            with h5py.File(Path(directory) / 'old_new.h5', 'r') as handle:
                self.assertEqual([x.decode() for x in handle['colors'][()]],
                                 [''] * 5)

    def test_actual_matplotlib_curve_uses_hdf5_color(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plot.h5'
            self.create_file(path, [b'', b'#112233', b'', b'', b''])
            state = self.state_for(path)
            state['reload_file_contents']()
            state['Axes'] = Axes
            state['styles'] = {'pressure_bar': 'solid'}
            state['colors'] = {'pressure_bar':
                               state['configured_plot_color'](
                                   'pressure_bar', 'tab:blue')}
            state['hdf5_named_value_by_display_name'] = {}
            figure = Figure()
            axes = figure.add_subplot(111)
            state['add_plot']('pressure_bar', axes)
            self.assertEqual(axes.get_lines()[0].get_color(), '#112233')
            self.assertEqual(axes.get_lines()[0].get_label(), 'pressure_bar')

    def test_invalid_color_preserved_but_ignored_in_plotting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'invalid.h5'
            self.create_file(path, [b'', b'badcolor', b'cyan', b'', b''])
            state = self.state_for(path)
            state['reload_file_contents']()
            self.assertEqual(state['configured_plot_color'](
                'pressure_bar', '#abcabc'), '#abcabc')
            state['on_save_button_clicked'](None)
            with h5py.File(Path(directory) / 'invalid_new.h5', 'r') as handle:
                self.assertEqual(handle['colors'][1], b'badcolor')

    def test_renames_deletes_and_added_columns_preserve_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'modified.h5'
            self.create_file(path, [b'', b'red', b'blue', b'green', b''])
            state = self.state_for(path)
            state['reload_file_contents']()
            registry = state['column_registry']
            info = registry.rename('pressure_bar', 'overpressure')
            state['data_frame'].rename(
                columns={'pressure_bar': info.internal_name}, inplace=True)
            state['data_frame'].drop(columns='plant.flow', inplace=True)
            registry.remove('plant.flow')
            info = registry.add('derived')
            state['data_frame'][info.internal_name] = (
                state['data_frame']['pressure_pa'] * 2)
            state['on_save_button_clicked'](None)
            with h5py.File(Path(directory) / 'modified_new.h5', 'r') as handle:
                self.assertEqual([x.decode() for x in handle['names'][()]],
                                 ['time', 'overpressure', 'pressure',
                                  'plant.temperature', 'derived'])
                self.assertEqual([x.decode() for x in handle['colors'][()]],
                                 ['', 'red', 'blue', '', ''])

    def test_color_button_updates_saved_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'manual.h5'
            self.create_file(path, [b'', b'red', b'', b'', b''])
            state = self.state_for(path)
            state['reload_file_contents']()
            state['colors'] = {'pressure_bar': 'red'}
            state['colors_cycle'] = itertools.cycle(['#abcdef'])
            state['axes_left'] = object()
            state['axes_right'] = object()
            state['Axes'] = type('Axes', (), {'get_lines': staticmethod(
                lambda axes: [])})
            state['reset_plot'] = lambda *args: None
            state['Gtk'] = type('Gtk', (), {'Button': type('Button', (), {
                'get_parent': staticmethod(lambda button: button.item)
            })})
            button = type('ButtonInstance', (), {'item': type('Item', (), {
                'name': 'pressure_bar'})()})()
            state['on_color_button_click'](button)
            self.assertEqual(state['column_registry'].get(
                'pressure_bar').color, '#abcdef')
            state['on_save_button_clicked'](None)
            with h5py.File(Path(directory) / 'manual_new.h5', 'r') as handle:
                self.assertEqual(handle['colors'][1], b'#abcdef')

    def test_wrong_colors_length_or_dimensions_rejected(self):
        for colors in ([b'red'], np.full((5, 1), b'r', dtype='S1')):
            with self.subTest(shape=np.asarray(colors).shape):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / 'bad.h5'
                    self.create_file(path, colors)
                    state = self.state_for(path)
                    with redirect_stderr(StringIO()), \
                            self.assertRaises(SystemExit):
                        state['reload_file_contents']()


if __name__ == '__main__':
    unittest.main()
