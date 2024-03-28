# csv_plotter.py

Interactively plot CSV files.

## Features
- matplotlib's plot window features:
    * image saving
    * mouse interaction (zoom, crop...)
- select which columns to plot
- rename columns
- select X axis
- create new curves by inserting expressions parsed by `pandas.eval()`
- remove unwanted columns (for organization purposes)
    * Possibly save as a new file (also save new curves)
- command to reload file contents (in case you make external changes)

## Non-features
- CSV edition (use a text/spreadsheet editor instead)
    * You can only delete columns and add new ones by inserting expressions
      and save the resulting data frame as a new file
- open more than one file

## TODO
- ~~Add new curves as linear combinations of the existing data~~.
- ~~Add option to configurate color, linesize and linestyle for each curve.~~
  * ~~button to select color and style sequentially, not randomly~~
- ~~Use left and right axes to fit plots with different amplitudes.~~
- ~~Improve the positioning of the legends~~
  * ~~Make only one legend box with both axis lines.~~

## Dependencies
- matplotlib
- pygobject
- pandas

## Screenshot
![csv_plotter.py](https://github.com/lucas-mior/csv_plotter/blob/master/screenshot.png)
