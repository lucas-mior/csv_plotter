# csv_plotter.py

Interactively plot CSV files.

## Features
- matplotlib's plot window features:
    * image saving
    * mouse interaction (zoom, crop...)
- select which columns to plot
- select X axis
- create new curves by inserting expressions parsed by `pandas.eval()`
- remove unwanted columns (for organization purposes)
- command to reload file contents (in case you make external changes)

## Non-features
- CSV edition (use a text/spreadsheet editor instead)
- open more than one file

## TODO
- ~~Add new curves as linear combinations of the existing data~~.
- Add option to configurate color, linesize and linestyle for each curve.
- ~~Use left and right axes to fit plots with different amplitudes.~~
- Improve the positioning of the legends, options:
  * Always left and right, making axis clear and axis labels useless.
  * Make only one legend box with both axis lines.

## Dependencies
- matplotlib
- pygobject
- pandas

## Screenshot
![csv_plotter.py](https://github.com/lucas-mior/csv_plotter/blob/master/screenshot.png)
