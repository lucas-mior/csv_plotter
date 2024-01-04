import sys
import pandas as pd
import numpy as np

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

from matplotlib.backends.backend_gtk4 \
    import NavigationToolbar2GTK4 as NavigationToolbar

from matplotlib.backends.backend_gtk4agg \
    import FigureCanvasGTK4Agg as FigureCanvas
from matplotlib.figure import Figure

def error(message):
    print(f"{program}: {message}", file=sys.stderr)
    return


def on_activate(app):
    global axes, canvas, x
    window = Gtk.ApplicationWindow(application=app)
    window.set_default_size(900, 600)
    window.set_title(f"{program} - {filename}")

    df = app.df
    x = df.iloc[:, 0]

    figure = Figure()
    axes = figure.add_subplot(111)
    for column in df.columns:
        if column != x.name:
            y = df[column]
            axes.plot(x, y, label=column)

    axes.set_title(f"{filename}")
    axes.legend()

    plot_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    canvas = FigureCanvas(figure)
    canvas.set_hexpand(True)
    canvas.set_vexpand(True)

    toolbar = NavigationToolbar(canvas)
    plot_box.append(toolbar)
    plot_box.append(canvas)

    config_box = Gtk.Paned.new(orientation=Gtk.Orientation.VERTICAL)
    y_selection = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    x_selection = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    x_label = Gtk.Label(label="Select X axis")
    x_selection.append(x_label)

    group = None
    for column in df.columns:
        toggle_button = Gtk.ToggleButton(label=column, group=group)
        toggle_button.connect("toggled", toggle_button_toggled)
        x_selection.append(toggle_button)
        if group is None:
            group = toggle_button
            toggle_button.set_active(True)

    y_label = Gtk.Label(label="Select columns to plot")
    y_selection.append(y_label)
    for column in df.columns:
        check_button = Gtk.CheckButton(label=column, active=True)
        check_button.connect("toggled", check_button_toggled)
        y_selection.append(check_button)

    config_box.set_start_child(x_selection)
    config_box.set_end_child(y_selection)

    paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)

    paned.set_start_child(plot_box)
    paned.set_end_child(config_box)

    window.set_child(paned)
    window.show()
    return


def toggle_button_toggled(toggle_button):
    column = toggle_button.get_label()
    active = toggle_button.get_active()
    print(f"user toggled: {column} : {active}")
    return


def check_button_toggled(check_button):
    global axes, canvas, x

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
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <file.csv>", file=sys.stderr)
        exit(1)

    program = sys.argv[0]
    filename = sys.argv[1]

    df = None
    try:
        df = pd.read_csv(filename)
    except Exception:
        error(f"Error reading {filename}")
        exit(1)
    if df is None:
        error(f"Error reading {filename}")
        exit(1)

    app = Gtk.Application(application_id=f"{program}")
    app.df = df
    app.connect('activate', on_activate)
    app.run(None)

    exit(0)
