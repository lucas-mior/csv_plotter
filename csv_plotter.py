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
from matplotlib.artist import Artist
from matplotlib.lines import Line2D
import matplotlib.colors as mcolors

matplotlib.rcParams.update({'font.size': 14})

base_colors = {k: v for k, v in mcolors.BASE_COLORS.items() if k != 'w'}
base_colors = list(dict.keys(base_colors))
tableau_colors = list(dict.keys(mcolors.TABLEAU_COLORS))

colors_options = tableau_colors + base_colors
styles_options = ["solid", "dashdot", "dotted"]

styles = {}
colors = {}

def on_application_activation(application):
    global window, filename

    window = Gtk.ApplicationWindow(application=application)
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

    if not "time" in data_frame.columns:
        try:
            rows = DataFrame.reset_index(data_frame).index
            DataFrame.insert(data_frame, 0, 'Row', rows)
        except:
            pass
    x_data = data_frame.iloc[:, 0]
    return


def configure_window_once():
    global axes_left, axes_right, canvas

    filebase = os.path.basename(filename)
    Gtk.ApplicationWindow.set_title(window, f"{program} - {filebase}")

    figure = Figure(layout="constrained")
    canvas = FigureCanvas(figure)
    toolbar = NavigationToolbar(canvas)

    FigureCanvas.set_hexpand(canvas, True)
    FigureCanvas.set_vexpand(canvas, True)

    axes_left = Figure.add_subplot(figure, 111)
    Axes.set_title(axes_left, f"{filebase}")
    Axes.grid(axes_left)
    axes_right = Axes.twinx(axes_left)

    plot_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    config_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    buttons_header = Gtk.Label(label="Select x axis and columns to plot")

    Gtk.Box.append(config_box, buttons_header)

    selection_scroll = Gtk.ScrolledWindow()

    reload_button = Gtk.Button.new_from_icon_name("document-revert")
    save_button = Gtk.Button.new_from_icon_name("document-save")

    axis_button = Gtk.CheckButton(label="axis labels", active=True)

    Gtk.Button.set_tooltip_text(reload_button, "Reload file contents")
    Gtk.Button.set_tooltip_text(save_button, "Save file changes on new file")

    Gtk.CheckButton.set_tooltip_text(axis_button, "Toggle axis labels")

    Gtk.Button.connect(reload_button, "clicked", on_reload_button_clicked)
    Gtk.Button.connect(save_button, "clicked", on_save_button_clicked)

    reload_button.selection_scroll = selection_scroll
    save_button.selection_scroll = selection_scroll

    Gtk.CheckButton.connect(axis_button, "toggled", on_axis_button_toggled)
    on_axis_button_toggled(axis_button)

    toolbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    Gtk.Box.append(toolbar_box, toolbar)
    Gtk.Box.append(toolbar_box, axis_button)
    Gtk.Box.append(toolbar_box, reload_button)
    Gtk.Box.append(toolbar_box, save_button)

    Gtk.Box.append(plot_box, toolbar_box)
    Gtk.Box.append(plot_box, canvas)

    reconfigure_plots_and_buttons(selection_scroll)

    Gtk.ScrolledWindow.set_vexpand(selection_scroll, True)
    Gtk.ScrolledWindow.set_policy(selection_scroll,
                                  hscrollbar_policy=Gtk.PolicyType.NEVER,
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

    Gtk.ApplicationWindow.set_child(window, window_pane)
    Gtk.ApplicationWindow.set_visible(window, True)
    return


def clean_plotted_get_list():
    plotted_left = []
    plotted_right = []

    for line in Axes.get_lines(axes_left):
        list.append(plotted_left, Line2D.get_label(line))
        Line2D.remove(line)
    for line in Axes.get_lines(axes_right):
        list.append(plotted_right, Line2D.get_label(line))
        Line2D.remove(line)

    return plotted_left, plotted_right


def reconfigure_plots_and_buttons(selection_scroll):
    global x_button_group, data_frame

    plotted_left, plotted_right = clean_plotted_get_list()

    buttons_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    name_first = data_frame.columns[0]
    x_button_group = None
    add_buttons(name_first, buttons_box)

    for i, name in enumerate(data_frame.columns[1:]):
        left = right = False
        # TODO: dots bug expressions in pandas.eval(), find better solution
        new = str.replace(name, ".", "_")
        DataFrame.rename(data_frame, columns={name: new}, inplace=True)

        if name == "time" or name == "hour":
            pass
        elif not plotted_left and not plotted_right:
            if i < 10:
                add_plot(new, left=True)
                left = True
        else:
            if new in plotted_left:
                add_plot(new, left=True)
                left = True
            if new in plotted_right:
                add_plot(new, left=False)
                right = True
        add_buttons(new, buttons_box, left=left, right=right)

    Axes.set_xlabel(axes_left, x_data.name)
    set_axis_labels()
    put_legends()

    Gtk.ScrolledWindow.set_child(selection_scroll, buttons_box)
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


def add_buttons(name, buttons_box, left=False, right=False):
    global x_button_group

    def _set_margins(button):
        button.set_margin_end(2)
        button.set_margin_start(2)

    x_button = Gtk.CheckButton(group=x_button_group)
    y_button_left = Gtk.CheckButton(active=left)
    y_button_right = Gtk.CheckButton(active=right)
    buttons_label = Gtk.Label(label=name)
    style_button = Gtk.Button.new_from_icon_name("system-run-symbolic")
    color_button = Gtk.Button.new_from_icon_name("color-select-symbolic")
    delete_button = Gtk.Button.new_from_icon_name("edit-delete")

    Gtk.Button.set_tooltip_text(x_button, f"Set {name} as x axis")
    Gtk.Button.set_tooltip_text(y_button_left, f"Plot {name} on left axis")
    Gtk.Button.set_tooltip_text(y_button_right, f"Plot {name} on right axis")
    Gtk.Button.set_tooltip_text(style_button, f"Change {name} line style")
    Gtk.Button.set_tooltip_text(color_button, f"Change {name} line color")
    Gtk.Button.set_tooltip_text(delete_button, f"Delete {name} from data")

    x_button.name = name
    y_button_left.name = name
    y_button_right.name = name
    style_button.name = name
    color_button.name = name
    delete_button.name = name

    y_button_left.is_left = True
    y_button_right.is_left = False

    _set_margins(x_button)
    _set_margins(y_button_left)
    _set_margins(y_button_right)

    if x_button_group is None:
        x_button_group = x_button
        Gtk.CheckButton.set_active(x_button, True)

    Gtk.CheckButton.connect(x_button, "toggled", on_x_button_toggled)
    Gtk.CheckButton.connect(y_button_left, "toggled", on_y_button_toggled)
    Gtk.CheckButton.connect(y_button_right, "toggled", on_y_button_toggled)
    Gtk.Button.connect(style_button, "clicked", on_style_button_click)
    Gtk.Button.connect(color_button, "clicked", on_color_button_click)
    Gtk.Button.connect(delete_button, "clicked", on_delete_button_click)

    item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

    Gtk.Box.append(item, x_button)
    Gtk.Box.append(item, y_button_left)
    Gtk.Box.append(item, y_button_right)
    Gtk.Box.append(item, buttons_label)
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


def on_reload_button_clicked(reload_button):
    reload_file_contents()
    reconfigure_plots_and_buttons(reload_button.selection_scroll)
    redraw_plots()
    return


def on_save_button_clicked(save_button):
    newfile = str.rsplit(filename, '.', maxsplit=1)[0]
    newfile += "_new.csv"
    DataFrame.to_csv(data_frame, newfile, sep=',', index=False)
    return


def on_style_button_click(style_button):
    name = style_button.name

    try:
        old = styles[name]
        while styles[name] == old:
            styles[name] = random.choice(styles_options)
    except Exception:
        styles[name] = random.choice(styles_options)

    left = right = False

    for line in Axes.get_lines(axes_left):
        if Line2D.get_label(line) == name:
            left = True
            break
    for line in Axes.get_lines(axes_right):
        if Line2D.get_label(line) == name:
            right = True
            break

    if left or right:
        remove_plot(name, left, right)

    if left:
        add_plot(name, left=True)
    if right:
        add_plot(name, left=False)

    redraw_plots()
    return


def on_color_button_click(color_button):
    name = color_button.name

    try:
        old = colors[name]
        while colors[name] == old:
            colors[name] = random.choice(colors_options)
    except Exception:
        colors[name] = random.choice(colors_options)

    left = right = False

    for line in Axes.get_lines(axes_left):
        if Line2D.get_label(line) == name:
            left = True
            break
    for line in Axes.get_lines(axes_right):
        if Line2D.get_label(line) == name:
            right = True
            break

    if left or right:
        remove_plot(name, left, right)

    if left:
        add_plot(name, left=True)
    if right:
        add_plot(name, left=False)

    redraw_plots()
    return


def on_delete_button_click(delete_button):
    global data_frame
    name = delete_button.name

    if name != x_data.name:
        print(f"deleting {name}...")
        DataFrame.drop(data_frame, name, axis=1, inplace=True)

        remove_plot(name, left=True, right=True)
        redraw_plots()

        parent_box = Gtk.Button.get_parent(delete_button)
        grand_parent = Gtk.Box.get_parent(parent_box)
        Gtk.Box.remove(grand_parent, parent_box)
    return


def on_x_button_toggled(x_button):
    global x_data

    name = x_button.name
    active = Gtk.CheckButton.get_active(x_button)

    if not active:
        return

    x_data = data_frame[name]

    plotted_left, plotted_right = clean_plotted_get_list()

    for name in plotted_left:
        add_plot(name, left=True)
    for name in plotted_right:
        add_plot(name, left=False)

    Axes.set_xlabel(axes_left, x_data.name)
    redraw_plots()
    return


def on_y_button_toggled(y_button):
    name = y_button.name
    is_left = y_button.is_left
    active = Gtk.CheckButton.get_active(y_button)

    if active:
        add_plot(name, left=is_left)
    else:
        remove_plot(name, left=is_left, right=not is_left)

    redraw_plots()
    return


def on_entry_activate(entry):
    global data_frame

    buffer = Gtk.Entry.get_buffer(entry)
    text = Gtk.EntryBuffer.get_text(buffer)

    local_dict = DataFrame.to_dict(data_frame, orient='series')
    data_frame[text] = pd.eval(text, local_dict=local_dict)
    Gtk.Entry.set_text(entry, "")

    viewport = Gtk.ScrolledWindow.get_child(entry.selection_scroll)
    buttons_box = Gtk.Viewport.get_child(viewport)

    name = data_frame.columns[-1]
    add_buttons(name, buttons_box, left=True)

    add_plot(name, left=True)
    redraw_plots()
    return


def remove_plot(name, left=False, right=False):
    if left:
        for line in Axes.get_lines(axes_left):
            if Line2D.get_label(line) == name:
                Line2D.remove(line)
                break
    if right:
        for line in Axes.get_lines(axes_right):
            if Line2D.get_label(line) == name:
                Line2D.remove(line)
                break
    return


def put_legends():
    plotted = []
    for line in Axes.get_lines(axes_left):
        list.append(plotted, line)
    for line in Axes.get_lines(axes_right):
        list.append(plotted, line)
    Axes.legend(axes_left, plotted, [p.get_label() for p in plotted])
    return


def redraw_plots():
    set_axis_labels()

    Axes.relim(axes_left)
    Axes.relim(axes_right)
    Axes.autoscale(axes_left)
    Axes.autoscale(axes_right)
    put_legends()

    FigureCanvas.draw(canvas)
    return


def add_plot(name, left=True):
    global styles

    if left:
        axes = axes_left
    else:
        axes = axes_right

    y = data_frame[name]

    try:
        linestyle = styles[name]
        color = colors[name]
    except Exception:
        linestyle = random.choice(styles_options)
        color = random.choice(colors_options)
        styles[name] = linestyle
        colors[name] = color

    if x_data.is_monotonic_increasing:
        Axes.plot(axes, x_data, y, linestyle=linestyle, color=color, label=name)
    else:
        Axes.plot(axes, x_data, y, 'o', markersize=1.5, color=color, label=name)
    return


if __name__ == "__main__":
    program = os.path.basename(sys.argv[0])
    application = Gtk.Application(application_id=f"{program}")
    Gtk.Application.connect(application, 'activate', on_application_activation)
    Gtk.Application.run(application, None)

    sys.exit(0)
