#!/usr/bin/python

import os
import sys
import keyword
import re
import pandas as pd
import numpy as np
try:
    import h5py
except ImportError:
    h5py = None
from itertools import cycle

from pandas import DataFrame
from csv_plotter_fft import (
    amplitude_spectrum, limit_spectrum_frequencies, select_time_interval,
    spectrum_decibels
)
from csv_plotter_metadata import (
    metadata_views, normalize_metadata_rows, read_hdf5_metadata, read_hdf5_strings,
    read_result_tsv, write_result_tsv, TSV_RUN_KEY_ORDER, SCALAR_NAMESPACES
)
from csv_plotter_units import (
    ColumnRegistry, read_csv, read_tsv, split_tsv_header, write_csv,
    write_tsv
)

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import GLib

import matplotlib
from matplotlib.backends.backend_gtk4 \
    import NavigationToolbar2GTK4

from matplotlib.backends.backend_gtk4agg \
    import FigureCanvasGTK4Agg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
import matplotlib.colors as mcolors

FONTSIZE = 22
matplotlib.rcParams.update({'font.size': FONTSIZE})

base_colors = {
    k: v for k, v in mcolors.BASE_COLORS.items() if k != 'w' and k != 'y'
}
base_colors = list(dict.keys(base_colors))
tableau_colors = list(dict.keys(mcolors.TABLEAU_COLORS))

colors_cycle = cycle(tableau_colors + base_colors)
styles_cycle = cycle(["solid", "dashdot", "dotted", "dashed"])

styles = {}
colors = {}

pre_plots = []
custom_labels = {
    "left": None,
    "right": None,
}

file_type = None
tsv_variant = None
has_timeseries = False
metadata_rows = []
column_registry = ColumnRegistry()
named_values = []
named_value_by_display_name = {}
simulation_metadata = []
fit_metadata = []
fit_inputs = []
HDF5_EXTENSIONS = (".h5", ".hdf5")

plot_notebook = None
spectrum_page_index = None
spectrum_settings = {
    "window": "hann",
    "detrend": "mean",
    "scale": "linear",
    "time_range": "full",
    "frequency_min": 0.0,
    "frequency_max": None,
}


class PlotNavigationToolbar(NavigationToolbar2GTK4):
    def release_zoom(self, event):
        super().release_zoom(event)
        rescale_visible_y()

    def release_pan(self, event):
        super().release_pan(event)
        rescale_visible_y()

    def _update_view(self):
        super()._update_view()
        rescale_visible_y()


def on_application_activation(application):
    global window, filename, pre_plots

    window = Gtk.ApplicationWindow(application=application)
    Gtk.ApplicationWindow.set_default_size(window, 1400, 900)

    argc = len(sys.argv)

    if argc < 2:
        dialog = Gtk.FileDialog(title=f"{program} - Choose a CSV, TSV or HDF5 file")
        Gtk.FileDialog.open(dialog, window, None, on_have_filename_ready, None)
    else:
        filename = sys.argv[1]
        if argc > 2:
            pre_plots = str.split(sys.argv[2], ",")
        on_have_filename_ready(None, None, None)
    return


def on_have_filename_ready(dialog, async_result, data):
    global axes_left, axes_right, canvas, filebase, filename
    global plot_notebook, spectrum_page_index, spectrum_canvas
    global spectrum_axes_left, spectrum_axes_right, spectrum_status
    global spectrum_min_entry, spectrum_max_entry

    if dialog is not None:
        gfile = Gtk.FileDialog.open_finish(dialog, result=async_result)
        if gfile is None:
            print("Error getting file", file=sys.stderr)
            sys.exit(1)
        filename = Gio.File.get_path(gfile)

    reload_file_contents()
    filebase = os.path.basename(filename)
    Gtk.ApplicationWindow.set_title(window, f"{program} - {filebase}")

    figure = Figure(layout="constrained")
    canvas = FigureCanvas(figure)
    toolbar = PlotNavigationToolbar(canvas)

    FigureCanvas.set_hexpand(canvas, True)
    FigureCanvas.set_vexpand(canvas, True)

    axes_left = Figure.add_subplot(figure, 111)
    Axes.grid(axes_left)
    axes_right = Axes.twinx(axes_left)

    plot_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    config_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    search_entry = Gtk.SearchEntry()
    Gtk.SearchEntry.set_placeholder_text(search_entry, "Search variables...")
    Gtk.Widget.set_hexpand(search_entry, True)
    Gtk.SearchEntry.connect(search_entry, "changed",
                            on_selector_search_changed)
    search_entry.search_timeout_id = 0

    buttons_header = Gtk.Label(label="Select x axis and columns to plot")

    Gtk.Box.append(config_box, search_entry)
    Gtk.Box.append(config_box, buttons_header)

    selection_scroll = Gtk.ScrolledWindow()
    search_entry.selection_scroll = selection_scroll
    selection_scroll.search_entry = search_entry
    metadata_scroll = Gtk.ScrolledWindow()

    custom_left_label_entry = Gtk.Entry()
    custom_right_label_entry = Gtk.Entry()

    Gtk.Entry.set_placeholder_text(custom_left_label_entry, "custom left label")
    Gtk.Entry.set_placeholder_text(custom_right_label_entry, "custom right label")
    Gtk.Entry.connect(custom_left_label_entry, "activate",
                      on_custom_label_activate)
    Gtk.Entry.connect(custom_right_label_entry, "activate",
                      on_custom_label_activate)

    custom_left_label_entry.axes = axes_left
    custom_right_label_entry.axes = axes_right

    reload_button = Gtk.Button.new_from_icon_name("document-revert")
    save_button = Gtk.Button.new_from_icon_name("document-save")
    title_button = Gtk.CheckButton(active=False, label="Show title")

    Gtk.Button.set_tooltip_text(reload_button, "Reload file contents")
    Gtk.Button.set_tooltip_text(save_button, "Save file changes on new file")
    Gtk.CheckButton.set_tooltip_text(title_button, "Toggle filename display")

    Gtk.Button.connect(reload_button, "clicked", on_reload_button_clicked)
    Gtk.Button.connect(save_button, "clicked", on_save_button_clicked)
    Gtk.CheckButton.connect(title_button, "toggled", on_title_button_clicked)

    reload_button.selection_scroll = selection_scroll
    reload_button.metadata_scroll = metadata_scroll
    save_button.selection_scroll = selection_scroll

    toolbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    Gtk.Box.append(toolbar_box, toolbar)
    Gtk.Box.append(toolbar_box, custom_left_label_entry)
    Gtk.Box.append(toolbar_box, custom_right_label_entry)
    Gtk.Box.append(toolbar_box, title_button)

    Gtk.Box.append(plot_box, toolbar_box)
    Gtk.Box.append(plot_box, canvas)

    reconfigure_plots_and_buttons(selection_scroll)
    reconfigure_metadata_tab(metadata_scroll)

    Gtk.ScrolledWindow.set_vexpand(selection_scroll, True)
    Gtk.ScrolledWindow.set_policy(selection_scroll,
                                  hscrollbar_policy=Gtk.PolicyType.NEVER,
                                  vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
    Gtk.ScrolledWindow.set_vexpand(metadata_scroll, True)
    Gtk.ScrolledWindow.set_policy(metadata_scroll,
                                  hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
                                  vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)

    new_data_entry = Gtk.Entry()
    Gtk.Entry.set_placeholder_text(new_data_entry, "add a plot...")
    Gtk.Entry.connect(new_data_entry, "activate", on_entry_activate)
    new_data_entry.selection_scroll = selection_scroll

    Gtk.Box.append(config_box, selection_scroll)
    Gtk.Box.append(config_box, new_data_entry)

    window_pane = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
    Gtk.Paned.set_wide_handle(window_pane, True)
    Gtk.Paned.set_position(window_pane, 1100)

    Gtk.Paned.set_start_child(window_pane, plot_box)
    Gtk.Paned.set_end_child(window_pane, config_box)

    Gtk.Paned.set_shrink_start_child(window_pane, False)
    Gtk.Paned.set_shrink_end_child(window_pane, False)

    spectrum_figure = Figure(layout="constrained")
    spectrum_canvas = FigureCanvas(spectrum_figure)
    spectrum_toolbar = NavigationToolbar2GTK4(spectrum_canvas)
    FigureCanvas.set_hexpand(spectrum_canvas, True)
    FigureCanvas.set_vexpand(spectrum_canvas, True)
    spectrum_axes_left = Figure.add_subplot(spectrum_figure, 111)
    spectrum_axes_right = Axes.twinx(spectrum_axes_left)
    spectrum_status = Gtk.Label(label="Select signals in the Plot tab")
    Gtk.Label.set_xalign(spectrum_status, 0.0)
    Gtk.Label.set_wrap(spectrum_status, True)
    Gtk.Label.set_selectable(spectrum_status, True)

    spectrum_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    spectrum_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                spacing=12)
    add_spectrum_dropdown(spectrum_controls, "Window", "window",
                          ("Hann", "Rectangular"), ("hann", "rectangular"))
    add_spectrum_dropdown(spectrum_controls, "Detrend", "detrend",
                          ("Remove mean", "None"), ("mean", "none"))
    add_spectrum_dropdown(spectrum_controls, "Amplitude", "scale",
                          ("Linear", "dB (relative to peak)"),
                          ("linear", "db"))
    add_spectrum_dropdown(spectrum_controls, "Time range", "time_range",
                          ("All samples", "Visible Plot range"),
                          ("full", "visible"))
    Gtk.Box.append(spectrum_box, spectrum_controls)

    frequency_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                 spacing=12)
    Gtk.Box.append(frequency_controls, Gtk.Label(label="Frequency [Hz]:"))
    Gtk.Box.append(frequency_controls, Gtk.Label(label="Min"))
    spectrum_min_entry = Gtk.Entry()
    Gtk.Entry.set_width_chars(spectrum_min_entry, 9)
    Gtk.Entry.set_text(spectrum_min_entry, "0")
    Gtk.Entry.connect(spectrum_min_entry, "activate",
                      on_spectrum_frequency_apply)
    Gtk.Box.append(frequency_controls, spectrum_min_entry)
    Gtk.Box.append(frequency_controls, Gtk.Label(label="Max"))
    spectrum_max_entry = Gtk.Entry()
    Gtk.Entry.set_width_chars(spectrum_max_entry, 9)
    Gtk.Entry.set_placeholder_text(spectrum_max_entry, "Nyquist")
    Gtk.Entry.connect(spectrum_max_entry, "activate",
                      on_spectrum_frequency_apply)
    Gtk.Box.append(frequency_controls, spectrum_max_entry)
    frequency_button = Gtk.Button(label="Apply Hz")
    Gtk.Button.connect(frequency_button, "clicked",
                       on_spectrum_frequency_apply)
    Gtk.Box.append(frequency_controls, frequency_button)
    Gtk.Box.append(spectrum_box, frequency_controls)

    Gtk.Box.append(spectrum_box, spectrum_toolbar)
    Gtk.Box.append(spectrum_box, spectrum_canvas)
    Gtk.Box.append(spectrum_box, spectrum_status)

    plot_notebook = Gtk.Notebook()
    Gtk.Notebook.set_tab_pos(plot_notebook, Gtk.PositionType.TOP)
    Gtk.Notebook.append_page(plot_notebook, window_pane,
                             Gtk.Label(label="Plot"))
    spectrum_page_index = Gtk.Notebook.append_page(
        plot_notebook, spectrum_box, Gtk.Label(label="Spectrum"))
    Gtk.Notebook.append_page(plot_notebook, metadata_scroll,
                             Gtk.Label(label="Metadata"))
    Gtk.Notebook.connect(plot_notebook, "switch-page",
                         on_notebook_switch_page)

    # Keep file operations available even when there is no plot axis.
    file_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    Gtk.Box.append(file_controls, reload_button)
    Gtk.Box.append(file_controls, save_button)
    root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    Gtk.Box.append(root_box, file_controls)
    Gtk.Widget.set_vexpand(plot_notebook, True)
    Gtk.Box.append(root_box, plot_notebook)
    update_plot_availability()
    Gtk.ApplicationWindow.set_child(window, root_box)
    Gtk.ApplicationWindow.set_visible(window, True)
    return


