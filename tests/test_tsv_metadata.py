"""Cystemas TSV column metadata parsing, plotting colors and round trips."""

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from csv_plotter_units import (
    read_tsv, split_tsv_header_metadata, write_tsv,
)
from test_hdf5_colors import ColorsHdf5Tests


class TsvMetadataTests(unittest.TestCase):
    def test_cystemas_metadata_and_duplicate_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.tsv"
            path.write_text(
                'time[s]\tQ [W]{color="red"; other="ignored"}'
                '\tQ [kW]{COLOR="#12ab34"}\tR{other="ignored"}\n'
                '0\t1\t2\t3\n1\t4\t5\t6\n', encoding="utf-8")
            frame, registry = read_tsv(path)
            self.assertEqual(list(frame.columns),
                             ["time", "Q_w", "Q_kw", "R"])
            self.assertEqual(registry.units(), {
                "time": "s", "Q_w": "W", "Q_kw": "kW", "R": ""})
            self.assertEqual(registry.colors(frame.columns),
                             ["", "red", "#12ab34", ""])
            self.assertEqual(registry.get("Q_w").display_label, "Q [W]")
            self.assertEqual(registry.get("Q_kw").display_label, "Q [kW]")

    def test_no_unit_and_spaces_before_metadata(self):
        self.assertEqual(split_tsv_header_metadata(
            'R  {color="cyan"}  '), ('R', '', 'cyan'))
        self.assertEqual(split_tsv_header_metadata(
            'flow [ kg/s ] { other = "ignored" ; color = "blue"; }'),
            ('flow', 'kg/s', 'blue'))
        self.assertEqual(split_tsv_header_metadata("plain [W]"),
                         ("plain", "W", ""))

    def test_save_reloads_colors_and_escapes_without_csv_quoting(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "source.tsv"
            saved = Path(directory) / "saved.tsv"
            original.write_text('time[s]\tQ [W]{color="blue"}\n0\t2\n',
                                encoding="utf-8")
            frame, registry = read_tsv(original)
            registry.get("Q").color = 'red;"blue\\test\nend'
            write_tsv(saved, frame, registry)
            self.assertEqual(saved.read_text().splitlines()[0],
                             'time [s]\tQ [W]'
                             '{color="red;\\"blue\\\\test\\nend"}')
            new_frame, new_registry = read_tsv(saved)
            pd.testing.assert_frame_equal(new_frame, frame)
            self.assertEqual(new_registry.colors(new_frame.columns),
                             ['', 'red;"blue\\test\nend'])

    def test_invalid_color_is_retained_but_not_used_for_plotting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'invalid.tsv'
            path.write_text('time[s]\tQ[W]{color="not-a-color"}\n0\t1\n',
                            encoding='utf-8')
            state = ColorsHdf5Tests().state_for(path)
            state['reload_file_contents']()
            self.assertEqual(state['column_registry'].get('Q').color,
                             'not-a-color')
            self.assertEqual(state['configured_plot_color']('Q', 'orange'),
                             'orange')

    def test_plot_uses_tsv_color_and_manual_change_is_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "curve.tsv"
            path.write_text(
                'time [s]\tQ [W]{color="#112233"}\n0\t2\n1\t3\n',
                encoding="utf-8")
            state = ColorsHdf5Tests().state_for(path)
            state['reload_file_contents']()
            self.assertEqual(state['configured_plot_color'](
                'Q', 'tab:blue'), '#112233')
            state['Axes'] = Axes
            state['styles'] = {'Q': 'solid'}
            state['colors'] = {
                'Q': state['configured_plot_color']('Q', 'tab:blue')}
            figure = Figure()
            axes = figure.add_subplot(111)
            state['add_plot']('Q', axes)
            self.assertEqual(axes.get_lines()[0].get_color(), '#112233')

            state['column_registry'].get('Q').color = '#abcdef'
            state['on_save_button_clicked'](None)
            _, registry = read_tsv(Path(directory) / 'curve_new.tsv')
            self.assertEqual(registry.get('Q').color, '#abcdef')

    def test_empty_color_does_not_add_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'legacy.tsv'
            path.write_text('time[s]\tQ[W]\n0\t2\n', encoding='utf-8')
            frame, registry = read_tsv(path)
            write_tsv(path, frame, registry)
            self.assertEqual(path.read_text().splitlines()[0],
                             'time [s]\tQ [W]')

    def test_malformed_metadata_is_rejected(self):
        headers = (
            'Q{color="broken}',
            'Q{color=blue}',
            'Q{color="red" other="x"}',
            'Q{color="red"; COLOR="blue"}',
            'Q{color="bad\\q"}',
            'Q{color="bad\\"}',
            'Q{1key="bad"}',
            'Q{color="foo"; other="unterminated}',
        )
        for header in headers:
            with self.subTest(header=header):
                with self.assertRaises(ValueError):
                    split_tsv_header_metadata(header)


if __name__ == '__main__':
    unittest.main()
