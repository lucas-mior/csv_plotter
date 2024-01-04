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
    window = Gtk.ApplicationWindow(application=app)
    window.set_default_size(400, 300)
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

    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    canvas = FigureCanvas(figure)
    canvas.set_hexpand(True)
    canvas.set_vexpand(True)

    toolbar = NavigationToolbar(canvas)
    vbox.append(toolbar)
    vbox.append(canvas)

    side_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    label = Gtk.Label(label="Side Box")
    side_box.append(label)

    paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
    window.set_child(paned)

    paned.set_start_child(vbox)
    paned.set_end_child(side_box)

    window.show()
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
