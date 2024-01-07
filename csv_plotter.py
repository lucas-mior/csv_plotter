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


def on_application_activation(app):
    global window, filename

    window = Gtk.ApplicationWindow(application=app)
    Gtk.ApplicationWindow.set_default_size(window, 1200, 900)

    if len(sys.argv) < 2:
        dialog = Gtk.FileDialog(title=f"{program} - Choose a CSV file")
        dialog.open(window, None, on_have_filename_ready, None)
    else:
        filename = sys.argv[1]
        on_have_filename_ready(None, None, None)
    return


def on_have_filename_ready(dialog, async_result, data):
    global filename

    if dialog is not None:
        gfile = dialog.open_finish(result=async_result)
        if gfile is None:
            print("Error getting file", file=sys.stderr)
            sys.exit(1)
        filename = gfile.get_path()

    reload_file_contents()
    configure_window_once()
    return


def reload_file_contents():
    global df, x
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
    return


def configure_window_once():
    global axes_left, canvas

    filebase = os.path.basename(filename)
    Gtk.ApplicationWindow.set_title(window, f"{program} - {filebase}")

    figure = Figure(layout="constrained")
    canvas = FigureCanvas(figure)
    canvas.set_hexpand(True)
    canvas.set_vexpand(True)
    toolbar = NavigationToolbar(canvas)
    axes_left = Figure.add_subplot(figure, 111)
    axes_left.set_title(f"{filebase}")
    # axes_right = axes_left.twinx()

    plot_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    x_selection_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    y_selection_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    x_label = Gtk.Label(label="Select X axis")
    y_label = Gtk.Label(label="Select columns to plot")

    Gtk.Box.append(x_selection_box, x_label)
    Gtk.Box.append(y_selection_box, y_label)

    x_config_scroll = Gtk.ScrolledWindow()
    y_config_scroll = Gtk.ScrolledWindow()

    reload_button = Gtk.Button.new_from_icon_name("document-revert")
    Gtk.Button.connect(reload_button, "clicked", on_reload_button_clicked,
                       x_config_scroll, y_config_scroll)

    toolbar_box = Gtk.Box()
    Gtk.Box.append(toolbar_box, toolbar)
    Gtk.Box.append(toolbar_box, reload_button)

    Gtk.Box.append(plot_box, toolbar_box)
    Gtk.Box.append(plot_box, canvas)

    reinitialize_plots(x_config_scroll, y_config_scroll)

    Gtk.ScrolledWindow.set_vexpand(x_config_scroll, True)
    Gtk.ScrolledWindow.set_vexpand(y_config_scroll, True)
    Gtk.ScrolledWindow.set_policy(x_config_scroll,
                                  hscrollbar_policy=Gtk.PolicyType.NEVER,
                                  vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
    Gtk.ScrolledWindow.set_policy(y_config_scroll,
                                  hscrollbar_policy=Gtk.PolicyType.NEVER,
                                  vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)

    Gtk.Box.append(x_selection_box, x_config_scroll)
    Gtk.Box.append(y_selection_box, y_config_scroll)
    new_data_entry = Gtk.Entry()
    Gtk.Entry.set_placeholder_text(new_data_entry, "add a plot...")
    Gtk.Entry.connect(new_data_entry, "activate", on_entry_activate,
                      x_config_scroll, y_config_scroll)
    Gtk.Box.append(y_selection_box, new_data_entry)

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


def reinitialize_plots(x_config_scroll, y_config_scroll):
    global x_button_group

    for line in axes_left.get_lines():
        line.remove()

    x_buttons_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    y_buttons_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    name_first = df.columns[0]
    x_button_group = None
    add_buttons_xy(name_first, x_buttons_box, y_buttons_box,
                   xactive=True, yactive=False)

    for i, name in enumerate(df.columns[1:]):
        # TODO: dots bug expressions in pandas.eval(), find better solution
        new = str.replace(name, ".", "_")
        df.rename(columns={name: new}, inplace=True)

        if i < 10:
            add_plot_name_nplots(new)
        add_buttons_xy(new, x_buttons_box, y_buttons_box, yactive=i < 10)

    axes_left.legend()
    axes_left.set_xlabel(x.name)

    Gtk.ScrolledWindow.set_child(x_config_scroll, x_buttons_box)
    Gtk.ScrolledWindow.set_child(y_config_scroll, y_buttons_box)
    return


def add_buttons_xy(name, x_buttons_box, y_buttons_box,
                   xactive=False, yactive=False):
    global x_button_group

    x_button = Gtk.ToggleButton(label=name, x_button_group=x_button_group)
    y_button = Gtk.CheckButton(label=name, active=yactive)

    if x_button_group is None:
        x_button_group = x_button

    Gtk.ToggleButton.set_active(x_button, xactive)
    Gtk.ToggleButton.connect(x_button, "toggled", on_x_button_toggled)
    Gtk.CheckButton.connect(y_button, "toggled", on_y_button_toggled)

    x_item = Gtk.Box()
    y_item = Gtk.Box()

    x_item.append(x_button)
    y_item.append(y_button)

    x_delete = Gtk.Button.new_from_icon_name("edit-delete")
    y_delete = Gtk.Button.new_from_icon_name("edit-delete")

    x_delete.set_hexpand(True)
    y_delete.set_hexpand(True)

    x_delete.set_halign(Gtk.Align.END)
    y_delete.set_halign(Gtk.Align.END)

    Gtk.Button.connect(x_delete,
                       "clicked", on_delete_button_click, (x_button, y_button))
    Gtk.Button.connect(y_delete,
                       "clicked", on_delete_button_click, (y_button, x_button))

    x_item.append(x_delete)
    y_item.append(y_delete)

    Gtk.Box.append(x_buttons_box, x_item)
    Gtk.Box.append(y_buttons_box, y_item)
    return


def on_entry_activate(entry, x_config_scroll, y_config_scroll):
    buffer = Gtk.Entry.get_buffer(entry)
    text = Gtk.EntryBuffer.get_text(buffer)

    local_dict = df.to_dict(orient='series')
    df[text] = pd.eval(text, local_dict=local_dict)
    Gtk.Entry.set_text(entry, "")

    name = df.columns[-1]

    x_buttons_box = x_config_scroll.get_child().get_child()
    y_buttons_box = y_config_scroll.get_child().get_child()
    add_buttons_xy(name, x_buttons_box, y_buttons_box, yactive=True)

    add_plot_name_nplots(name)
    redraw_plots()
    return


def on_delete_button_click(delete_button, user_data):

    def _delete_parent(button):
        parent = Gtk.Button.get_parent(button)
        grand_parent = Gtk.Box.get_parent(parent)
        Gtk.Box.remove(grand_parent, parent)
        return

    x_button = user_data[0]
    y_button = user_data[1]
    name = x_button.get_label()

    if name != x.name:
        df.drop(name, axis=1)

        remove_plot(name)
        redraw_plots()
        _delete_parent(x_button)
        _delete_parent(y_button)
    return


def on_x_button_toggled(x_button):
    global axes_left, x, df

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

    for name in plotted:
        add_plot_name_nplots(name)

    axes_left.set_xlabel(x.name)
    redraw_plots()
    return


def on_y_button_toggled(y_button):
    name = Gtk.CheckButton.get_label(y_button)
    active = Gtk.CheckButton.get_active(y_button)

    if active:
        add_plot_name_nplots(name)
    else:
        remove_plot(name)

    redraw_plots()
    return


def on_reload_button_clicked(reload_button, x_config_scroll, y_config_scroll):
    reload_file_contents()
    reinitialize_plots(x_config_scroll, y_config_scroll)
    redraw_plots()
    return


def remove_plot(name):
    for line in axes_left.get_lines():
        if line.get_label() == name:
            line.remove()
            break
    return


def redraw_plots():
    axes_left.relim()
    axes_left.autoscale()
    axes_left.legend()
    canvas.draw()
    return


def add_plot_name_nplots(name):
    nplots = len(axes_left.get_lines())

    y = df[name]
    if x.is_monotonic_increasing:
        linestyle = "solid" if nplots < 6 else "dashdot"
        axes_left.plot(x, y, linestyle=linestyle, label=name)
    else:
        axes_left.plot(x, y, 'o', markersize=1.5, label=name)
    return


if __name__ == "__main__":
    program = os.path.basename(sys.argv[0])
    app = Gtk.Application(application_id=f"{program}")
    Gtk.Application.connect(app, 'activate', on_application_activation)
    Gtk.Application.run(app, None)

    sys.exit(0)
