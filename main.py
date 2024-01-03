import sys
import pandas as pd
import numpy as np

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

from matplotlib.backends.backend_gtk4 import \
    NavigationToolbar2GTK4 as NavigationToolbar
from matplotlib.backends.backend_gtk4agg import \
    FigureCanvasGTK4Agg as FigureCanvas
from matplotlib.figure import Figure

def error(message):
    print(f"{program}: {message}", file=sys.stderr)
    return


def on_activate(app):
    win = Gtk.ApplicationWindow(application=app)
    win.set_default_size(400, 300)
    win.set_title("Embedding in GTK4")

    df = app.df
    x = df.iloc[:, 0]

    fig = Figure()
    ax = fig.add_subplot(111)
    for column in df.columns:
        if column != x.name:
            y = df[column]
            ax.plot(x, y, label=column)

    ax.set_title(f"{filename}")
    ax.legend()

    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    win.set_child(vbox)

    canvas = FigureCanvas(fig)
    canvas.set_hexpand(True)
    canvas.set_vexpand(True)
    vbox.append(canvas)

    toolbar = NavigationToolbar(canvas)
    vbox.append(toolbar)

    win.show()
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
