#!/usr/bin/python

import os
import sys
import pandas as pd
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

matplotlib.rcParams.update({'font.size': 14})

base_colors = {
    k: v for k, v in mcolors.BASE_COLORS.items() if k != 'w' and k != 'y'
}
base_colors = list(dict.keys(base_colors))
tableau_colors = list(dict.keys(mcolors.TABLEAU_COLORS))

colors_cycle = cycle(tableau_colors + base_colors)
styles_cycle = cycle(["solid", "dashdot", "dotted"])

styles = {}
colors = {}

pre_plots = []


def on_application_activation(application):
    global window, filename, pre_plots

    window = Gtk.ApplicationWindow(application=application)
    Gtk.ApplicationWindow.set_default_size(window, 1400, 900)

    argc = len(sys.argv)

    if argc < 2:
        dialog = Gtk.FileDialog(title=f"{program} - Choose a CSV file")
        Gtk.FileDialog.open(dialog, window, None, on_have_filename_ready, None)
    else:
        filename = sys.argv[1]
        if argc > 2:
            pre_plots = str.split(sys.argv[2], ",")
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

    if "time" not in data_frame.columns:
        try:
            rows = DataFrame.reset_index(data_frame).index
            DataFrame.insert(data_frame, 0, 'Row', rows)
        except Exception:
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

    Gtk.Button.set_tooltip_text(reload_button, "Reload file contents")
    Gtk.Button.set_tooltip_text(save_button, "Save file changes on new file")

    Gtk.Button.connect(reload_button, "clicked", on_reload_button_clicked)
    Gtk.Button.connect(save_button, "clicked", on_save_button_clicked)

    reload_button.selection_scroll = selection_scroll
    save_button.selection_scroll = selection_scroll

    toolbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    Gtk.Box.append(toolbar_box, toolbar)
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


def reconfigure_plots_and_buttons(selection_scroll):
    global x_button_group, data_frame, pre_plots

    buttons_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    name_first = data_frame.columns[0]
    x_button_group = None
    add_buttons(name_first, buttons_box)
    colors[name_first] = next(colors_cycle)
    styles[name_first] = "solid"

    for name in data_frame.columns[1:]:
        left = right = False
        # TODO: dots bug expressions in pandas.eval(), find better solution
        new = str.replace(name, ".", "_")
        DataFrame.rename(data_frame, columns={name: new}, inplace=True)
        name = new

        colors[name] = next(colors_cycle)
        styles[name] = "solid"

        if name in pre_plots:
            add_plot(name, axes_left)
            left = True
        else:
            plotted_left, plotted_right = clean_plotted_get_list()
            if name in plotted_left:
                add_plot(name, axes_left)
                left = True
            if name in plotted_right:
                add_plot(name, axes_right)
                right = True

        add_buttons(name, buttons_box, left=left, right=right)

    pre_plots = []
    Axes.set_xlabel(axes_left, x_data.name)
    configure_y_axis_labels_and_ticks()
    put_legends()

    Gtk.ScrolledWindow.set_child(selection_scroll, buttons_box)
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


def configure_y_axis_labels_and_ticks():
    names_left = ""
    names_right = ""

    for line in Axes.get_lines(axes_left):
        name = Line2D.get_label(line)
        names_left += f" {name} "
    for line in Axes.get_lines(axes_right):
        name = Line2D.get_label(line)
        names_right += f" {name} "

    if names_left == "":
        Axes.tick_params(axes_left, axis='y', left=False, labelleft=False)
    else:
        Axes.tick_params(axes_left, axis='y', left=True, labelleft=True)
    if names_right == "":
        Axes.tick_params(axes_right, axis='y', right=False, labelright=False)
    else:
        Axes.tick_params(axes_right, axis='y', right=True, labelright=True)

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
    redraw_plots()
    return


def on_save_button_clicked(save_button):
    newfile = str.rsplit(filename, '.', maxsplit=1)[0]
    newfile += "_new.csv"
    DataFrame.to_csv(data_frame, newfile, sep=',', index=False)
    return


def on_item_label_notify_editing(editable_label, editing):
    if Gtk.EditableLabel.get_editing(editable_label):
        return

    item = Gtk.Button.get_parent(editable_label)
    old_name = item.name
    new_name = Gtk.EditableLabel.get_text(editable_label)

    DataFrame.rename(data_frame, columns={old_name: new_name}, inplace=True)
    styles[new_name] = styles.pop(old_name)
    colors[new_name] = colors.pop(old_name)

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

    item.name = new_name

    redraw_plots()
    return


def on_style_button_click(style_button):
    name = get_button_name(style_button)

    styles[name] = next(styles_cycle)

    left = right = False

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

    left = right = False

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

    if name != x_data.name:
        DataFrame.drop(data_frame, name, axis=1, inplace=True)

        del colors[name]
        del styles[name]

        remove_plot(name, axes_left)
        remove_plot(name, axes_right)
        redraw_plots()

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

    x_data = data_frame[name]

    plotted_left, plotted_right = clean_plotted_get_list()

    for name in plotted_left:
        add_plot(name, axes_left)
    for name in plotted_right:
        add_plot(name, axes_right)

    Axes.set_xlabel(axes_left, x_data.name)
    redraw_plots()
    return


def on_y_button_toggled(y_button):
    name = get_button_name(y_button)

    axes = y_button.axes
    active = Gtk.CheckButton.get_active(y_button)

    if active:
        add_plot(name, axes)
    else:
        remove_plot(name, axes)

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

    colors[name] = next(colors_cycle)
    styles[name] = next(styles_cycle)

    add_buttons(name, buttons_box, left=False, right=True)

    add_plot(name, axes_right)
    redraw_plots()
    return


def reset_plot(name, left, right):
    if left:
        remove_plot(name, axes_left)
    if right:
        remove_plot(name, axes_right)

    if left:
        add_plot(name, axes_left)
    if right:
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
    plotted = []
    for line in Axes.get_lines(axes_left):
        list.append(plotted, line)
    for line in Axes.get_lines(axes_right):
        list.append(plotted, line)

    names = [Line2D.get_label(line) for line in plotted]

    Axes.legend(axes_left, plotted, names)
    return


def redraw_plots():
    configure_y_axis_labels_and_ticks()

    Axes.relim(axes_left)
    Axes.relim(axes_right)
    Axes.autoscale(axes_left)
    Axes.autoscale(axes_right)
    put_legends()

    FigureCanvas.draw(canvas)
    return


def add_plot(name, axes):
    global styles

    y = data_frame[name]

    linestyle = styles[name]
    color = colors[name]

    if x_data.is_monotonic_increasing:
        Axes.plot(axes, x_data, y, label=name,
                  linestyle=linestyle, color=color)
    else:
        Axes.plot(axes, x_data, y, 'o', label=name,
                  markersize=1.5, color=color)
    return


if __name__ == "__main__":
    program = os.path.basename(sys.argv[0])
    application = Gtk.Application(application_id=f"{program}")
    Gtk.Application.connect(application, 'activate', on_application_activation)
    Gtk.Application.run(application, None)

    sys.exit(0)
