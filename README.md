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
- read Cystemas HDF5 `/colors` metadata and use explicit per-column colors
  for plotting; columns with missing, empty, or unrecognized colors keep
  their automatic colors; legacy HDF5 files without `/colors` still work
- preserve color metadata in saved HDF5 files (including changes made with
  the color button); CSV and TSV formats continue to store no color metadata
- select which columns to plot
- rename columns
- select X axis
- create new curves by inserting expressions parsed by `pandas.eval()`
- remove unwanted columns (for organization purposes)
    * Possibly save as a new file (also save new curves)
- command to reload file contents (in case you make external changes)
- **Spectrum** tab with one-sided FFT amplitude plots of selected signals,
  using the same left/right axis assignments, colors, and line styles as the
  time-domain plot and an independent Matplotlib navigation toolbar
- interactive FFT controls for Hann/rectangular window, mean removal,
  linear/relative dB amplitudes, full/visible time range, and frequency limits

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

## Frequency-domain computation (FFT)

`csv_plotter_fft.py` provides `amplitude_spectrum(time, signal, *,
window="hann", detrend="mean", missing="raise", sampling_rtol=1e-3)`.
It returns two NumPy arrays: nonnegative frequencies in Hz and the
corresponding one-sided amplitudes in the input signal's physical units.
The analysis uses `numpy.fft.rfft`, a periodic Hann window by default,
mean removal by default, and coherent-gain normalization. DC and the
Nyquist component (when present) are scaled without doubling.

Times must be strictly increasing, approximately uniformly spaced, and
expressed in seconds. Irregular timestamps are rejected rather than silently
resampled. Nonfinite timestamps, infinite signal values, and missing samples
are also rejected. You can explicitly set `missing="interpolate"` to fill
*interior* NaN signal values with linear interpolation; missing first/last
samples cannot be filled automatically. Alternative options are
`window="rectangular"` and `detrend="none"`.

The **Spectrum** tab computes the FFT of signals selected in the **Plot**
tab, using the currently selected X column as time in seconds. The Spectrum
tab refreshes when opened and when the selection, data, X column, or line
styles change while it is visible. Each signal's amplitude retains its
physical unit, with left and right axes corresponding to the Plot tab.
Spectrum navigation, zooming, and image export use a separate Matplotlib
toolbar. The original data and time-domain plot are not modified.

Spectrum controls above the plot allow choosing the **Hann** or
**Rectangular** window, **Remove mean** or **None** detrending, and
**Linear** or **dB (relative to peak)** amplitude. In dB mode, each signal's
largest FFT amplitude is 0 dB, and smaller amplitudes are displayed relative
to that peak, floored at -120 dB. dB amplitudes are therefore not in the
signal's original units and are not directly comparable across signals.
A signal with zero amplitude at every frequency is reported as unavailable in
dB mode.

The **Time range** menu offers **All samples** (default) or **Visible Plot
range**. To use the latter, zoom the time-domain Plot first and open the
Spectrum tab; it computes the FFT from only the timestamps inside the Plot's
visible X limits. The time selection must contain at least three samples.
A shorter interval changes the FFT's frequency resolution.

Optional **Min** and **Max** frequency fields are in Hz. Press **Apply Hz**
or Enter to restrict the displayed FFT bins; an empty maximum includes the
Nyquist frequency. These fields crop the *displayed spectrum*, not the
underlying data or the FFT resolution. Invalid limits leave the previous
valid settings intact.

Defaults remain Hann window, mean removal, linear amplitude, all samples,
and the full frequency range. The X axis must contain uniformly spaced,
increasing times measured in seconds. If its unit is missing, seconds are
assumed and the tab says so. The tab reports invalid sample spacing or
missing signal samples instead of silently interpolating. The time-domain
plot and original data are not modified.
Run the tests with `python -m unittest discover -s tests`.
