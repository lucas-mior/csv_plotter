# Cystemas result TSV format, version 1

Status: Stage 1 specification. Extended TSV support is not implemented yet.
The authoritative copy is `cystemas/tsv-format.md`; csv_plotter carries a
byte-identical copy and the same fixtures under `tests/fixtures/tsv_v1/`.
The specification applies to result exports, not to arbitrary CSV files.

## File variants and detection

| Variant | First physical line | Following sections |
| --- | --- | --- |
| Legacy time series | Existing time-series header | Existing numeric rows |
| Metadata only | `# cystemas-tsv:1` | Metadata marker, header, rows |
| Combined | `# cystemas-tsv:1` | Metadata marker, header, rows, time-series marker, header, rows |

The existing separate decisions TSV is also an unmarked legacy table; it is
not a version-1 metadata file or necessarily a time series. Do not change its
format or infer a new format from its column names.

For a TSV input, both C and Python shall use the following classification:

1. Read the first physical line. Remove one UTF-8 BOM (bytes EF BB BF) at the
   beginning of the file, if present, and its LF or CRLF line ending. Do not
   trim other whitespace or search subsequent lines for the signature.
2. If the resulting line does not start with the exact ASCII prefix
   `# cystemas-tsv:`, dispatch to the existing legacy reader. Preserve its
   original behavior (including any legacy BOM handling). Empty files are
   legacy candidates, not valid extended files.
3. If the prefix is present but the entire line is not exactly
   `# cystemas-tsv:1`, report an unsupported or malformed version. Never fall
   back to legacy parsing, including for `01`, `2`, or `1 `.
4. Require the next line to be exactly `# metadata`, followed by the metadata
   header defined below. Parse metadata rows until EOF or the exact line
   `# timeseries`. EOF means metadata-only; the marker means combined and
   must be followed by a time-series header. Zero metadata rows are allowed.
5. There are no additional sections. A second section marker or signature in
   an extended file is an error. Missing headers, malformed metadata rows and invalid
   encodings are errors, not reasons to retry the legacy reader.

The classification is based only on the signature and section structure, not
on the number of columns, presence of a time column, numeric values, or empty
lines. Marker comparison is case-sensitive and byte-exact after line-ending
removal. A leading blank line or space before the signature is not recognized.
Report errors with the original physical line number where applicable.

Writers use UTF-8 without BOM, LF endings, and one final newline. Extended
readers accept LF, CRLF (including mixed endings), and an unterminated last
nonempty line. Bare CR, NUL, invalid UTF-8, blank physical lines in metadata,
comments, and extra sections are not allowed in extended files. A final line
ending is not an extra blank line. Legacy files retain their existing rules.
A reader may record byte offsets to stream or seek to either section; it need
not load the time-series data when only metadata is requested. Section and
metadata validation must not depend on whether HDF5 support is available.

## Metadata table

The exact header, with literal tabs between the ten field names, is:

```text
kind	name	value	unit	default_value	initial_value	original_initial_value	lower_bound	upper_bound	optimized
```

Each row has exactly ten cells (nine tab separators), including trailing empty
cells. No CSV quoting, inline comments, or multiline physical records. Double
quotes are ordinary characters. Escape textual cells using the following
single-pass mapping before joining with tabs:

| Character | On disk |
| --- | --- |
| Backslash | `\\` |
| Tab | `\t` |
| LF | `\n` |
| CR | `\r` |

On reading, split on literal tabs first, then decode text cells left to right.
Any other escape or trailing backslash is invalid. Literal NUL and other ASCII
control characters (DEL included) are invalid in metadata; tab, LF and CR are
only allowed in decoded text via the escapes above. Do not trim names, units,
or text values, perform Unicode normalization, apply CSV quoting, or interpret
strings such as `NA`, `null` or `nan` as missing text. Empty textual values are
allowed for run metadata; absence of the row means the key was not supplied.

`kind` is a nonempty ASCII identifier matching `[a-z][a-z0-9_]*`. `name` is
nonempty decoded text. The pair `(kind, name)` is unique, compared exactly
(case-sensitive UTF-8); the same name in different kinds is allowed. `unit`
is the declared physical unit, or empty if unknown or unspecified. The other
fields have these meanings:

