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

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from gi.repository import Gio

import matplotlib
from matplotlib.backends.backend_gtk4 \
    import NavigationToolbar2GTK4 as NavigationToolbar

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
column_units = {}
hdf5_named_values = []
hdf5_named_value_by_display_name = {}
hdf5_simulation_metadata = []
hdf5_fit_metadata = []
hdf5_fit_inputs = []
HDF5_EXTENSIONS = (".h5", ".hdf5")


def on_application_activation(application):
    global window, filename, pre_plots

    window = Gtk.ApplicationWindow(application=application)
    Gtk.ApplicationWindow.set_default_size(window, 1400, 900)

    argc = len(sys.argv)

    if argc < 2:
        dialog = Gtk.FileDialog(title=f"{program} - Choose a CSV or HDF5 file")
        Gtk.FileDialog.open(dialog, window, None, on_have_filename_ready, None)
    else:
        filename = sys.argv[1]
        if argc > 2:
            pre_plots = str.split(sys.argv[2], ",")
        on_have_filename_ready(None, None, None)
    return


def on_have_filename_ready(dialog, async_result, data):
    global axes_left, axes_right, canvas, filebase, filename

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
    toolbar = NavigationToolbar(canvas)

    FigureCanvas.set_hexpand(canvas, True)
    FigureCanvas.set_vexpand(canvas, True)

    axes_left = Figure.add_subplot(figure, 111)
    Axes.grid(axes_left)
    axes_right = Axes.twinx(axes_left)

    plot_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    config_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    buttons_header = Gtk.Label(label="Select x axis and columns to plot")

    Gtk.Box.append(config_box, buttons_header)

    selection_scroll = Gtk.ScrolledWindow()
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
    Gtk.Box.append(toolbar_box, reload_button)
    Gtk.Box.append(toolbar_box, save_button)
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

    notebook = Gtk.Notebook()
    Gtk.Notebook.set_tab_pos(notebook, Gtk.PositionType.TOP)
    Gtk.Notebook.append_page(notebook, window_pane, Gtk.Label(label="Plot"))
    Gtk.Notebook.append_page(notebook, metadata_scroll,
                             Gtk.Label(label="Metadata"))

    Gtk.ApplicationWindow.set_child(window, notebook)
    Gtk.ApplicationWindow.set_visible(window, True)
    return


def filename_has_hdf5_extension(path):
    extension = os.path.splitext(path)[1]
    return extension.lower() in HDF5_EXTENSIONS


def read_hdf5_strings(hdf5_file, dataset_name, count=None):
    values = hdf5_file[dataset_name][()]
    strings = []
    for value in values:
        if isinstance(value, bytes):
            raw_text = value
        elif isinstance(value, np.bytes_):
            raw_text = bytes(value)
        else:
            strings.append(str(value))
            continue

        raw_text = raw_text.split(b"\0", maxsplit=1)[0]
        strings.append(raw_text.decode("utf-8"))

    if count is not None and len(strings) != count:
        raise ValueError(
            f"HDF5 dataset {dataset_name} has {len(strings)} entries, "
            f"expected {count}")
    return strings


def hdf5_dataset_exists(hdf5_file, dataset_name):
    return dataset_name in hdf5_file


def read_hdf5_float_vector(hdf5_file, dataset_name, count=None):
    values = np.array(hdf5_file[dataset_name], dtype=np.float64)
    if values.ndim != 1:
        raise ValueError(
            f"HDF5 /{dataset_name} dataset must have 1 dimension")
    if count is not None and len(values) != count:
        raise ValueError(
            f"HDF5 dataset /{dataset_name} has {len(values)} entries, "
            f"expected {count}")
    return values


def read_hdf5_named_values(hdf5_file, kind):
    names_path = f"{kind}_names"
    units_path = f"{kind}_units"
    values_path = f"{kind}_values"
    paths = [names_path, units_path, values_path]

    if not any(hdf5_dataset_exists(hdf5_file, path) for path in paths):
        return []
    if not all(hdf5_dataset_exists(hdf5_file, path) for path in paths):
        raise ValueError(f"HDF5 file has incomplete /{kind}_* metadata")

    names = read_hdf5_strings(hdf5_file, names_path)
    units = read_hdf5_strings(hdf5_file, units_path, len(names))
    values = read_hdf5_float_vector(hdf5_file, values_path, len(names))

    result = []
    for name, unit, value in zip(names, units, values):
        result.append({
            "kind": kind,
            "name": name,
            "unit": unit,
            "value": float(value),
        })
    return result