def update_plot_availability():
    if plot_notebook is None:
        return
    enabled = not data_frame.empty
    for index in (0, spectrum_page_index):
        page = Gtk.Notebook.get_nth_page(plot_notebook, index)
        Gtk.Widget.set_sensitive(page, enabled)
    if not enabled:
        Gtk.Notebook.set_current_page(plot_notebook, 2)


def on_notebook_switch_page(notebook, page, page_number):
    if page_number == spectrum_page_index and not data_frame.empty:
        redraw_spectrum()
    return


def add_spectrum_dropdown(parent, label, setting, labels, values):
    """Create a setting selector without modifying the time-domain controls."""
    Gtk.Box.append(parent, Gtk.Label(label=label))
    dropdown = Gtk.DropDown.new_from_strings(list(labels))
    dropdown.spectrum_setting = setting
    dropdown.spectrum_values = values
    Gtk.DropDown.set_selected(dropdown,
                              values.index(spectrum_settings[setting]))
    Gtk.DropDown.connect(dropdown, "notify::selected",
                         on_spectrum_setting_changed)
    Gtk.Box.append(parent, dropdown)
    return


def on_spectrum_setting_changed(dropdown, property_spec=None):
    setting = dropdown.spectrum_setting
    selected = Gtk.DropDown.get_selected(dropdown)
    spectrum_settings[setting] = dropdown.spectrum_values[selected]
    if (plot_notebook is not None
            and not data_frame.empty
            and Gtk.Notebook.get_current_page(plot_notebook)
            == spectrum_page_index):
        redraw_spectrum()
    return


def on_spectrum_frequency_apply(widget):
    """Apply the frequency limits together, retaining prior valid settings."""
    try:
        low_text = Gtk.Entry.get_text(spectrum_min_entry).strip()
        high_text = Gtk.Entry.get_text(spectrum_max_entry).strip()
        low = float(low_text) if low_text else 0.0
        high = float(high_text) if high_text else None
        if not np.isfinite(low) or low < 0:
            raise ValueError("minimum frequency must be nonnegative")
        if high is not None and (not np.isfinite(high) or high <= low):
            raise ValueError("maximum frequency must exceed minimum")
    except ValueError as exception:
        Gtk.Label.set_text(spectrum_status, f"Invalid frequency range: {exception}")
        return
    spectrum_settings["frequency_min"] = low
    spectrum_settings["frequency_max"] = high
    if (plot_notebook is not None
            and not data_frame.empty
            and Gtk.Notebook.get_current_page(plot_notebook)
            == spectrum_page_index):
        redraw_spectrum()
    return


def spectrum_signal_values(name):
    if name in named_value_by_display_name:
        value = named_value_by_display_name[name]["value"]
        return np.full(len(data_frame.index), value, dtype=np.float64)
    return data_frame[name].to_numpy()


def spectrum_axis_label(names):
    if spectrum_settings["scale"] == "db":
        return "Relative amplitude [dB re peak]"
    units = []
    for name in names:
        unit = str(selector_unit(name)).strip()
        if unit and unit not in units:
            units.append(unit)
    if not units:
        return "Amplitude"
    return "Amplitude " + ", ".join(
        unit if unit.startswith("[") and unit.endswith("]")
        else f"[{unit}]" for unit in units)


