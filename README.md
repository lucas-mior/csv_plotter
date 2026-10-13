# csv_plotter.py

Interactively plot CSV, TSV (tab-separated), and HDF5 files.
## Demo
![csv_plotter.py](https://github.com/lucas-mior/csv_plotter/blob/master/demo.gif)

## Features
- matplotlib's plot window features:
    * image saving
    * mouse interaction (zoom, crop...)
- load comma-separated `.csv` and tab-separated `.tsv` files
- recognize Cystemas-style `[unit]` headers in TSV and CSV files, as well
  as separate HDF5 names/units metadata
- show units alongside editable variable names in the right-hand selector;
  the unit is separate from the name used in expressions
- disambiguate duplicate names with units: `pressure[bar]` and `pressure[Pa]`
  appear as `pressure [bar]` and `pressure [Pa]`, while their expression
  names are `pressure_bar` and `pressure_pa` (shown in tooltips)
- keep dot-separated namespaces grouped and names without dots ungrouped
- use internal names in expressions (`pressure_bar + pressure_pa`) or backtick
  quoted display labels (`` `pressure [bar]` + `pressure [Pa]` ``)
- save modified CSV, TSV, and HDF5 data with original source names and unit
  metadata preserved, including duplicate names with different units
- select which columns to plot
- rename columns
- select X axis
- create new curves by inserting expressions parsed by `pandas.eval()`
- remove unwanted columns (for organization purposes)
    * Possibly save as a new file (also save new curves)
- command to reload file contents (in case you make external changes)

## Non-features
- CSV/TSV edition (use a text/spreadsheet editor instead)
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