def read_hdf5_text_metadata(hdf5_file, prefix):
    names_path = f"{prefix}_metadata_names"
    values_path = f"{prefix}_metadata_values"
    paths = [names_path, values_path]

    if not any(hdf5_dataset_exists(hdf5_file, path) for path in paths):
        return []
    if not all(hdf5_dataset_exists(hdf5_file, path) for path in paths):
        raise ValueError(
            f"HDF5 file has incomplete /{prefix}_metadata_*")

    names = read_hdf5_strings(hdf5_file, names_path)
    values = read_hdf5_strings(hdf5_file, values_path, len(names))

    result = []
    for name, value in zip(names, values):
        result.append({
            "name": name,
            "value": value,
        })
    return result


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


def write_hdf5_named_values(hdf5_file, kind, named_values):
    values = [value for value in named_values if value["kind"] == kind]
    if len(values) == 0:
        return

    names = [value["name"] for value in values]
    units = [value["unit"] for value in values]
    data = np.array([value["value"] for value in values], dtype=np.float64)

    hdf5_file.create_dataset(f"{kind}_names", data=fixed_hdf5_strings(names))
    hdf5_file.create_dataset(f"{kind}_units", data=fixed_hdf5_strings(units))
    hdf5_file.create_dataset(f"{kind}_values", data=data)
    return


def configure_hdf5_named_values(named_values):
    global hdf5_named_values, hdf5_named_value_by_display_name

    hdf5_named_values = named_values
    hdf5_named_value_by_display_name = {}
    for named_value in hdf5_named_values:
        name = named_value["name"]
        if named_value["kind"] == "parameter":
            display_name = f"parameters.{name}"
        elif named_value["kind"] == "fit_parameter":
            display_name = f"fit_parameters.{name}"
        else:
            display_name = f"constants.{name}"
        named_value["display_name"] = display_name
        hdf5_named_value_by_display_name[display_name] = named_value
    return


def configure_hdf5_simulation_metadata(simulation_metadata):
    global hdf5_simulation_metadata

    hdf5_simulation_metadata = simulation_metadata
    return


def configure_hdf5_fit_metadata(fit_metadata):
    global hdf5_fit_metadata

    hdf5_fit_metadata = fit_metadata
    return


def configure_hdf5_fit_inputs(fit_inputs):
    global hdf5_fit_inputs

    hdf5_fit_inputs = fit_inputs
    return