def redraw_spectrum():
    """Plot the selected time-domain signals without modifying input data."""
    Axes.clear(spectrum_axes_left)
    Axes.clear(spectrum_axes_right)
    Axes.grid(spectrum_axes_left, True)
    Axes.set_xlabel(spectrum_axes_left, "Frequency [Hz]", fontsize=FONTSIZE)
    Axes.set_xmargin(spectrum_axes_left, 0.01)

    source_axes = (axes_left, axes_right)
    target_axes = (spectrum_axes_left, spectrum_axes_right)
    times = x_data.to_numpy()
    plotted_names = [[], []]
    problems = []
    resampled_names = []
    filled_names = []
    selected = sum((len(Axes.get_lines(axes)) for axes in source_axes), 0)
    time_unit = str(selector_unit(x_data.name)).strip().lower()
    if time_unit.startswith("[") and time_unit.endswith("]"):
        time_unit = time_unit[1:-1].strip()

    if time_unit and time_unit not in ("s", "sec", "second", "seconds"):
        problems.append(f"X axis '{x_data.name}' uses '{time_unit}'; "
                        "select time in seconds for an FFT in Hz")
    elif selected == 0:
        problems.append("Select one or more Y signals in the Plot tab")
    else:
        for source, target, names in zip(source_axes, target_axes,
                                         plotted_names):
            for line in Axes.get_lines(source):
                name = Line2D.get_label(line)
                try:
                    samples = spectrum_signal_values(name)
                    sample_times = times
                    if spectrum_settings["time_range"] == "visible":
                        sample_times, samples = select_time_interval(
                            times, samples, Axes.get_xlim(axes_left))
                    frequencies, amplitudes, sample_info = amplitude_spectrum(
                        sample_times, samples,
                        window=spectrum_settings["window"],
                        detrend=spectrum_settings["detrend"],
                        sampling="interpolate", missing="interpolate",
                        return_info=True)
                    if spectrum_settings["scale"] == "db":
                        amplitudes = spectrum_decibels(amplitudes)
                    frequencies, amplitudes = limit_spectrum_frequencies(
                        frequencies, amplitudes,
                        spectrum_settings["frequency_min"],
                        spectrum_settings["frequency_max"])
                except (ValueError, TypeError, KeyError) as exception:
                    problems.append(f"{name}: {exception}")
                    continue
                if sample_info["resampled"]:
                    resampled_names.append(name)
                if sample_info["interpolated_missing"]:
                    filled_names.append(name)
                Axes.plot(target, frequencies, amplitudes, label=name,
                          linestyle=styles[name], color=colors[name],
                          alpha=0.9, linewidth=2)
                names.append(name)

    for axes, names in zip(target_axes, plotted_names):
        Axes.set_ylabel(axes, spectrum_axis_label(names), fontsize=FONTSIZE)
        show_left = bool(names) and axes is spectrum_axes_left
        show_right = bool(names) and axes is spectrum_axes_right
        Axes.tick_params(axes, axis="y", left=show_left,
                         labelleft=show_left, right=show_right,
                         labelright=show_right)
        if names:
            Axes.legend(axes, fontsize=max(10, FONTSIZE // 2),
                        loc="upper left" if axes is spectrum_axes_left
                        else "upper right")

    if problems:
        message = " | ".join(problems[:3])
        if len(problems) > 3:
            message += f" | ... and {len(problems) - 3} more errors"
    else:
        window_label = spectrum_settings["window"].capitalize()
        trend_label = ("mean removed" if spectrum_settings["detrend"] == "mean"
                       else "mean retained")
        message = f"One-sided spectrum · {window_label} window · {trend_label}"
        if spectrum_settings["scale"] == "db":
            message += " · dB relative to each signal's peak (floor -120 dB)"
        if spectrum_settings["time_range"] == "visible":
            message += " · Plot visible time interval"
        if resampled_names:
            message += " · Resampled time gaps: " + ", ".join(resampled_names)
        if filled_names:
            message += " · Interpolated missing values: " + ", ".join(filled_names)
        if not time_unit:
            message += " · X axis assumed to be in seconds"
    Gtk.Label.set_text(spectrum_status, message)
    FigureCanvas.draw(spectrum_canvas)
    return



def filename_has_hdf5_extension(path):
    extension = os.path.splitext(path)[1]
    return extension.lower() in HDF5_EXTENSIONS


def fixed_hdf5_strings(strings):
    strings = [str(s) for s in strings]
    width = 1
    for string in strings:
        width = max(width, len(string.encode("utf-8")) + 1)

    values = []
    for string in strings:
        value = string.encode("utf-8")[:width - 1]
        values.append(value)

    return np.array(values, dtype=f"S{width}")


def configure_metadata(rows, column_names=()):
    global metadata_rows, named_values, named_value_by_display_name
    global simulation_metadata, fit_metadata, fit_inputs

    metadata_rows = normalize_metadata_rows(rows)
    named_values, simulation_metadata, fit_metadata, fit_inputs = \
        metadata_views(metadata_rows, column_names)
    named_value_by_display_name = {
        value["display_name"]: value for value in named_values
    }


def reload_file_contents():
    global data_frame, x_data, file_type, column_registry
    global tsv_variant, has_timeseries

    data_frame = None
    x_data = None
    file_type = None
    tsv_variant = None
    has_timeseries = False
    column_registry = ColumnRegistry()
    configure_metadata([])
    try:
        if h5py is None:
            is_hdf5 = filename_has_hdf5_extension(filename)
        else:
            try:
                is_hdf5 = h5py.is_hdf5(filename)
            except Exception:
                is_hdf5 = filename_has_hdf5_extension(filename)

        if is_hdf5:
            if h5py is None:
                raise ImportError("h5py is required to read HDF5 files")

            with h5py.File(filename, "r") as hdf5_file:
                rows = read_hdf5_metadata(hdf5_file)
                has_timeseries = "data" in hdf5_file
                if not has_timeseries:
                    if any(key in hdf5_file for key in ("names", "units", "colors")):
                        raise ValueError("HDF5 file has incomplete time-series datasets")
                    if not rows and len(hdf5_file):
                        raise ValueError("HDF5 file has neither data nor recognized metadata")
                    data_frame = pd.DataFrame()
                else:
                    if "names" not in hdf5_file:
                        raise ValueError("HDF5 file does not have a /names dataset")
                    data = np.array(hdf5_file["data"], dtype=np.float64)
                    if data.ndim != 2:
                        raise ValueError("HDF5 /data dataset must have 2 dimensions")
                    ncolumns = data.shape[1]
                    names = read_hdf5_strings(hdf5_file, "names", ncolumns)
                    if "units" in hdf5_file:
                        units = read_hdf5_strings(hdf5_file, "units", ncolumns)
                    else:
                        units = [""]*ncolumns
                    if "colors" in hdf5_file:
                        column_colors = read_hdf5_strings(hdf5_file, "colors", ncolumns)
                    else:
                        column_colors = [""]*ncolumns
                    column_registry = ColumnRegistry.from_columns(
                        names, units, column_colors)
                    data_frame = pd.DataFrame(data, columns=column_registry.names())
            configure_metadata(rows, data_frame.columns)
            file_type = "hdf5"
        else:
            file_type = "tsv" if filename.lower().endswith(".tsv") else "csv"
            if file_type == "tsv":
                tsv_variant, rows, data_frame, column_registry = read_result_tsv(filename)
                has_timeseries = tsv_variant != "metadata_only"
                configure_metadata(rows, data_frame.columns)
            else:
                data_frame, column_registry = read_csv(filename)
                has_timeseries = True
    except Exception as exception:
        print(f"Error reading {filename}: {exception}", file=sys.stderr)
        sys.exit(1)
    if data_frame is None:
        print(f"Error reading {filename}", file=sys.stderr)
        sys.exit(1)

    if not has_timeseries:
        return
    if "time" not in data_frame.columns:
        try:
            rows = DataFrame.reset_index(data_frame).index
            DataFrame.insert(data_frame, 0, 'Row', rows)
            column_registry.add("Row")
        except Exception:
            pass
    if len(data_frame.columns):
        x_data = data_frame.iloc[:, 0]
    return


def run_metadata_display_name(name, kind):
    display_names = {
        "started_at": "Started at (UTC)",
        "ended_at": "Ended at (UTC)",
        "elapsed_seconds": "Elapsed wall time (s)",
        "converged": "Converged",
        "pre_initialized": "Pre-initialized via cy_system_init",
        "commit_on_success": "Commit fitted values on success",
        "parameters_committed": "Fitted values committed",
        "params_committed": "Fitted values committed",
        "integration_method": "Integration method",
        "input_file": "Input / experimental data file",
        "minimization_method": "Minimization method",
        "simulation_count": "Simulation runs",
    }
    if name == "simulation_date":
        return "Simulation date (UTC)"
    if name == "fit_date":
        return "Fitting date (UTC)"
    return display_names.get(name, name.replace("_", " ").title())


def simulation_metadata_display_name(name):
    return run_metadata_display_name(name, "simulation")


def fit_metadata_display_name(name):
    return run_metadata_display_name(name, "fit")


def metadata_values_for_kind(kind):
    values = []
    for named_value in named_values:
        if named_value["kind"] == kind:
            values.append(named_value)
    return values


def append_metadata_text_section(lines, title, headers, rows):
    if len(rows) == 0:
        return

    if len(lines) > 0:
        lines.append("")
    lines.append(title)

    text_rows = []
    for row in rows:
        text_row = []
        for cell in row:
            if cell is None:
                text_row.append("—")
            elif isinstance(cell, str):
                text_row.append(cell.replace("\\", "\\\\")
                                .replace("\t", "\\t").replace("\n", "\\n")
                                .replace("\r", "\\r"))
            elif np.isfinite(cell):
                text_row.append(str(cell) if isinstance(cell, (int, np.integer))
                                else repr(float(cell)))
            else:
                text_row.append(str(cell))
        text_rows.append(text_row)

    widths = []
    for index, header in enumerate(headers):
        width = len(header)
        for row in text_rows:
            width = max(width, len(row[index]))
        widths.append(width)

    table_lines = []
    cells = []
    for index, header in enumerate(headers):
        if index == len(headers) - 1:
            cells.append(header)
        else:
            cells.append(f"{header:<{widths[index]}}")
    table_lines.append("  ".join(cells))

    for row in text_rows:
        cells = []
        for index, cell in enumerate(row):
            if index == len(row) - 1:
                cells.append(cell)
            else:
                cells.append(f"{cell:<{widths[index]}}")
        table_lines.append("  ".join(cells))
    lines.append("\n".join(table_lines))
    return


def run_metadata_rows(metadata, display_name):
    rows = []
    for value in metadata:
        metadata_value = value["value"]
        if value["name"] == "elapsed_seconds":
            try:
                seconds = float(metadata_value)
                valid_duration = seconds >= 0 and np.isfinite(seconds * 1000.0)
            except (ValueError, TypeError, OverflowError):
                valid_duration = False
            if valid_duration:
                total_milliseconds = int(round(seconds*1000.0))
                whole_seconds, milliseconds = divmod(total_milliseconds, 1000)
                raw_seconds = f"{whole_seconds}.{milliseconds:03d}s"

                if seconds <= 60.0:
                    metadata_value = raw_seconds
                elif seconds <= 3600.0:
                    minutes, remaining_seconds = divmod(whole_seconds, 60)
                    metadata_value = (
                        f"{minutes}min{remaining_seconds}s ({raw_seconds})")
                elif seconds <= 3600.0*60.0:
                    hours, remainder = divmod(whole_seconds, 3600)
                    minutes = remainder//60
                    metadata_value = f"{hours}h{minutes}min ({raw_seconds})"
                else:
                    days, remainder = divmod(whole_seconds, 24*3600)
                    hours, remainder = divmod(remainder, 3600)
                    minutes = remainder//60
                    metadata_value = (
                        f"{days}d{hours}h{minutes}min ({raw_seconds})")
        rows.append([
            display_name(value["name"]),
            metadata_value,
        ])
    return rows


def metadata_rows_for_kind(kind, fields=("name", "value", "unit", "display_name")):
    """Use canonical rows, including those without a plottable value."""
    plot_names = {value["name"]: value["display_name"]
                  for value in metadata_values_for_kind(kind)}
    rows = sorted((row for row in metadata_rows if row["kind"] == kind),
                  key=lambda row: row["name"])
    result = []
    for row in rows:
        cells = []
        for field in fields:
            if field == "display_name":
                cell = plot_names.get(row["name"])
            else:
                cell = row[field]
                if field == "optimized" and cell is not None:
                    cell = "Yes" if cell else "No"
            cells.append(cell)
        result.append(cells)
    return result


def metadata_pane_text():
    """Render equivalent HDF5 and TSV metadata in the same order."""
    lines = ["Metadata"]
    append_metadata_text_section(lines, "File", ["Name", "Value"], [
        ["Filename", filename],
    ])

    if not metadata_rows:
        lines.extend(["", "This file does not contain recognized metadata."])
        return "\n".join(lines) + "\n"

    for kind, title, values, display_name in (
            ("simulation", "Simulation", simulation_metadata,
             simulation_metadata_display_name),
            ("fit", "Fitting", fit_metadata, fit_metadata_display_name)):
        order = {name: i for i, name in enumerate(TSV_RUN_KEY_ORDER[kind])}
        values = sorted(values, key=lambda row: (
            order.get(row["name"], len(order)), row["name"]))
        append_metadata_text_section(lines, title, ["Name", "Value"],
                                     run_metadata_rows(values, display_name))

    sections = [
        ("fit_input", "Optimized inputs", ["Name", "Knot interval (s)"],
         ("name", "value")),
        ("parameter", "Parameters", ["Name", "Value", "Default", "Unit", "Plot name"],
         ("name", "value", "default_value", "unit", "display_name")),
        ("initial_state", "Initial states", ["Name", "Effective", "Original", "Unit", "Plot name"],
         ("name", "value", "initial_value", "unit", "display_name")),
    ]
    for kind, title in (("fit_parameter", "Fitted parameters"),
                        ("fit_initial_state", "Fitted initial states")):
        sections.append((kind, title,
                         ["Name", "Fitted", "Initial", "Original initial", "Lower", "Upper",
                          "Optimized", "Unit", "Plot name"],
                         ("name", "value", "initial_value", "original_initial_value",
                          "lower_bound", "upper_bound", "optimized", "unit", "display_name")))
    for kind, title in (("tf_parameter", "TF identification"), ("constant", "Constants")):
        sections.append((kind, title, ["Name", "Value", "Unit", "Plot name"],
                         ("name", "value", "unit", "display_name")))
    for kind, title, headers, fields in sections:
        append_metadata_text_section(lines, title, headers,
                                     metadata_rows_for_kind(kind, fields))

    known = {"simulation", "fit"} | {section[0] for section in sections}
    for kind in sorted({row["kind"] for row in metadata_rows} - known):
        append_metadata_text_section(
            lines, f"Other metadata ({kind})",
            ["Name", "Value", "Unit", "Default", "Initial", "Original initial",
             "Lower", "Upper", "Optimized"],
            metadata_rows_for_kind(kind, (
                "name", "value", "unit", "default_value", "initial_value",
                "original_initial_value", "lower_bound", "upper_bound", "optimized")))
    return "\n".join(lines) + "\n"


def reconfigure_metadata_tab(metadata_scroll):
    text = metadata_pane_text()
    buffer = Gtk.TextBuffer()
    Gtk.TextBuffer.set_text(buffer, text, -1)

    text_view = Gtk.TextView.new_with_buffer(buffer)
    Gtk.TextView.set_editable(text_view, False)
    Gtk.TextView.set_cursor_visible(text_view, False)
    Gtk.TextView.set_monospace(text_view, True)
    Gtk.TextView.set_wrap_mode(text_view, Gtk.WrapMode.NONE)
    Gtk.TextView.set_left_margin(text_view, 12)
    Gtk.TextView.set_right_margin(text_view, 12)
    Gtk.TextView.set_top_margin(text_view, 12)
    Gtk.TextView.set_bottom_margin(text_view, 12)
    Gtk.Widget.set_hexpand(text_view, True)
    Gtk.Widget.set_vexpand(text_view, True)
    Gtk.ScrolledWindow.set_child(metadata_scroll, text_view)
    return


def metadata_name(name):
    return (name in named_value_by_display_name
            and name not in data_frame.columns)


def selector_unit(name):
    info = column_registry.get(name)
    if info is not None:
        return info.unit
    metadata = named_value_by_display_name.get(name)
    if metadata is not None:
        return metadata["unit"]
    return ""


def display_unit(unit):
    unit = str(unit).strip()
    if not unit:
        return ""
    if unit.startswith("[") and unit.endswith("]"):
        return f" {unit}"
    return f" [{unit}]"


def selector_parent_box(buttons_box, name, namespace_boxes=None):
    """Use expanders only for names containing a dot."""
    if "." not in name:
        return buttons_box

    namespace = name.split(".", 1)[0]
    if namespace_boxes is not None and namespace in namespace_boxes:
        return namespace_boxes[namespace]

    if namespace_boxes is None:
        child = Gtk.Widget.get_first_child(buttons_box)
        while child is not None:
            if isinstance(child, Gtk.Expander):
                if Gtk.Expander.get_label(child) == namespace:
                    return Gtk.Expander.get_child(child)
            child = Gtk.Widget.get_next_sibling(child)

    expander = Gtk.Expander(label=namespace)
    ns_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    Gtk.Expander.set_expanded(expander, True)
    Gtk.Expander.set_child(expander, ns_box)
    Gtk.Box.append(buttons_box, expander)
    if namespace_boxes is not None:
        namespace_boxes[namespace] = ns_box
    return ns_box


def configured_plot_color(name, fallback):
    """Use a valid explicit column color, otherwise retain auto-coloring."""
    info = column_registry.get(name)
    if info is not None and info.color and mcolors.is_color_like(info.color):
        return info.color
    return fallback


def filter_selector_items(selection_scroll, query):
    query = query.casefold()
    buttons_box = selection_scroll.buttons_box
    child = Gtk.Widget.get_first_child(buttons_box)

    while child is not None:
        if isinstance(child, Gtk.Expander):
            namespace_box = Gtk.Expander.get_child(child)
            item = Gtk.Widget.get_first_child(namespace_box)
            namespace_visible = False
            while item is not None:
                visible = query in item.name.casefold()
                Gtk.Widget.set_visible(item, visible)
                namespace_visible = namespace_visible or visible
                item = Gtk.Widget.get_next_sibling(item)
            Gtk.Widget.set_visible(child, namespace_visible)
        else:
            Gtk.Widget.set_visible(child, query in child.name.casefold())
        child = Gtk.Widget.get_next_sibling(child)
    return


def on_selector_search_timeout(search_entry):
    search_entry.search_timeout_id = 0
    query = Gtk.Editable.get_text(search_entry)
    filter_selector_items(search_entry.selection_scroll, query)
    return False


def on_selector_search_changed(search_entry):
    if search_entry.search_timeout_id != 0:
        GLib.source_remove(search_entry.search_timeout_id)
    search_entry.search_timeout_id = GLib.timeout_add(
        100, on_selector_search_timeout, search_entry)
    return


def reconfigure_plots_and_buttons(selection_scroll):
    global x_button_group, data_frame, pre_plots

    buttons_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    namespace_boxes = {}
    ns_colors = {}

    if data_frame.empty:
        clean_plotted_get_list()
        x_button_group = None
        pre_plots = []
        Axes.set_xlabel(axes_left, "", fontsize=FONTSIZE)
        configure_y_axis_labels_and_ticks()
        put_legends()
        selection_scroll.buttons_box = buttons_box
        Gtk.ScrolledWindow.set_child(selection_scroll, buttons_box)
        return

    names = [str(name) for name in data_frame.columns]
    names.extend(sorted(named_value_by_display_name))
    name_first = names[0]
    x_button_group = None

    ns_first = str.split(name_first, ".")[0]
    first_box = selector_parent_box(buttons_box, name_first, namespace_boxes)

    if any(p.startswith("ref_") or p.startswith("reference") for p in str.split(name_first, ".")):
        colors[name_first] = "black"
        styles[name_first] = "dotted"
    else:
        ns_colors[ns_first] = next(colors_cycle)
        colors[name_first] = ns_colors[ns_first]
        styles[name_first] = "solid"

    colors[name_first] = configured_plot_color(name_first, colors[name_first])
    add_buttons(name_first, first_box)

    plotted_left = []
    plotted_right = []
    if len(pre_plots) == 0:
        plotted_left, plotted_right = clean_plotted_get_list()

    for name in names[1:]:
        left = False
        right = False

        ns = str.split(name, ".")[0]
        is_ref = any(p.startswith("ref_") or p.startswith("reference") for p in str.split(name, "."))

        if is_ref:
            colors[name] = "black"
            styles[name] = "dotted"
        else:
            if ns not in ns_colors:
                ns_colors[ns] = next(colors_cycle)
            colors[name] = ns_colors[ns]
            styles[name] = "solid"

        colors[name] = configured_plot_color(name, colors[name])

        if name in pre_plots:
            if not is_ref:
                styles[name] = "solid"
            add_plot(name, axes_left)
            left = True
        elif len(pre_plots) == 0:
            if name in plotted_left:
                if not is_ref:
                    styles[name] = "solid"
                add_plot(name, axes_left)
                left = True
            if name in plotted_right:
                if not is_ref:
                    styles[name] = "dashed"
                add_plot(name, axes_right)
                right = True

        parent_box = selector_parent_box(buttons_box, name, namespace_boxes)
        add_buttons(name, parent_box, left=left, right=right)

    pre_plots = []
    Axes.set_xlabel(axes_left, x_data.name, fontsize=FONTSIZE)
    configure_y_axis_labels_and_ticks()
    put_legends()

    selection_scroll.buttons_box = buttons_box
    Gtk.ScrolledWindow.set_child(selection_scroll, buttons_box)
    if hasattr(selection_scroll, "search_entry"):
        query = Gtk.Editable.get_text(selection_scroll.search_entry)
        filter_selector_items(selection_scroll, query)
    return


def clean_plotted_get_list():
    plotted_left = []
    plotted_right = []

    for line in list(Axes.get_lines(axes_left)):
        list.append(plotted_left, Line2D.get_label(line))
        Line2D.remove(line)
    for line in list(Axes.get_lines(axes_right)):
        list.append(plotted_right, Line2D.get_label(line))
        Line2D.remove(line)

    return plotted_left, plotted_right


def get_axes_label_from_units(axes):
    labels = []
    seen = set()

    for line in Axes.get_lines(axes):
        name = Line2D.get_label(line)
        unit = selector_unit(name)
        unit = str(unit).strip()
        if unit == "":
            label = None
        elif unit.startswith("[") and unit.endswith("]"):
            label = unit
        else:
            label = f"[{unit}]"
        if label is not None and label not in seen:
            labels.append(label)
            seen.add(label)

    if len(labels) > 0:
        return ", ".join(labels)

    names = ""
    for line in Axes.get_lines(axes):
        name = Line2D.get_label(line)
        names += f" {name} "
    return names


def configure_y_axis_labels_and_ticks(new_custom_label=None, axes=None):
    global custom_labels

    if new_custom_label is not None:
        name = "left" if axes is axes_left else "right"
        custom_labels[name] = new_custom_label

    has_left_plots = len(Axes.get_lines(axes_left)) != 0
    has_right_plots = len(Axes.get_lines(axes_right)) != 0

    if has_left_plots:
        Axes.tick_params(axes_left, axis='y', left=True, labelleft=True)
    else:
        Axes.tick_params(axes_left, axis='y', left=False, labelleft=False)
    if has_right_plots:
        Axes.tick_params(axes_right, axis='y', right=True, labelright=True)
    else:
        Axes.tick_params(axes_right, axis='y', right=False, labelright=False)

    Axes.ticklabel_format(axes_left, useOffset=False)
    Axes.ticklabel_format(axes_right, useOffset=False)

    label_left = get_axes_label_from_units(axes_left)
    label_right = get_axes_label_from_units(axes_right)

    if custom_labels["left"] is not None:
        label_left = custom_labels["left"]
    if custom_labels["right"] is not None:
        label_right = custom_labels["right"]

    Axes.set_ylabel(axes_left, label_left, fontsize=FONTSIZE)
    Axes.set_ylabel(axes_right, label_right, fontsize=FONTSIZE)
    return


def add_buttons(name, buttons_box, left=False, right=False):
    global x_button_group

    def _set_margins(button):
        Gtk.Button.set_margin_end(button, 2)
        Gtk.Button.set_margin_start(button, 2)

    x_button = Gtk.CheckButton(group=x_button_group)
    y_button_left = Gtk.CheckButton(active=left)
    y_button_right = Gtk.CheckButton(active=right)
    named_value = named_value_by_display_name.get(name)
    info = column_registry.get(name)
    if info is not None:
        item_label = Gtk.EditableLabel.new(info.source_name)
    elif named_value is not None:
        item_label = Gtk.Label(label=name.split(".", 1)[1])
    else:
        item_label = Gtk.EditableLabel.new(name)
    unit_label = Gtk.Label(label=display_unit(selector_unit(name)))
    Gtk.Widget.set_tooltip_text(item_label, f"Expression name: {name}")
    style_button = Gtk.Button.new_from_icon_name("system-run-symbolic")
    color_button = Gtk.Button.new_from_icon_name("preferences-color-symbolic")
    delete_button = Gtk.Button.new_from_icon_name("edit-delete")

    Gtk.Button.set_tooltip_text(x_button, "Set as x axis")
    Gtk.Button.set_tooltip_text(y_button_left, "Plot on left axis")
    Gtk.Button.set_tooltip_text(y_button_right, "Plot on right axis")
    Gtk.Button.set_tooltip_text(style_button, "Change line style")
    Gtk.Button.set_tooltip_text(color_button, "Change line color")
    Gtk.Button.set_tooltip_text(delete_button, "Delete from data")

    if metadata_name(name):
        Gtk.Button.set_sensitive(x_button, False)
        Gtk.Button.set_sensitive(delete_button, False)
        Gtk.Button.set_tooltip_text(x_button,
                                    "Scalar metadata cannot be x axis")
        Gtk.Button.set_tooltip_text(delete_button,
                                    "Metadata is saved separately")

    y_button_left.axes = axes_left
    y_button_right.axes = axes_right

    _set_margins(x_button)
    _set_margins(y_button_left)
    _set_margins(y_button_right)

    if x_button_group is None:
        x_button_group = x_button
        Gtk.CheckButton.set_active(x_button, True)

    Gtk.CheckButton.connect(x_button, "toggled", on_x_button_toggled)
    Gtk.CheckButton.connect(y_button_left, "toggled", on_y_button_toggled)
    Gtk.CheckButton.connect(y_button_right, "toggled", on_y_button_toggled)
    if named_value is None:
        Gtk.EditableLabel.connect(item_label, "notify::editing", on_item_label_notify_editing)
    Gtk.Button.connect(style_button, "clicked", on_style_button_click)
    Gtk.Button.connect(color_button, "clicked", on_color_button_click)
    Gtk.Button.connect(delete_button, "clicked", on_delete_button_click)

    item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    item.name = name
    item.y_button_left = y_button_left
    item.y_button_right = y_button_right
    item.unit_label = unit_label

    Gtk.Box.append(item, x_button)
    Gtk.Box.append(item, y_button_left)
    Gtk.Box.append(item, y_button_right)
    Gtk.Box.append(item, item_label)
    Gtk.Box.append(item, unit_label)
    Gtk.Box.append(item, style_button)
    Gtk.Box.append(item, color_button)
    Gtk.Box.append(item, delete_button)

    Gtk.Button.set_hexpand(style_button, True)
    Gtk.Button.set_hexpand(color_button, False)
    Gtk.Button.set_hexpand(delete_button, False)

    Gtk.Button.set_halign(style_button, Gtk.Align.END)
    Gtk.Button.set_halign(color_button, Gtk.Align.END)
    Gtk.Button.set_halign(delete_button, Gtk.Align.END)

    Gtk.Box.append(buttons_box, item)
    return


def on_reload_button_clicked(reload_button):
    reload_file_contents()
    reconfigure_plots_and_buttons(reload_button.selection_scroll)
    reconfigure_metadata_tab(reload_button.metadata_scroll)
    update_plot_availability()
    redraw_plots(full=True)
    return


def on_save_button_clicked(save_button):
    root = str.rsplit(filename, '.', maxsplit=1)[0]
    if file_type == "hdf5":
        newfile = root + "_new.h5"
    else:
        newfile = root + "_new.tsv"

    try:
        if file_type == "hdf5":
            if h5py is None:
                raise ImportError("h5py is required to save HDF5 files")

            table_datasets = {}
            if has_timeseries:
                names = column_registry.source_names(data_frame.columns)
                units = [column_registry.get(name).unit for name in data_frame.columns]
                column_colors = column_registry.colors(data_frame.columns)
                table_datasets = {
                    "data": data_frame.to_numpy(dtype=np.float64),
                    "names": fixed_hdf5_strings(names),
                    "units": fixed_hdf5_strings(units),
                    "colors": fixed_hdf5_strings(column_colors),
                }

            # Preserve unrelated HDF5 contents, including unknown metadata
            # groups, datasets and file attributes. Only the plotted table is
            # replaced when the user saves edited columns.
            with h5py.File(filename, "r") as source, \
                    h5py.File(newfile, "w") as hdf5_file:
                for name in source:
                    source.copy(name, hdf5_file)
                for name, value in source.attrs.items():
                    hdf5_file.attrs[name] = value
                for name, values in table_datasets.items():
                    if name not in hdf5_file:
                        hdf5_file.create_dataset(name, data=values)
                        continue
                    dataset = hdf5_file[name]
                    if (dataset.shape == values.shape
                            and np.can_cast(values.dtype, dataset.dtype,
                                            casting="safe")):
                        # Keep compression, chunk layout and attributes when
                        # an existing column dataset can be updated in place.
                        dataset[...] = values
                        continue
                    attributes = dict(dataset.attrs.items())
                    del hdf5_file[name]
                    dataset = hdf5_file.create_dataset(name, data=values)
                    for attr_name, attr_value in attributes.items():
                        dataset.attrs[attr_name] = attr_value
        elif file_type == "tsv":
            write_result_tsv(newfile, tsv_variant, metadata_rows,
                             data_frame, column_registry)
        else:
            write_tsv(newfile, data_frame, column_registry)
    except Exception as exception:
        print(f"Error saving {newfile}: {exception}", file=sys.stderr)
    return


def on_title_button_clicked(title_button):
    active = Gtk.CheckButton.get_active(title_button)
    if active:
        Axes.set_title(axes_left, filebase)
    else:
        Axes.set_title(axes_left, "")
    redraw_plots()
    return


def on_custom_label_activate(entry):
    buffer = Gtk.Entry.get_buffer(entry)
    text = Gtk.EntryBuffer.get_text(buffer)

    configure_y_axis_labels_and_ticks(text, entry.axes)
    redraw_plots()
    return


def reserved_metadata_names():
    """Protect current and preferred scalar names during column editing."""
    return set(named_value_by_display_name) | {
        f"{SCALAR_NAMESPACES[row['kind']]}.{row['name']}"
        for row in named_values
    }


def on_item_label_notify_editing(editable_label, editing):
    global x_data
    if Gtk.EditableLabel.get_editing(editable_label):
        return

    item = Gtk.Button.get_parent(editable_label)
    old_name = item.name
    if metadata_name(old_name):
        return

    info = column_registry.get(old_name)
    if info is None:
        return
    label_text = Gtk.EditableLabel.get_text(editable_label).strip()
    new_source_name, parsed_unit = split_tsv_header(label_text)
    new_unit = parsed_unit if new_source_name != label_text else info.unit
    if new_source_name == info.source_name and new_unit == info.unit:
        return
    if not new_source_name:
        Gtk.EditableLabel.set_text(editable_label, info.source_name)
        return

    # Resolve collisions before touching the DataFrame so a rename never
    # overwrites another column, including one with a different unit.
    try:
        new_info = column_registry.rename(old_name, new_source_name, new_unit,
                                          reserved_names=reserved_metadata_names())
    except ValueError as exception:
        Gtk.EditableLabel.set_text(editable_label, info.source_name)
        Gtk.Widget.set_tooltip_text(editable_label, str(exception))
        return
    new_name = new_info.internal_name
    DataFrame.rename(data_frame, columns={old_name: new_name}, inplace=True)
    styles[new_name] = styles.pop(old_name)
    colors[new_name] = colors.pop(old_name)

    y_button_left = item.y_button_left
    y_button_right = item.y_button_right
    left = Gtk.CheckButton.get_active(y_button_left)
    right = Gtk.CheckButton.get_active(y_button_right)

    remove_plot(old_name, axes_left)
    remove_plot(old_name, axes_right)

    if x_data.name == old_name:
        x_data = data_frame[new_name]
        Axes.set_xlabel(axes_left, x_data.name, fontsize=FONTSIZE)

    if left:
        add_plot(new_name, axes_left)
    if right:
        add_plot(new_name, axes_right)

    old_box = Gtk.Widget.get_parent(item)
    old_expander = Gtk.Widget.get_parent(old_box)
    if isinstance(old_expander, Gtk.Expander):
        buttons_box = Gtk.Widget.get_parent(old_expander)
    else:
        old_expander = None
        buttons_box = old_box

    parent_box = selector_parent_box(buttons_box, new_name)
    if parent_box is not old_box:
        Gtk.Box.remove(old_box, item)
        Gtk.Box.append(parent_box, item)
        if old_expander is not None:
            if Gtk.Widget.get_first_child(old_box) is None:
                Gtk.Box.remove(buttons_box, old_expander)

    item.name = new_name
    if label_text != new_info.source_name:
        Gtk.EditableLabel.set_text(editable_label, new_info.source_name)
    if hasattr(item, "unit_label"):
        Gtk.Label.set_text(item.unit_label, display_unit(new_info.unit))
    Gtk.Widget.set_tooltip_text(editable_label,
                                f"Expression name: {new_name}")
    redraw_plots()
    return


def on_style_button_click(style_button):
    name = get_button_name(style_button)

    styles[name] = next(styles_cycle)

    left = False
    right = False

    for line in Axes.get_lines(axes_left):
        if Line2D.get_label(line) == name:
            left = True
            break
    for line in Axes.get_lines(axes_right):
        if Line2D.get_label(line) == name:
            right = True
            break

    reset_plot(name, left, right)
    return


def on_color_button_click(color_button):
    item = Gtk.Button.get_parent(color_button)
    name = item.name

    colors[name] = next(colors_cycle)
    info = column_registry.get(name)
    if info is not None:
        info.color = colors[name]

    left = False
    right = False

    for line in Axes.get_lines(axes_left):
        if Line2D.get_label(line) == name:
            left = True
            break
    for line in Axes.get_lines(axes_right):
        if Line2D.get_label(line) == name:
            right = True
            break

    reset_plot(name, left, right)
    return


def on_delete_button_click(delete_button):
    global data_frame

    item = Gtk.Button.get_parent(delete_button)
    name = item.name

    if metadata_name(name):
        return

    if name != x_data.name:
        DataFrame.drop(data_frame, name, axis=1, inplace=True)

        del colors[name]
        del styles[name]
        column_registry.remove(name)

        remove_plot(name, axes_left)
        remove_plot(name, axes_right)
        redraw_plots(autoscale_y=True)

        parent_box = Gtk.Widget.get_parent(item)
        parent_expander = Gtk.Widget.get_parent(parent_box)
        Gtk.Box.remove(parent_box, item)
        if isinstance(parent_expander, Gtk.Expander):
            if Gtk.Widget.get_first_child(parent_box) is None:
                buttons_box = Gtk.Widget.get_parent(parent_expander)
                Gtk.Box.remove(buttons_box, parent_expander)
    return


def get_button_name(button):
    item = Gtk.Button.get_parent(button)
    return item.name


def on_x_button_toggled(x_button):
    global x_data

    name = get_button_name(x_button)
    active = Gtk.CheckButton.get_active(x_button)

    if not active:
        return

    if metadata_name(name):
        return

    x_data = data_frame[name]

    plotted_left, plotted_right = clean_plotted_get_list()

    for name in plotted_left:
        add_plot(name, axes_left)
    for name in plotted_right:
        add_plot(name, axes_right)

    Axes.set_xlabel(axes_left, x_data.name, fontsize=FONTSIZE)
    redraw_plots(full=True)
    return


def on_y_button_toggled(y_button):
    name = get_button_name(y_button)

    axes = y_button.axes
    active = Gtk.CheckButton.get_active(y_button)
    is_ref = any(p.startswith("ref_") or p.startswith("reference") for p in str.split(name, "."))

    if active:
        if is_ref:
            styles[name] = "dotted"
        else:
            if axes is axes_left:
                styles[name] = "solid"
            else:
                styles[name] = "dashed"
        add_plot(name, axes)
    else:
        remove_plot(name, axes)

    redraw_plots(autoscale_y=True)
    return


def add_expression_name(local_dict, name, value, prefix=""):
    if str(name).isidentifier() and not keyword.iskeyword(str(name)):
        if name not in local_dict:
            local_dict[name] = value

    safe_name = re.sub(r"\W", "_", str(name))
    if safe_name == "" or safe_name[0].isdigit():
        safe_name = f"_{safe_name}"
    if keyword.iskeyword(safe_name):
        safe_name = f"{safe_name}_"
    if prefix != "":
        safe_name = f"{prefix}_{safe_name}"
    if safe_name not in local_dict:
        local_dict[safe_name] = value
    return


def on_entry_activate(entry):
    global data_frame

    buffer = Gtk.Entry.get_buffer(entry)
    text = Gtk.EntryBuffer.get_text(buffer)

    try:
        if text in data_frame.columns:
            raise ValueError(f"Column {text!r} already exists")
        local_dict = DataFrame.to_dict(data_frame, orient='series')

        for name in data_frame.columns:
            add_expression_name(local_dict, name, data_frame[name])

        # Register aliases only if a single scalar owns the alias. Columns
        # take precedence; exact names in backticks are always available.
        aliases = {}
        for named_value in named_values:
            value = named_value["value"]
            name = named_value["name"]
            display_name = named_value["display_name"]
            candidates = {}
            add_expression_name(candidates, name, value)
            add_expression_name(candidates, display_name, value)
            add_expression_name(candidates, name, value, named_value["kind"])
            for alias in candidates:
                aliases.setdefault(alias, []).append(value)
        for alias, values in aliases.items():
            if len(values) == 1:
                local_dict.setdefault(alias, values[0])

        replacements = {}

        def replace_match(match):
            name = match.group(1)
            if name not in replacements:
                placeholder = f"__csv_plotter_name_{len(replacements)}"
                if name in data_frame.columns:
                    local_dict[placeholder] = data_frame[name]
                elif name in named_value_by_display_name:
                    local_dict[placeholder] = (
                        named_value_by_display_name[name]["value"])
                else:
                    resolved = column_registry.resolve_reference(name)
                    if resolved is not None:
                        local_dict[placeholder] = data_frame[resolved]
                    else:
                        matches = [row for row in named_values if row["name"] == name]
                        if len(matches) > 1:
                            raise ValueError(f"Ambiguous scalar {name!r}; use its plot name")
                        if not matches:
                            raise KeyError(name)
                        local_dict[placeholder] = matches[0]["value"]
                replacements[name] = placeholder
            return replacements[name]

        expression = re.sub(r"`([^`]+)`", replace_match, text)
        value = pd.eval(expression, local_dict=local_dict)

        if np.isscalar(value):
            value = np.full(len(data_frame.index), value, dtype=np.float64)
        if isinstance(value, np.ndarray):
            value = pd.Series(value, index=data_frame.index)
        if not isinstance(value, pd.Series):
            value = pd.Series(value, index=data_frame.index)
        if len(value) != len(data_frame.index):
            raise ValueError(
                f"Expression produced {len(value)} rows, "
                f"expected {len(data_frame.index)}")
        info = column_registry.add(text, reserved_names=reserved_metadata_names())
        data_frame[info.internal_name] = value
    except Exception as exception:
        title = Gtk.Label(label="Error evaluating expression")
        message = Gtk.Label(label=str(exception))

        Gtk.Widget.set_margin_start(message, 50)
        Gtk.Widget.set_margin_end(message, 50)
        Gtk.Widget.set_margin_bottom(message, 30)
        Gtk.Widget.set_margin_top(message, 30)

        header_bar = Gtk.HeaderBar()
        Gtk.HeaderBar.set_title_widget(header_bar, title)

        message_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        Gtk.Box.append(message_box, header_bar)
        Gtk.Box.append(message_box, message)

        new_window = Gtk.Window(transient_for=window)
        Gtk.Window.set_child(new_window, message_box)
        Gtk.Window.set_visible(new_window, True)
        return

    Gtk.Entry.set_text(entry, "")

    viewport = Gtk.ScrolledWindow.get_child(entry.selection_scroll)
    buttons_box = Gtk.Viewport.get_child(viewport)

    name = data_frame.columns[-1]
    ns = str.split(name, ".")[0]

    is_ref = any(p.startswith("ref_") or p.startswith("reference") for p in str.split(name, "."))

    if is_ref:
        colors[name] = "black"
        styles[name] = "dotted"
    else:
        color_assigned = False
        for col in data_frame.columns[:-1]:
            if str.split(col, ".")[0] == ns:
                col_is_ref = any(p.startswith("ref_") or p.startswith("reference") for p in str.split(col, "."))
                if not col_is_ref:
                    colors[name] = colors[col]
                    color_assigned = True
                    break

        if not color_assigned:
            colors[name] = next(colors_cycle)

        styles[name] = "dashed"

    parent_box = selector_parent_box(buttons_box, name)
    add_buttons(name, parent_box, left=False, right=True)

    add_plot(name, axes_right)
    redraw_plots(autoscale_y=True)
    return


def reset_plot(name, left, right):
    if left:
        remove_plot(name, axes_left)
        add_plot(name, axes_left)
    if right:
        remove_plot(name, axes_right)
        add_plot(name, axes_right)

    redraw_plots()
    return


def remove_plot(name, axes):
    for line in Axes.get_lines(axes):
        if Line2D.get_label(line) == name:
            Line2D.remove(line)
            break
    return


def put_legends():
    plotted_left = []
    for line in Axes.get_lines(axes_left):
        list.append(plotted_left, line)

    names_left = [Line2D.get_label(line) for line in plotted_left]

    if len(plotted_left) > 0:
        Axes.legend(axes_left, plotted_left, names_left, fontsize=FONTSIZE, loc="upper left", bbox_to_anchor=(0.0, -0.1))
    else:
        legend_left = Axes.get_legend(axes_left)
        if legend_left is not None:
            legend_left.remove()

    plotted_right = []
    for line in Axes.get_lines(axes_right):
        list.append(plotted_right, line)

    names_right = [Line2D.get_label(line) for line in plotted_right]

    if len(plotted_right) > 0:
        Axes.legend(axes_right, plotted_right, names_right, fontsize=FONTSIZE, loc="upper right", bbox_to_anchor=(1.0, -0.1))
    else:
        legend_right = Axes.get_legend(axes_right)
        if legend_right is not None:
            legend_right.remove()

    return


def custom_ticks(axes):
    Axes.locator_params(axes, axis="y", tight=True, nbins=4)
    Axes.locator_params(axes, axis="x", tight=True, nbins=5)
    return


def rescale_visible_y(plot_axes=None, x_limits=None):
    if plot_axes is None:
        plot_axes = (axes_left, axes_right)
    if x_limits is None:
        x_limits = Axes.get_xlim(axes_left)

    x_min, x_max = sorted(x_limits)
    for axes in plot_axes:
        y_min = None
        y_max = None
        for line in Axes.get_lines(axes):
            if not Line2D.get_visible(line):
                continue
            x_values = np.asarray(Line2D.get_xdata(line, orig=False))
            y_values = np.asarray(Line2D.get_ydata(line, orig=False))
            if x_values.size != y_values.size:
                continue
            visible = ((x_values >= x_min) & (x_values <= x_max)
                       & np.isfinite(x_values) & np.isfinite(y_values))
            if not np.any(visible):
                continue
            line_y_min = np.min(y_values[visible])
            line_y_max = np.max(y_values[visible])
            y_min = line_y_min if y_min is None else min(y_min, line_y_min)
            y_max = line_y_max if y_max is None else max(y_max, line_y_max)

        if y_min is None:
            continue
        y_min, y_max = axes.yaxis.get_major_locator().nonsingular(
            y_min, y_max)
        margin = Axes.margins(axes)[1]
        padding = (y_max - y_min) * margin
        Axes.set_ylim(axes, y_min - padding, y_max + padding)
    return


def redraw_plots(full=False, autoscale_y=False):
    configure_y_axis_labels_and_ticks()

    Axes.set_xmargin(axes_left, 0.01)
    Axes.set_xmargin(axes_right, 0.01)
    Axes.set_ymargin(axes_left, 0.02)
    Axes.set_ymargin(axes_right, 0.2)

    if full:
        Axes.relim(axes_left)
        Axes.relim(axes_right)
        Axes.autoscale(axes_left)
        Axes.autoscale(axes_right)
    elif autoscale_y:
        rescale_visible_y()

    custom_ticks(axes_left)
    custom_ticks(axes_right)
    put_legends()

    FigureCanvas.draw(canvas)
    if (plot_notebook is not None
            and not data_frame.empty
            and Gtk.Notebook.get_current_page(plot_notebook)
            == spectrum_page_index):
        redraw_spectrum()
    return


def add_plot(name, axes):
    global styles

    if name in named_value_by_display_name:
        named_value = named_value_by_display_name[name]
        values = np.full(len(data_frame.index), named_value["value"],
                         dtype=np.float64)
        y = pd.Series(values, index=data_frame.index, name=name)
    else:
        y = data_frame[name]

    linestyle = styles[name]
    color = colors[name]

    if x_data.is_monotonic_increasing:
        Axes.plot(axes, x_data, y, label=name,
                  linestyle=linestyle, color=color, alpha=0.9, linewidth=2)
    else:
        Axes.plot(axes, x_data, y, 'o', label=name,
                  markersize=1.5, color=color)
    return


if __name__ == "__main__":
    program = os.path.basename(sys.argv[0])
    application = Gtk.Application(application_id="com.example.plotter")
    Gtk.Application.connect(application, 'activate', on_application_activation)
    Gtk.Application.run(application, None)

    sys.exit(0)