| Field | Meaning |
| --- | --- |
| `value` | Main scalar or run text, depending on kind |
| `default_value` | Declared parameter default |
| `initial_value` | Effective decision initial value, or original all-state initial condition (see below) |
| `original_initial_value` | Prepared scalar decision before recovery, warm starts or refinement |
| `lower_bound`, `upper_bound` | Scalar optimization bounds in the same unit as the value |
| `optimized` | `1` if active in at least one launched optimizer, otherwise `0` |

Numeric cells are locale-independent IEEE binary64 decimals. Accepted finite
syntax is `[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?`;
only ASCII digits, no surrounding spaces, hexadecimal or thousands separators.
The exact special tokens are `nan`, `inf`, `-inf`. Overflow of a finite token
is an error, not an implicit infinity; rounding to binary64 (including
subnormals and underflow to signed zero) is allowed. Writers use round-trip
precision (shortest round-tripping decimal or equivalent), preserve signed
zero and emit the canonical special tokens. NaN payloads are not preserved.
An empty optional numeric cell is missing, distinct from zero, NaN and
infinity. `optimized` is empty (unknown), `0` or `1`, never a float or boolean
word. Numeric values are not text-escaped. The parser checks representation,
not optimization feasibility (e.g. a nonconverged result may be exported).

### Categories and field applicability

`value` is required and numeric for known numeric categories. Run values are
text on disk, including numeric-looking values. Only the listed auxiliary
fields may be nonempty for a known category. Optional fields may be absent
when an older HDF5 file or result lacks them. Writers populate every applicable
field for which the source has information, including fixed/inactive choices.

| Kind | Meaning of `value` | Applicable auxiliary fields |
| --- | --- | --- |
| `simulation` | Run metadata text | none |
| `fit` | Run metadata text | none |
| `parameter` | Configured parameter value | `unit`, `default_value` |
| `constant` | Model constant | `unit` |
| `initial_state` | Effective initial condition used for simulation/replay | `unit`, `initial_value` (original all-state condition in a fit) |
| `fit_parameter` | Fitted scalar parameter | `unit`, `initial_value`, `original_initial_value`, `lower_bound`, `upper_bound`, `optimized` |
| `fit_initial_state` | Fitted selected initial state | same as `fit_parameter` |
| `fit_input` | Knot interval (seconds), not a fitted input value | `unit` (exactly `s`) |
| `tf_parameter` | Scalar TF identification metadata | `unit` |

`tf_parameter` is defined for interchange and future export support, not a
requirement to add a new TF result-saving API during this migration. Unknown
kinds and unknown run keys must not break parsing; retain their decoded data
and re-emit it on a format-preserving save. For unknown kinds, `value` is
opaque text and all other non-key fields may be present (numeric auxiliary
fields and `optimized` retain their syntax). Do not infer plotting or model
application semantics for unknown kinds. A later incompatible layout requires
a new version. Unknown columns are not allowed in version 1.

Order has no semantic significance. For deterministic export, group by
`simulation`, `fit`, `fit_input`, `parameter`, `initial_state`,
`fit_parameter`, `fit_initial_state`, `tf_parameter`, `constant` (unknown
kinds last in encounter order). Within a group preserve model/result order,
or run-key order below. Readers must accept any order. The pane must use
identical ordering for equivalent inputs (e.g. sort names within a section
by decoded UTF-8 bytes, and use the specified order for known run keys).

### Run keys

Use the existing HDF5 keys, without renaming:

- `simulation`: `simulation_date`, `started_at`, `ended_at`,
  `elapsed_seconds`, `converged`, `pre_initialized`, `integration_method`,
  `input_file` (if present).
- `fit`: `fit_date`, `started_at`, `ended_at`, `elapsed_seconds`,
  `converged`, `commit_on_success`, `params_committed`,
  `integration_method`, `input_file`, `minimization_method`,
  `simulation_count`.