def reload_file_contents():
    global data_frame, x_data, file_type, column_units

    data_frame = None
    configure_hdf5_named_values([])
    configure_hdf5_simulation_metadata([])
    configure_hdf5_fit_metadata([])
    configure_hdf5_fit_inputs([])
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
                if "data" not in hdf5_file:
                    raise ValueError(
                        "HDF5 file does not have a /data dataset")
                if "names" not in hdf5_file:
                    raise ValueError(
                        "HDF5 file does not have a /names dataset")

                data = np.array(hdf5_file["data"], dtype=np.float64)
                if data.ndim != 2:
                    raise ValueError(
                        "HDF5 /data dataset must have 2 dimensions")

                ncolumns = data.shape[1]
                names = read_hdf5_strings(hdf5_file, "names", ncolumns)
                if "units" in hdf5_file:
                    units = read_hdf5_strings(hdf5_file, "units", ncolumns)
                else:
                    units = [""]*ncolumns

                parameter_values = read_hdf5_named_values(
                    hdf5_file, "parameter")
                if len(parameter_values) != 0:
                    dataset_name = "parameter_default_values"
                    if hdf5_dataset_exists(hdf5_file, dataset_name):
                        values = read_hdf5_float_vector(
                            hdf5_file, dataset_name, len(parameter_values))
                        for metadata, value in zip(parameter_values, values):
                            metadata["default_value"] = float(value)

                fit_parameter_values = read_hdf5_named_values(
                    hdf5_file, "fit_parameter")
                if len(fit_parameter_values) != 0:
                    optional_fields = [
                        ("initial_value",
                         "fit_parameter_initial_values"),
                        ("lower_bound", "fit_parameter_lower_bounds"),
                        ("upper_bound", "fit_parameter_upper_bounds"),
                    ]
                    for field, dataset_name in optional_fields:
                        if not hdf5_dataset_exists(hdf5_file, dataset_name):
                            continue
                        values = read_hdf5_float_vector(
                            hdf5_file, dataset_name,
                            len(fit_parameter_values))
                        for metadata, value in zip(fit_parameter_values,
                                                   values):
                            metadata[field] = float(value)

                fit_input_names_path = "fit_input_names"
                intervals_path = "fit_input_knot_intervals"
                paths = [fit_input_names_path, intervals_path]

                if not any(hdf5_dataset_exists(hdf5_file, path)
                           for path in paths):
                    fit_inputs = []
                elif not all(hdf5_dataset_exists(hdf5_file, path)
                             for path in paths):
                    raise ValueError(
                        "HDF5 file has incomplete /fit_input_* metadata")
                else:
                    fit_input_names = read_hdf5_strings(
                        hdf5_file, fit_input_names_path)
                    intervals = read_hdf5_float_vector(
                        hdf5_file, intervals_path, len(fit_input_names))

                    fit_inputs = []
                    for name, interval in zip(fit_input_names, intervals):
                        fit_inputs.append({
                            "name": name,
                            "knot_interval": float(interval),
                        })

                named_values = []
                named_values += parameter_values
                named_values += read_hdf5_named_values(hdf5_file, "constant")
                named_values += fit_parameter_values
                simulation_metadata = read_hdf5_text_metadata(
                    hdf5_file, "simulation")
                fit_metadata = read_hdf5_text_metadata(hdf5_file, "fit")

            data_frame = pd.DataFrame(data, columns=names)
            column_units = dict(zip(names, units))
            configure_hdf5_named_values(named_values)
            configure_hdf5_simulation_metadata(simulation_metadata)
            configure_hdf5_fit_metadata(fit_metadata)
            configure_hdf5_fit_inputs(fit_inputs)
            file_type = "hdf5"
        else:
            data_frame = pd.read_csv(filename)
            column_units = {name: "" for name in data_frame.columns}
            file_type = "csv"
    except Exception as exception:
        print(f"Error reading {filename}: {exception}", file=sys.stderr)
        sys.exit(1)
    if data_frame is None:
        print(f"Error reading {filename}", file=sys.stderr)
        sys.exit(1)

    if "time" not in data_frame.columns:
        try:
            rows = DataFrame.reset_index(data_frame).index
            DataFrame.insert(data_frame, 0, 'Row', rows)
            column_units["Row"] = ""
        except Exception:
            pass
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
    for named_value in hdf5_named_values:
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
            if isinstance(cell, str):
                text_row.append(cell)
            elif np.isfinite(cell):
                text_row.append(f"{cell:.16g}")
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
            seconds = float(metadata_value)
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


def metadata_rows_for_kind(kind):
    rows = []
    for named_value in metadata_values_for_kind(kind):
        rows.append([
            named_value["name"],
            named_value["value"],
            named_value["unit"],
            named_value["display_name"],
        ])
    return rows


