#!/usr/bin/python

import os
import sys
import pandas as pd
import numpy as np

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

import matplotlib
from matplotlib.backends.backend_gtk4 \
    import NavigationToolbar2GTK4 as NavigationToolbar

from matplotlib.backends.backend_gtk4agg \
    import FigureCanvasGTK4Agg as FigureCanvas
from matplotlib.figure import Figure


filename = None


def plot_name_nplots(name, nplots):
    global axes_left, canvas, x, df

    y = df[name]
    linestyle = "solid" if nplots < 6 else "dashdot"
    axes_left.plot(x, y, linestyle=linestyle, label=name)
    return


def set_margins(widget):
    size = 5
    widget.set_margin_start(size)
    widget.set_margin_end(size)
    widget.set_margin_top(size)
    widget.set_margin_bottom(size)
    return


def on_entry_activate(entry):
    buffer = Gtk.Entry.get_buffer(entry)
    text = Gtk.EntryBuffer.get_text(buffer)
    print("on_entry_activate: ", text)
    local_dict = df.to_dict(orient='series')
    pd.eval(text, local_dict=local_dict, target=df, inplace=True)
    return


def on_open_response(dialog, async_result, data):
    global filename, window, df, axes_left, canvas, x

    if dialog is not None:
        gfile = dialog.open_finish(result=async_result)
        if gfile is None:
            print("Error getting file", file=sys.stderr)
            sys.exit(1)
        filename = gfile.get_path()

    df = None
    try:
        df = pd.read_csv(filename)
    except Exception:
        print(f"Error reading {filename}", file=sys.stderr)
        sys.exit(1)
    if df is None:
        print(f"Error reading {filename}", file=sys.stderr)
        sys.exit(1)

    df.insert(0, 'Row', df.reset_index().index)
    x = df.iloc[:, 0]

    filename = os.path.basename(filename)
    Gtk.ApplicationWindow.set_title(window, f"{program} - {filename}")

    figure = Figure(layout="constrained")
    canvas = FigureCanvas(figure)
    canvas.set_hexpand(True)
    canvas.set_vexpand(True)
    toolbar = NavigationToolbar(canvas)
    axes_left = figure.add_subplot(111)
    # axes_right = axes_left.twinx()
    for i, name in enumerate(df.columns[1:]):
        plot_name_nplots(name, i)
        if i >= 10:
            break

    axes_left.set_title(f"{filename}")
    axes_left.legend()
    axes_left.set_xlabel(x.name)
    matplotlib.rcParams['lines.linewidth'] = 2

    plot_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    set_margins(plot_box)

    Gtk.Box.append(plot_box, toolbar)
    Gtk.Box.append(plot_box, canvas)

    x_selection_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    y_selection_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    set_margins(x_selection_box)
    set_margins(y_selection_box)

    x_buttons_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    y_buttons_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    x_label = Gtk.Label(label="Select X axis")
    y_label = Gtk.Label(label="Select columns to plot")

    Gtk.Box.append(x_selection_box, x_label)
    Gtk.Box.append(y_selection_box, y_label)

    set_margins(x_label)
    set_margins(y_label)

    name_first = df.columns[0]
    x_button = Gtk.ToggleButton(label=name_first, group=None)
    y_button = Gtk.CheckButton(label=name_first, active=False)

    Gtk.ToggleButton.connect(x_button, "toggled", on_x_button_toggled)
    Gtk.ToggleButton.set_active(x_button, True)
    group = x_button
    Gtk.CheckButton.connect(y_button, "toggled", on_y_button_toggled)

    Gtk.Box.append(x_buttons_box, x_button)
    Gtk.Box.append(y_buttons_box, y_button)

    for i, name in enumerate(df.columns[1:]):
        x_button = Gtk.ToggleButton(label=name, group=group)
        y_button = Gtk.CheckButton(label=name, active=(i <= 10))

        Gtk.ToggleButton.connect(x_button, "toggled", on_x_button_toggled)
        Gtk.CheckButton.connect(y_button, "toggled", on_y_button_toggled)

        Gtk.Box.append(x_buttons_box, x_button)
        Gtk.Box.append(y_buttons_box, y_button)

    x_buttons_scroll = Gtk.ScrolledWindow()
    y_buttons_scroll = Gtk.ScrolledWindow()

    Gtk.ScrolledWindow.set_vexpand(x_buttons_scroll, True)
    Gtk.ScrolledWindow.set_vexpand(y_buttons_scroll, True)
    Gtk.ScrolledWindow.set_policy(x_buttons_scroll,
                                  hscrollbar_policy=Gtk.PolicyType.NEVER,
                                  vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
    Gtk.ScrolledWindow.set_policy(y_buttons_scroll,
                                  hscrollbar_policy=Gtk.PolicyType.NEVER,
                                  vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)

    Gtk.ScrolledWindow.set_child(x_buttons_scroll, x_buttons_box)
    Gtk.ScrolledWindow.set_child(y_buttons_scroll, y_buttons_box)

    Gtk.Box.append(x_selection_box, x_buttons_scroll)
    Gtk.Box.append(y_selection_box, y_buttons_scroll)
    new_entry = Gtk.Entry()
    Gtk.Box.append(y_selection_box, new_entry)
    Gtk.Entry.connect(new_entry, "activate", on_entry_activate)

    config_pane = Gtk.Paned.new(orientation=Gtk.Orientation.VERTICAL)
    Gtk.Paned.set_wide_handle(config_pane, True)

    Gtk.Paned.set_start_child(config_pane, x_selection_box)
    Gtk.Paned.set_end_child(config_pane, y_selection_box)

    Gtk.Paned.set_shrink_start_child(config_pane, False)
    Gtk.Paned.set_shrink_end_child(config_pane, False)

    window_pane = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
    Gtk.Paned.set_wide_handle(window_pane, True)
    Gtk.Paned.set_position(window_pane, 900)

    Gtk.Paned.set_start_child(window_pane, plot_box)
    Gtk.Paned.set_end_child(window_pane, config_pane)

    Gtk.Paned.set_shrink_start_child(window_pane, False)
    Gtk.Paned.set_shrink_end_child(window_pane, False)

    Gtk.ApplicationWindow.set_child(window, window_pane)
    Gtk.ApplicationWindow.set_visible(window, True)
    return


def on_activate(app):
    global axes_left, canvas, x, df, window, filename
    window = Gtk.ApplicationWindow(application=app)
    Gtk.ApplicationWindow.set_default_size(window, 1200, 900)

    if len(sys.argv) < 2:
        dialog = Gtk.FileDialog(title=f"{program} - Choose a CSV file")
        dialog.open(window, None, on_open_response, None)
    else:
        filename = sys.argv[1]
        on_open_response(None, None, None)
    return


def on_x_button_toggled(x_button):
    global axes_left, canvas, x, df
    name = Gtk.ToggleButton.get_label(x_button)
    active = Gtk.ToggleButton.get_active(x_button)

    if not active:
        return

    x = df[name]

    plotted = []
    for line in axes_left.get_lines():
        list.append(plotted, line.get_label())
        line.remove()

    axes_left.set_prop_cycle(None)

    for i, name in enumerate(plotted):
        plot_name_nplots(name, i)

    axes_left.relim()
    axes_left.autoscale()
    axes_left.legend()
    axes_left.set_xlabel(x.name)
    canvas.draw()
    return


def on_y_button_toggled(y_button):
    global axes_left, canvas, x, df

    name = Gtk.CheckButton.get_label(y_button)
    active = Gtk.CheckButton.get_active(y_button)

    plotted = axes_left.get_lines()

    if not active:
        for line in plotted:
            if line.get_label() == name:
                line.remove()
                break
    else:
        plot_name_nplots(name, len(plotted))

    axes_left.relim()
    axes_left.autoscale()
    axes_left.legend()
    canvas.draw()
    return


if __name__ == "__main__":
    program = os.path.basename(sys.argv[0])
    app = Gtk.Application(application_id=f"{program}")
    Gtk.Application.connect(app, 'activate', on_activate)
    Gtk.Application.run(app, None)

    sys.exit(0)