Writers use `YYYY-MM-DD` and UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`, following
`cy_wall_time_format()`, canonical decimal seconds and decimal integer count,
existing method aliases and `true`/`false` strings. Preserve legacy HDF5 run
strings as text rather than parsing/reformatting them (including empty values
and any older spellings). A fit need not fabricate a separate `simulation`
run section. Omit unavailable metadata rather than synthesizing a date, method
or elapsed time. `unit` remains empty for run keys; the units of
`elapsed_seconds` and timestamp fields are implied by the key.

### Semantics, units and HDF5 mapping

The normalized scalar schema is shared between the two formats. Dataset
prefixes below refer to root datasets. Vectors are aligned by index within
one group; `names`, `units`, `values` are required together when the group
exists. Optional vectors missing in older HDF5 files produce empty TSV cells;
inconsistent vector lengths are errors. Absent groups produce no rows.

| TSV kind | HDF5 datasets / mapping |
| --- | --- |
| `simulation` | `/simulation_metadata_names`, `/simulation_metadata_values` |
| `fit` | `/fit_metadata_names`, `/fit_metadata_values` |
| `parameter` | `/param_names`, `/param_units`, `/param_values`, `/param_default_values` |
| `constant` | `/constant_names`, `/constant_units`, `/constant_values` |
| `initial_state` | `/initial_state_names`, `/initial_state_units`, `/initial_state_values`, `/initial_state_fitted_values` |
| `fit_parameter` | `/fit_param_names`, `/fit_param_units`, `/fit_param_values`, `/fit_param_initial_values`, `/fit_param_original_initial_values`, `/fit_param_lower_bounds`, `/fit_param_upper_bounds`, `/fit_param_optimized` |
| `fit_initial_state` | `/fit_initial_state_names`, `/fit_initial_state_units`, `/fit_initial_state_values`, `/fit_initial_state_initial_values`, `/fit_initial_state_original_initial_values`, `/fit_initial_state_lower_bounds`, `/fit_initial_state_upper_bounds`, `/fit_initial_state_optimized` |
| `fit_input` | `/fit_input_names`, `/fit_input_knot_intervals` |
| `tf_parameter` | `/tf_param_names`, `/tf_param_units`, `/tf_param_values` |

The actual cystemas dataset prefixes are `param`, `fit_param` and `tf_param`;
the current csv_plotter reader and its tests instead use `parameter`,
`fit_parameter` and `tf_parameter`. The shared Python HDF5 adapter must
recognize both spellings, including associated optional vectors. Use the
cystemas prefixes for new HDF5 output. Resolve aliases per group, not per
field: if both groups are present, require equivalent normalized values
(including optional fields), otherwise report ambiguous metadata. Do not
silently merge inconsistent vectors. Existing HDF5 saves preserve the source
layout rather than rewriting unrelated datasets.

For the all-state group in a fit, HDF5 `/initial_state_values` contains the
original conditions and `/initial_state_fitted_values` the effective
`result->simulation.X0`. Map the former to `initial_value` and the latter to
`value`. For a simulation, map `/initial_state_values` to `value` and leave
`initial_value` empty; ordinary simulation HDF5 initial-state export is a
planned addition, not current behavior. If reading an older fit with only the
original all-state vector, do not claim that it is the effective replay state:
retain the original for display and report incomplete metadata for any
conversion requiring the effective value. This case cannot be faithfully
serialized as a version-1 `initial_state` row without the effective value.
Do not derive all-state conditions from selected decisions or time-series
samples. Selected state rows are distinct from all-state rows, including when
the same name occurs in both.

Keep fully qualified subsystem names as emitted by existing metadata writers.
`parameter` is configured/model metadata, not necessarily the fitted value
(e.g. `commit_on_success` is false); `fit_parameter` is the result snapshot.
Do not overwrite one with the other. All decision fields have the semantics
of `CyFitValueResult`; `initial_value` can change during refinement, and
`original_initial_value` and `optimized` refer to the entire run.

Use the same native declared units and scalar values as HDF5 metadata, not
converted time-series display units. This matters for nonlinear absolute
state units, where the existing separate decisions TSV can apply a different
conversion. All values, defaults and bounds in a row share its unit. Any
conversion for display or application must convert the values and units
consistently in both readers. Do not convert infinite bounds to finite ones.
Simulation export currently reads configured parameters at save time; exact
run snapshots require a later implementation change. Do not silently label
live parameters as a snapshot of a previous run.

The fitted input knot interval is included for metadata-pane parity. Do not
store fitted input knot counts, knot times or knot values in this version's
metadata table. HDF5 retains `/fit_input_knot_counts`, `/fit_input_knot_times`
and `/fit_input_knot_values`; TSV is not a complete input checkpoint. Sampled
input trajectories in the time-series table are unchanged and must not be
used to reconstruct optimizer knots implicitly. Unrecognized HDF5 datasets
and attributes are outside version-1 parity guarantees.

## Time-series table

After `# timeseries`, write exactly the conventional TSV header and numeric
rows that the corresponding time-series-only export would write. Existing
column names, bracketed units, optional `{color="..."}` suffixes, numeric
precision policy, duplicate-name handling and unquoted-cell conventions
remain unchanged. Metadata-cell escaping does not apply to this section.
A nonempty header is mandatory; a header with zero samples is structurally valid, but
existing time-series APIs may reject an empty trajectory. No extra marker or
signature may occur in this section. Consumers use their existing table
validation rules: cystemas time-series loaders require `time` or `t`, while
csv_plotter can select another X column. The detector does not impose a time
column on legacy or extended files. A metadata-only input to a time-series
loader reports that the time-series section is absent; it is not an empty
trajectory. Plain time-series exports have no added signature or marker.