def reconfigure_metadata_tab(metadata_scroll):
    lines = ["Metadata"]

    append_metadata_text_section(lines, "File", ["Name", "Value"], [
        ["Filename", filename],
    ])

    if (len(hdf5_named_values) == 0
            and len(hdf5_simulation_metadata) == 0
            and len(hdf5_fit_metadata) == 0
            and len(hdf5_fit_inputs) == 0):
        lines.append("")
        if file_type == "hdf5":
            lines.append("This HDF5 file does not contain recognized metadata.")
        else:
            lines.append("CSV files do not contain metadata.")
    else:
        append_metadata_text_section(
            lines, "Simulation", ["Name", "Value"],
            run_metadata_rows(hdf5_simulation_metadata,
                              simulation_metadata_display_name))
        append_metadata_text_section(
            lines, "Fitting", ["Name", "Value"],
            run_metadata_rows(hdf5_fit_metadata, fit_metadata_display_name))

        rows = []
        for value in hdf5_fit_inputs:
            rows.append([
                value["name"],
                value["knot_interval"],
            ])
        append_metadata_text_section(
            lines, "Optimized inputs", ["Name", "Knot interval (s)"],
            rows)
        append_metadata_text_section(lines, "Parameters",
                                     ["Name", "Value", "Unit", "Plot name"],
                                     metadata_rows_for_kind("parameter"))

        rows = []
        for named_value in metadata_values_for_kind("fit_parameter"):
            rows.append([
                named_value["name"],
                named_value["value"],
                named_value.get("initial_value", ""),
                named_value.get("lower_bound", ""),
                named_value.get("upper_bound", ""),
                named_value["unit"],
                named_value["display_name"],
            ])
        append_metadata_text_section(
            lines, "Fitted parameters",
            ["Name", "Fitted", "Initial", "Lower", "Upper", "Unit",
             "Plot name"],
            rows)
        append_metadata_text_section(lines, "Constants",
                                     ["Name", "Value", "Unit", "Plot name"],
                                     metadata_rows_for_kind("constant"))

    text = "\n".join(lines) + "\n"
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
    return name in hdf5_named_value_by_display_name


def reconfigure_plots_and_buttons(selection_scroll):
    global x_button_group, data_frame, pre_plots

    buttons_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    namespace_boxes = {}
    ns_colors = {}

    names = [str(name) for name in data_frame.columns]
    for named_value in hdf5_named_values:
        names.append(named_value["display_name"])
    name_first = names[0]
    x_button_group = None

    ns_first = str.split(name_first, ".")[0]
    expander_first = Gtk.Expander(label=ns_first)
    ns_box_first = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    Gtk.Expander.set_expanded(expander_first, True)
    Gtk.Expander.set_child(expander_first, ns_box_first)
    Gtk.Box.append(buttons_box, expander_first)

    namespace_boxes[ns_first] = ns_box_first

    if any(p.startswith("ref_") or p.startswith("reference") for p in str.split(name_first, ".")):
        colors[name_first] = "black"
        styles[name_first] = "dotted"
    else:
        ns_colors[ns_first] = next(colors_cycle)
        colors[name_first] = ns_colors[ns_first]
        styles[name_first] = "solid"

    add_buttons(name_first, ns_box_first)

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

        if ns not in namespace_boxes:
            expander = Gtk.Expander(label=ns)
            ns_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            Gtk.Expander.set_expanded(expander, True)
            Gtk.Expander.set_child(expander, ns_box)
            Gtk.Box.append(buttons_box, expander)
            namespace_boxes[ns] = ns_box

        add_buttons(name, namespace_boxes[ns], left=left, right=right)

    pre_plots = []
    Axes.set_xlabel(axes_left, x_data.name, fontsize=FONTSIZE)
    configure_y_axis_labels_and_ticks()
    put_legends()

    Gtk.ScrolledWindow.set_child(selection_scroll, buttons_box)
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
        if metadata_name(name):
            named_value = hdf5_named_value_by_display_name.get(name)
            if named_value is None:
                unit = ""
            else:
                unit = named_value["unit"]
        else:
            unit = column_units.get(name, "")
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
    named_value = hdf5_named_value_by_display_name.get(name)
    if named_value is not None:
        item_label = Gtk.EditableLabel.new(named_value["name"])
    else:
        item_label = Gtk.EditableLabel.new(name)
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
    Gtk.EditableLabel.connect(item_label, "notify::editing", on_item_label_notify_editing)
    Gtk.Button.connect(style_button, "clicked", on_style_button_click)
    Gtk.Button.connect(color_button, "clicked", on_color_button_click)
    Gtk.Button.connect(delete_button, "clicked", on_delete_button_click)

    item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    item.name = name
    item.y_button_left = y_button_left
    item.y_button_right = y_button_right

    Gtk.Box.append(item, x_button)
    Gtk.Box.append(item, y_button_left)
    Gtk.Box.append(item, y_button_right)
    Gtk.Box.append(item, item_label)
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
    redraw_plots(full=True)
    return


