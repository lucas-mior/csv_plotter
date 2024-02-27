#!/usr/bin/python

import os
import sys
import pandas as pd
import numpy as np
import random

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
import matplotlib.colors as mcolors

matplotlib.rcParams.update({'font.size': 14})


def on_application_activation(app):
    global window, filename

    window = Gtk.ApplicationWindow(application=app)
    Gtk.ApplicationWindow.set_default_size(window, 1400, 900)

    if len(sys.argv) < 2:
        dialog = Gtk.FileDialog(title=f"{program} - Choose a CSV file")
        Gtk.FileDialog.open(dialog, window, None, on_have_filename_ready, None)
    else:
        filename = sys.argv[1]
        on_have_filename_ready(None, None, None)
    return


def on_have_filename_ready(dialog, async_result, data):
    global filename

    if dialog is not None:
        gfile = Gtk.FileDialog.open_finish(dialog, result=async_result)
        if gfile is None:
            print("Error getting file", file=sys.stderr)
            sys.exit(1)
        filename = Gio.File.get_path(gfile)

    reload_file_contents()
    configure_window_once()
    return


def reload_file_contents():
    global data_frame, x_data
    data_frame = None
    try:
        data_frame = pd.read_csv(filename)
    except Exception:
        print(f"Error reading {filename}", file=sys.stderr)
        sys.exit(1)
    if data_frame is None:
        print(f"Error reading {filename}", file=sys.stderr)
        sys.exit(1)

    rows = DataFrame.reset_index(data_frame).index
    DataFrame.insert(data_frame, 0, 'Row', rows)
    x_data = data_frame.iloc[:, 0]
    return


def configure_plot_colors():
    base_colors = {k: v for k, v in mcolors.BASE_COLORS.items() if k != 'w'}
    Axes.set_prop_cycle(axes_left, color=mcolors.TABLEAU_COLORS)
    Axes.set_prop_cycle(axes_right, color=base_colors)
    return


