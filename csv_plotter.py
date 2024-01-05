import os
import sys
import pandas as pd
import numpy as np

import gi
import time
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

from matplotlib.backends.backend_gtk4 \
    import NavigationToolbar2GTK4 as NavigationToolbar

from matplotlib.backends.backend_gtk4agg \
    import FigureCanvasGTK4Agg as FigureCanvas
from matplotlib.figure import Figure


filename = None


def set_margins(widget):
    size = 5
    widget.set_margin_start(size)
    widget.set_margin_end(size)
    widget.set_margin_top(size)
    widget.set_margin_bottom(size)
    return


def on_open_response(dialog, async_result, data):
    global filename, window, df, axes, canvas

    if dialog:
        gfile = dialog.open_finish(result=async_result)
        if gfile is None:
            print("Error getting file\n", file=sys.stderr)
            exit(1)
        filename = gfile.get_path()

    df = None
    try:
        df = pd.read_csv(filename)
    except Exception:
        print(f"Error reading {filename}", file=sys.stderr)
        exit(1)
    if df is None:
        print(f"Error reading {filename}", file=sys.stderr)
        exit(1)

    df.insert(0, 'Row', df.reset_index().index)
    name = os.path.basename(filename)
    window.set_title(f"{program} - {name}")
    x = df.iloc[:, 0]

    figure = Figure(layout="constrained")
    canvas = FigureCanvas(figure)
    toolbar = NavigationToolbar(canvas)
    axes = figure.add_subplot(111)
    for i, column in enumerate(df.columns[1:]):
        y = df[column]
        axes.plot(x, y, label=column)
        if i >= 10:
            break

    axes.set_title(f"{name}")
    axes.legend()
    axes.set_xlabel(x.name)

    plot_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    set_margins(plot_box)
    Gtk.Box.append(plot_box, toolbar)
    Gtk.Box.append(plot_box, canvas)

    config_pane = Gtk.Paned.new(orientation=Gtk.Orientation.VERTICAL)
    x_selection = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    set_margins(x_selection)
    x_selection_scroll = Gtk.ScrolledWindow()
    x_selection_scroll.set_vexpand(True)
    x_selection_boxes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    y_selection = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    set_margins(y_selection)
    y_selection_scroll = Gtk.ScrolledWindow()
    y_selection_scroll.set_vexpand(True)
    y_selection_boxes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    x_label = Gtk.Label(label="Select X axis")
    set_margins(x_label)
    Gtk.Box.append(x_selection, x_label)
    y_label = Gtk.Label(label="Select columns to plot")
    set_margins(y_label)
    Gtk.Box.append(y_selection, y_label)

    name_first = df.columns[0]
    toggle_button = Gtk.ToggleButton(label=name_first, group=None)
    toggle_button.connect("toggled", on_toggle_button_toggled)
    toggle_button.set_active(True)
    group = toggle_button
    Gtk.Box.append(x_selection_boxes, toggle_button)

    check_button = Gtk.CheckButton(label=name_first, active=False)
    check_button.connect("toggled", on_check_button_toggled)
    Gtk.Box.append(y_selection_boxes, check_button)

    for i, column in enumerate(df.columns[1:]):
        toggle_button = Gtk.ToggleButton(label=column, group=group)
        toggle_button.connect("toggled", on_toggle_button_toggled)
        Gtk.Box.append(x_selection_boxes, toggle_button)

        check_button = Gtk.CheckButton(label=column, active=(i <= 10))
        check_button.connect("toggled", on_check_button_toggled)
        Gtk.Box.append(y_selection_boxes, check_button)

    x_selection_scroll.set_child(x_selection_boxes)
    y_selection_scroll.set_child(y_selection_boxes)
    Gtk.Box.append(x_selection, x_selection_scroll)
    Gtk.Box.append(y_selection, y_selection_scroll)
    x_selection_scroll.set_policy(Gtk.PolicyType.NEVER,
                                  Gtk.PolicyType.AUTOMATIC)
    y_selection_scroll.set_policy(Gtk.PolicyType.NEVER,
                                  Gtk.PolicyType.AUTOMATIC)

    config_pane.set_start_child(x_selection)
    config_pane.set_end_child(y_selection)
    config_pane.set_wide_handle(True)

    window_pane = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
    window_pane.set_start_child(plot_box)
    window_pane.set_end_child(config_pane)
    window_pane.set_wide_handle(True)

    plot_box.set_size_request(900, 900)

    window.set_child(window_pane)
    window.show()


def on_activate(app):
    global axes, canvas, x, df, window
    window = Gtk.ApplicationWindow(application=app)
    window.set_default_size(1200, 900)

    if len(sys.argv) < 2:
        dialog = Gtk.FileDialog(title=f"{program} - Choose a CSV file")
        dialog.open(
            parent=window,
            cancellable=None,
            callback=on_open_response,
            user_data=None,
        )
    else:
        filename = sys.argv[1]
    return


def on_toggle_button_toggled(toggle_button):
    global axes, canvas, x, df
    column = toggle_button.get_label()
    active = toggle_button.get_active()

    if active:
        x = df[column]

    plotted = []
    for line in axes.get_lines():
        list.append(plotted, line.get_label())
        line.remove()

    axes.set_prop_cycle(None)

    for column in df.columns:
        if column in plotted:
            y = df[column]
            axes.plot(x, y, label=column)

    axes.relim()
    axes.autoscale()
    axes.legend()
    axes.set_xlabel(x.name)
    canvas.draw()
    return


def on_check_button_toggled(check_button):
    global axes, canvas, x, df

    column = check_button.get_label()
    active = check_button.get_active()

    if not active:
        for line in axes.get_lines():
            if line.get_label() == column:
                line.remove()
                break
    else:
        y = df[column]
        axes.plot(x, y, label=column)

    axes.relim()
    axes.autoscale()
    axes.legend()
    canvas.draw()
    return


if __name__ == "__main__":
    program = os.path.basename(sys.argv[0])
    app = Gtk.Application(application_id=f"{program}")
    app.connect('activate', on_activate)
    app.run(None)

    exit(0)