def on_save_button_clicked(save_button):
    root = str.rsplit(filename, '.', maxsplit=1)[0]
    if file_type == "hdf5":
        newfile = root + "_new.h5"
    else:
        newfile = root + "_new.csv"

    try:
        if file_type == "hdf5":
            if h5py is None:
                raise ImportError("h5py is required to save HDF5 files")

            names = [str(name) for name in data_frame.columns]
            units = [column_units.get(name, "") for name in names]
            data = data_frame.to_numpy(dtype=np.float64)

            with h5py.File(newfile, "w") as hdf5_file:
                hdf5_file.create_dataset("data", data=data)
                hdf5_file.create_dataset("names",
                                         data=fixed_hdf5_strings(names))
                hdf5_file.create_dataset("units",
                                         data=fixed_hdf5_strings(units))

                values = [
                    value for value in hdf5_named_values
                    if value["kind"] == "parameter"
                ]
                if len(values) != 0:
                    write_hdf5_named_values(hdf5_file, "parameter", values)
                    if all("default_value" in value for value in values):
                        data = np.array(
                            [value["default_value"] for value in values],
                            dtype=np.float64)
                        hdf5_file.create_dataset("parameter_default_values",
                                                 data=data)

                write_hdf5_named_values(hdf5_file, "constant",
                                        hdf5_named_values)

                values = [
                    value for value in hdf5_named_values
                    if value["kind"] == "fit_parameter"
                ]
                if len(values) != 0:
                    write_hdf5_named_values(hdf5_file, "fit_parameter",
                                            values)

                    optional_fields = [
                        ("initial_value",
                         "fit_parameter_initial_values"),
                        ("lower_bound", "fit_parameter_lower_bounds"),
                        ("upper_bound", "fit_parameter_upper_bounds"),
                    ]
                    for field, dataset_name in optional_fields:
                        if not all(field in value for value in values):
                            continue
                        data = np.array(
                            [value[field] for value in values],
                            dtype=np.float64)
                        hdf5_file.create_dataset(dataset_name, data=data)

                if len(hdf5_simulation_metadata) != 0:
                    metadata_names = [
                        value["name"] for value in hdf5_simulation_metadata
                    ]
                    metadata_values = [
                        value["value"] for value in hdf5_simulation_metadata
                    ]
                    hdf5_file.create_dataset(
                        "simulation_metadata_names",
                        data=fixed_hdf5_strings(metadata_names))
                    hdf5_file.create_dataset(
                        "simulation_metadata_values",
                        data=fixed_hdf5_strings(metadata_values))

                if len(hdf5_fit_metadata) != 0:
                    metadata_names = [
                        value["name"] for value in hdf5_fit_metadata
                    ]
                    metadata_values = [
                        value["value"] for value in hdf5_fit_metadata
                    ]
                    hdf5_file.create_dataset(
                        "fit_metadata_names",
                        data=fixed_hdf5_strings(metadata_names))
                    hdf5_file.create_dataset(
                        "fit_metadata_values",
                        data=fixed_hdf5_strings(metadata_values))

                if len(hdf5_fit_inputs) != 0:
                    fit_input_names = [
                        value["name"] for value in hdf5_fit_inputs
                    ]
                    intervals = np.array([
                        value["knot_interval"] for value in hdf5_fit_inputs
                    ], dtype=np.float64)
                    hdf5_file.create_dataset(
                        "fit_input_names",
                        data=fixed_hdf5_strings(fit_input_names))
                    hdf5_file.create_dataset("fit_input_knot_intervals",
                                             data=intervals)
        else:
            DataFrame.to_csv(data_frame, newfile, sep=',', index=False)
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


