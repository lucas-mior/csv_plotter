import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_gtk3 import FigureCanvasGTK3, NavigationToolbar2GTK3
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

def error(message):
    print(f"{program}: {message}", file=sys.stderr)
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

    x = df.iloc[:, 0]

    fig, ax = plt.subplots()
    for column in df.columns:
        if column != x.name:
            y = df[column]
            ax.plot(x, y, label=column)

    ax.set_title(f"{filename}")
    ax.legend()

    win = Gtk.Window()
    win.connect("destroy", Gtk.main_quit)
    win.set_default_size(600, 400)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    canvas = FigureCanvasGTK3(fig)
    toolbar = NavigationToolbar2GTK3(canvas)

    box.pack_start(canvas, False, False, 1)
    box.pack_start(toolbar, False, False, 0)

    win.add(box)

    win.show_all()
    Gtk.main()