def configure_window_once():
    global axes_left, axes_right, canvas

    filebase = os.path.basename(filename)
    Gtk.ApplicationWindow.set_title(window, f"{program} - {filebase}")

    figure = Figure(layout="constrained")
    canvas = FigureCanvas(figure)
    axes_left = Figure.add_subplot(figure, 111)

    FigureCanvas.set_hexpand(canvas, True)
    FigureCanvas.set_vexpand(canvas, True)

    toolbar = NavigationToolbar(canvas)

    Axes.set_title(axes_left, f"{filebase}")
    Axes.grid(axes_left)
    axes_right = Axes.twinx(axes_left)

    configure_plot_colors()

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
    axis_button = Gtk.CheckButton(label="axis labels", active=True)

    Gtk.Button.set_tooltip_text(reload_button, "Reload file contents")
    Gtk.CheckButton.set_tooltip_text(axis_button, "Toggle axis labels")

    Gtk.Button.connect(reload_button, "clicked", on_reload_button_clicked,
                       x_config_scroll, y_config_scroll)
    Gtk.CheckButton.connect(axis_button, "toggled", on_axis_button_toggled)
    on_axis_button_toggled(axis_button)

    toolbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    Gtk.Box.append(toolbar_box, toolbar)
    Gtk.Box.append(toolbar_box, axis_button)
    Gtk.Box.append(toolbar_box, reload_button)

    Gtk.Box.append(plot_box, toolbar_box)
    Gtk.Box.append(plot_box, canvas)

    reconfigure_plots_and_buttons(x_config_scroll, y_config_scroll)

    Gtk.ScrolledWindow.set_vexpand(x_config_scroll, True)
    Gtk.ScrolledWindow.set_vexpand(y_config_scroll, True)
    Gtk.ScrolledWindow.set_policy(x_config_scroll,
                                  hscrollbar_policy=Gtk.PolicyType.NEVER,
                                  vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
    Gtk.ScrolledWindow.set_policy(y_config_scroll,
                                  hscrollbar_policy=Gtk.PolicyType.NEVER,
                                  vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)

    new_data_entry = Gtk.Entry()
    Gtk.Entry.set_placeholder_text(new_data_entry, "add a plot...")
    Gtk.Entry.connect(new_data_entry, "activate", on_entry_activate,
                      x_config_scroll, y_config_scroll)

    Gtk.Box.append(x_selection_box, x_config_scroll)
    Gtk.Box.append(y_selection_box, y_config_scroll)
    Gtk.Box.append(y_selection_box, new_data_entry)

    config_pane = Gtk.Paned.new(orientation=Gtk.Orientation.VERTICAL)
    Gtk.Paned.set_wide_handle(config_pane, True)

    Gtk.Paned.set_start_child(config_pane, x_selection_box)
    Gtk.Paned.set_end_child(config_pane, y_selection_box)

    Gtk.Paned.set_shrink_start_child(config_pane, False)
    Gtk.Paned.set_shrink_end_child(config_pane, False)

    window_pane = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
    Gtk.Paned.set_wide_handle(window_pane, True)
    Gtk.Paned.set_position(window_pane, 1100)

    Gtk.Paned.set_start_child(window_pane, plot_box)
    Gtk.Paned.set_end_child(window_pane, config_pane)

    Gtk.Paned.set_shrink_start_child(window_pane, False)
    Gtk.Paned.set_shrink_end_child(window_pane, False)

    Gtk.ApplicationWindow.set_child(window, window_pane)
    Gtk.ApplicationWindow.set_visible(window, True)
    return


def reconfigure_plots_and_buttons(x_config_scroll, y_config_scroll):
    global x_button_group, diff_median

    for line in Axes.get_lines(axes_left):
        line.remove()
    for line in Axes.get_lines(axes_right):
        line.remove()

    x_buttons_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    y_buttons_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    name_first = data_frame.columns[0]
    x_button_group = None
    add_buttons_xy(name_first, x_buttons_box, y_buttons_box,
                   xactive=True, yactive=False)

    diff_all = np.max(data_frame, axis=0) - np.min(data_frame, axis=0)
    diff_median = np.median(diff_all)

    for i, name in enumerate(data_frame.columns[1:]):
        # TODO: dots bug expressions in pandas.eval(), find better solution
        new = str.replace(name, ".", "_")
        DataFrame.rename(data_frame, columns={name: new}, inplace=True)
        diff = np.max(data_frame[name]) - np.min(data_frame[name])

        if i < 10:
            add_plot(new)

        add_buttons_xy(new, x_buttons_box, y_buttons_box, yactive=i < 10)

    Axes.set_xlabel(axes_left, x_data.name)
    set_axis_labels()
    Axes.legend(axes_left)
    Axes.legend(axes_right)

    Gtk.ScrolledWindow.set_child(x_config_scroll, x_buttons_box)
    Gtk.ScrolledWindow.set_child(y_config_scroll, y_buttons_box)
    return


def set_axis_labels():
    names_left = ""
    names_right = ""
    if axis_labels:
        for line in Axes.get_lines(axes_left):
            names_left += f" {line.get_label()} "
        for line in Axes.get_lines(axes_right):
            names_right += f" {line.get_label()} "

    Axes.set_ylabel(axes_left, names_left)
    Axes.set_ylabel(axes_right, names_right)
    return


def add_buttons_xy(name, x_buttons_box, y_buttons_box,
                   xactive=False, yactive=False):
    global x_button_group

    x_button = Gtk.ToggleButton(label=name, group=x_button_group)
    y_button = Gtk.CheckButton(label=name, active=yactive)

    if x_button_group is None:
        x_button_group = x_button

    Gtk.ToggleButton.set_active(x_button, xactive)
    Gtk.ToggleButton.connect(x_button, "toggled", on_x_button_toggled)
    Gtk.CheckButton.connect(y_button, "toggled", on_y_button_toggled)

    x_item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    y_item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

    Gtk.Box.append(x_item, x_button)
    Gtk.Box.append(y_item, y_button)

    x_delete = Gtk.Button.new_from_icon_name("edit-delete")
    y_delete = Gtk.Button.new_from_icon_name("edit-delete")

    Gtk.Button.set_hexpand(x_delete, True)
    Gtk.Button.set_hexpand(y_delete, True)

    Gtk.Button.set_halign(x_delete, Gtk.Align.END)
    Gtk.Button.set_halign(y_delete, Gtk.Align.END)

    Gtk.Button.connect(x_delete, "clicked", on_delete_button_click,
                       x_button, y_button)
    Gtk.Button.connect(y_delete, "clicked", on_delete_button_click,
                       x_button, y_button)

    Gtk.Box.append(x_item, x_delete)
    Gtk.Box.append(y_item, y_delete)

    Gtk.Box.append(x_buttons_box, x_item)
    Gtk.Box.append(y_buttons_box, y_item)
    return


def on_axis_button_toggled(axis_button):
    global axis_labels

    try:
        axis_labels
    except NameError:
        axis_labels = True
        return

    name = Gtk.CheckButton.get_label(axis_button)
    axis_labels = Gtk.CheckButton.get_active(axis_button)

    redraw_plots()
    return


def on_reload_button_clicked(reload_button, x_config_scroll, y_config_scroll):
    reload_file_contents()
    reconfigure_plots_and_buttons(x_config_scroll, y_config_scroll)
    redraw_plots()
    return


def on_delete_button_click(delete_button, x_button, y_button):

    def _delete_parent_box(button):
        parent_box = Gtk.Button.get_parent(button)
        grand_parent = Gtk.Box.get_parent(parent_box)
        Gtk.Box.remove(grand_parent, parent_box)
        return

    name = Gtk.ToggleButton.get_label(x_button)

    if name != x_data.name:
        DataFrame.drop(data_frame, name, axis=1)

        remove_plot(name)
        redraw_plots()
        _delete_parent_box(x_button)
        _delete_parent_box(y_button)
    return


def on_x_button_toggled(x_button):
    global x_data

    name = Gtk.ToggleButton.get_label(x_button)
    active = Gtk.ToggleButton.get_active(x_button)

    if not active:
        return

    x_data = data_frame[name]

    plotted= []
    for line in Axes.get_lines(axes_left):
        list.append(plotted, line.get_label())
        line.remove()
    for line in Axes.get_lines(axes_right):
        list.append(plotted, line.get_label())
        line.remove()

    configure_plot_colors()

    for name in plotted:
        add_plot(name)

    Axes.set_xlabel(axes_left, x_data.name)
    redraw_plots()
    return


def on_y_button_toggled(y_button):
    name = Gtk.CheckButton.get_label(y_button)
    active = Gtk.CheckButton.get_active(y_button)

    if active:
        add_plot(name)
    else:
        remove_plot(name)

    redraw_plots()
    return


def on_entry_activate(entry, x_config_scroll, y_config_scroll):
    buffer = Gtk.Entry.get_buffer(entry)
    text = Gtk.EntryBuffer.get_text(buffer)

    local_dict = DataFrame.to_dict(data_frame, orient='series')
    data_frame[text] = pd.eval(text, local_dict=local_dict)
    Gtk.Entry.set_text(entry, "")

    name = data_frame.columns[-1]

    x_viewport = Gtk.ScrolledWindow.get_child(x_config_scroll)
    y_viewport = Gtk.ScrolledWindow.get_child(y_config_scroll)

    x_buttons_box = Gtk.Viewport.get_child(x_viewport)
    y_buttons_box = Gtk.Viewport.get_child(y_viewport)

    add_buttons_xy(name, x_buttons_box, y_buttons_box, yactive=True)

    add_plot(name)
    redraw_plots()
    return


def remove_plot(name):
    for line in Axes.get_lines(axes_left):
        if line.get_label() == name:
            line.remove()
            break
    for line in Axes.get_lines(axes_right):
        if line.get_label() == name:
            line.remove()
            break
    return


def redraw_plots():
    set_axis_labels()

    Axes.relim(axes_left)
    Axes.relim(axes_right)
    Axes.autoscale(axes_left)
    Axes.autoscale(axes_right)
    Axes.legend(axes_left)
    Axes.legend(axes_right)

    FigureCanvas.draw(canvas)
    return


def add_plot(name):
    data = data_frame[name]
    diff = np.max(data) - np.min(data)
    if diff < diff_median:
        axes = axes_left
    else:
        axes = axes_right

    nplots = len(Axes.get_lines(axes))

    y = data_frame[name]
    if x_data.is_monotonic_increasing:
        linestyle = "solid" if nplots < 5 else "dashdot"
        Axes.plot(axes, x_data, y, linestyle=linestyle, label=name)
    else:
        Axes.plot(axes, x_data, y, 'o', markersize=1.5, label=name)
    return


if __name__ == "__main__":
    program = os.path.basename(sys.argv[0])
    app = Gtk.Application(application_id=f"{program}")
    Gtk.Application.connect(app, 'activate', on_application_activation)
    Gtk.Application.run(app, None)

    sys.exit(0)