def on_item_label_notify_editing(editable_label, editing):
    global x_data
    if Gtk.EditableLabel.get_editing(editable_label):
        return

    item = Gtk.Button.get_parent(editable_label)
    old_name = item.name
    if metadata_name(old_name):
        return

    new_name = Gtk.EditableLabel.get_text(editable_label)

    DataFrame.rename(data_frame, columns={old_name: new_name}, inplace=True)
    styles[new_name] = styles.pop(old_name)
    colors[new_name] = colors.pop(old_name)
    column_units[new_name] = column_units.pop(old_name, "")

    y_button_left = item.y_button_left
    y_button_right = item.y_button_right

    left = Gtk.CheckButton.get_active(y_button_left)
    right = Gtk.CheckButton.get_active(y_button_right)

    remove_plot(old_name, axes_left)
    remove_plot(old_name, axes_right)

    if left:
        add_plot(new_name, axes_left)
    if right:
        add_plot(new_name, axes_right)

    if x_data.name == old_name:
        x_data.name = new_name
        Axes.set_xlabel(axes_left, x_data.name, fontsize=FONTSIZE)

    item.name = new_name
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
        if name in column_units:
            del column_units[name]

        remove_plot(name, axes_left)
        remove_plot(name, axes_right)
        redraw_plots(autoscale_y=True)

        parent_box = Gtk.Button.get_parent(delete_button)
        grand_parent = Gtk.Box.get_parent(parent_box)
        Gtk.Box.remove(grand_parent, parent_box)
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
        local_dict = DataFrame.to_dict(data_frame, orient='series')

        for name in data_frame.columns:
            add_expression_name(local_dict, name, data_frame[name])

        for named_value in hdf5_named_values:
            value = named_value["value"]
            name = named_value["name"]
            display_name = named_value["display_name"]
            add_expression_name(local_dict, name, value)
            add_expression_name(local_dict, display_name, value)
            add_expression_name(local_dict, name, value, named_value["kind"])

        replacements = {}

        def replace_match(match):
            name = match.group(1)
            if name not in replacements:
                placeholder = f"__csv_plotter_name_{len(replacements)}"
                if name in hdf5_named_value_by_display_name:
                    local_dict[placeholder] = (
                        hdf5_named_value_by_display_name[name]["value"])
                elif name in data_frame.columns:
                    local_dict[placeholder] = data_frame[name]
                else:
                    for named_value in hdf5_named_values:
                        if named_value["name"] == name:
                            local_dict[placeholder] = named_value["value"]
                            break
                    else:
                        raise KeyError(name)
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
        data_frame[text] = value
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
    column_units[name] = ""
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

    ns_box = None
    child = Gtk.Widget.get_first_child(buttons_box)

    while child is not None:
        if isinstance(child, Gtk.Expander):
            if Gtk.Expander.get_label(child) == ns:
                ns_box = Gtk.Expander.get_child(child)
                break
        child = Gtk.Widget.get_next_sibling(child)

    if ns_box is None:
        expander = Gtk.Expander(label=ns)
        ns_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        Gtk.Expander.set_expanded(expander, True)
        Gtk.Expander.set_child(expander, ns_box)
        Gtk.Box.append(buttons_box, expander)

    add_buttons(name, ns_box, left=False, right=True)

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


def redraw_plots(full=False, autoscale_y=False):
    configure_y_axis_labels_and_ticks()

    Axes.set_xmargin(axes_left, 0.01)
    Axes.set_xmargin(axes_right, 0.01)
    Axes.set_ymargin(axes_left, 0.02)
    Axes.set_ymargin(axes_right, 0.2)

    if full or autoscale_y:
        Axes.relim(axes_left)
        Axes.relim(axes_right)
    if full:
        Axes.autoscale(axes_left)
        Axes.autoscale(axes_right)
    elif autoscale_y:
        Axes.autoscale(axes_left, axis="y")
        Axes.autoscale(axes_right, axis="y")

    custom_ticks(axes_left)
    custom_ticks(axes_right)
    put_legends()

    FigureCanvas.draw(canvas)
    return


def add_plot(name, axes):
    global styles

    if name in hdf5_named_value_by_display_name:
        named_value = hdf5_named_value_by_display_name[name]
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