## Reader, API and display contract

Keep existing `cy_save_tsv_path()` and `cy_fit_save_tsv_path()` (and suffix
variants) time-series-only. Add metadata-only and complete saving APIs for
simulation and fitting (`cy_save_metadata_tsv_path()`,
`cy_save_complete_tsv_path()`, `cy_fit_save_metadata_tsv_path()`,
`cy_fit_save_complete_tsv_path()`; names to be finalized in implementation).
Existing separate decisions saving remains unchanged. New readers may load
metadata independently or load both sections. Existing time-series readers
skip the metadata section of a combined file. Metadata loading must never
apply parameters or initial states automatically. Conversion/checkpoint APIs
must explicitly handle data that cannot be preserved, particularly input knots.

Both csv_plotter loaders normalize to the same metadata categories, units,
values, optional fields and run-key strings. Use a single metadata pane
renderer, with the same section titles, order, labels and numeric formatting
for equivalent HDF5 and TSV contents, excluding file identity. Preserve the
existing Parameters, Fitted parameters, Constants, Simulation, Fitting,
Optimized inputs and TF identification sections; add Initial states and
Fitted initial states and expose defaults, original decisions and flags.
Missing optional fields appear blank in both formats. Unknown categories
may be shown as generic metadata but must not become numerical signals by
inference. Input knot sequences are not part of the shared scalar pane.

Preserve the existing scalar selector namespaces `parameters.<name>`,
`fit_parameters.<name>`, `constants.<name>` and `tf_parameters.<name>`.
Use `initial_states.<name>` and `fit_initial_states.<name>` for the new state
categories. Plot the main `value`, not bounds/defaults/history, using the
same collision policy and units for both formats. A scalar is stored once
and broadcast over the selected X values only when plotting or evaluating
an expression; do not insert repeated columns into the loaded data table.
Metadata-only files open the metadata pane without inventing a time axis.
On reload clear old metadata, and on format-preserving saves retain the
metadata and the original file variant (including unknown rows). Editing
trajectories does not implicitly change stored scalar metadata.

## Reference fixtures and acceptance

`tests/fixtures/tsv_v1/manifest.json` lists file classifications, expected
errors and comparison pairs. `expected_metadata.json` records decoded rows
with null for unavailable auxiliary numeric fields and string tokens for
nonfinite numbers. The synthetic HDF5 pairs use the root datasets described
above; they are reference inputs, not output from a real simulation or fit.
Compare normalized scalar data by `(kind, name)`, numeric binary64 values
(with explicit NaN and signed-zero handling), and time-series columns by
name, unit, color and samples. Do not compare file bytes across HDF5 and TSV.
The paired simulation HDF5 fixture includes the planned initial-state
metadata. Both repositories carry identical fixture bytes. A fixture marked
legacy tests routing only unless otherwise specified; a malformed fixture
must fail as extended, never be reinterpreted as legacy.
