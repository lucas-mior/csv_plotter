"""Shared scalar metadata, Cystemas HDF5 and extended TSV adapters.

The normalized rows follow tsv-format.md. Missing auxiliary fields are None;
run metadata is text, and scalar values are native-unit binary64 numbers.
The format adapters are independent of GTK.
"""

import io
import math
import re
import numpy as np
import pandas as pd


METADATA_FIELDS = (
    "kind", "name", "value", "unit", "default_value", "initial_value",
    "original_initial_value", "lower_bound", "upper_bound", "optimized",
)

SCALAR_NAMESPACES = {
    "parameter": "parameters",
    "constant": "constants",
    "fit_parameter": "fit_parameters",
    "initial_state": "initial_states",
    "fit_initial_state": "fit_initial_states",
    "tf_parameter": "tf_parameters",
}

DECISION_FIELDS = {
    "initial_value": "initial_values",
    "original_initial_value": "original_initial_values",
    "lower_bound": "lower_bounds",
    "upper_bound": "upper_bounds",
    "optimized": "optimized",
}


def normalize_metadata_rows(rows):
    """Copy rows into the common schema, rejecting duplicate identities.

    Readers are responsible for validating their own serialized input.
    None as a main value is reserved for incomplete legacy state snapshots.
    """
    result = []
    seen = set()
    for row in rows:
        key = (row["kind"], row["name"])
        if key in seen:
            raise ValueError(f"Duplicate metadata key: {key!r}")
        seen.add(key)
        normalized = {field: row.get(field) for field in METADATA_FIELDS}
        normalized["unit"] = row.get("unit", "")
        result.append(normalized)
    return result


def metadata_views(rows, column_names=()):
    """Derive existing pane and scalar-selector views from normalized rows.

    The pane reads the canonical rows, including missing effective states and
    unknown kinds. Only known, available scalar values become plot selectors.
    """
    named = []
    runs = {"simulation": [], "fit": []}
    inputs = []
    for row in rows:
        kind = row["kind"]
        if kind in runs:
            runs[kind].append({"name": row["name"], "value": row["value"]})
        elif kind == "fit_input":
            inputs.append({"name": row["name"], "knot_interval": row["value"]})
        elif kind in SCALAR_NAMESPACES and row["value"] is not None:
            # Keep optional missing fields absent in the legacy pane views.
            value = {key: item for key, item in row.items() if item is not None}
            value["display_name"] = f"{SCALAR_NAMESPACES[kind]}.{row['name']}"
            named.append(value)

    # Preserve all noncolliding names. Allocate deterministic suffixes only
    # when a trajectory column occupies the scalar's preferred plot name.
    used = set(column_names)
    reserved = used | {row["display_name"] for row in named}
    for row in sorted(named, key=lambda item: item["display_name"]):
        base = row["display_name"]
        if base in used:
            suffix = 2
            while f"{base}_{suffix}" in reserved:
                suffix += 1
            row["display_name"] = f"{base}_{suffix}"
            reserved.add(row["display_name"])
        used.add(row["display_name"])
    return named, runs["simulation"], runs["fit"], inputs


def read_hdf5_strings(hdf5_file, dataset_name, count=None):
    values = hdf5_file[dataset_name][()]
    if np.asarray(values).ndim != 1:
        raise ValueError(
            f"HDF5 /{dataset_name} dataset must have 1 dimension")
    strings = []
    for value in values:
        if isinstance(value, bytes):
            raw_text = value
        elif isinstance(value, np.bytes_):
            raw_text = bytes(value)
        else:
            strings.append(str(value))
            continue

        raw_text = raw_text.split(b"\0", maxsplit=1)[0]
        strings.append(raw_text.decode("utf-8"))

    if count is not None and len(strings) != count:
        raise ValueError(
            f"HDF5 dataset {dataset_name} has {len(strings)} entries, "
            f"expected {count}")
    return strings


def read_hdf5_float_vector(hdf5_file, dataset_name, count=None):
    values = np.array(hdf5_file[dataset_name], dtype=np.float64)
    if values.ndim != 1:
        raise ValueError(
            f"HDF5 /{dataset_name} dataset must have 1 dimension")
    if count is not None and len(values) != count:
        raise ValueError(
            f"HDF5 dataset /{dataset_name} has {len(values)} entries, "
            f"expected {count}")
    return values


def _read_hdf5_group(handle, prefix, kind, optional_fields):
    required = [f"{prefix}_{suffix}" for suffix in ("names", "units", "values")]
    optional = {field: f"{prefix}_{suffix}"
                for field, suffix in optional_fields.items()}
    if not any(path in handle for path in required + list(optional.values())):
        return None
    if not all(path in handle for path in required):
        raise ValueError(f"HDF5 file has incomplete /{prefix}_* metadata")
    names = read_hdf5_strings(handle, required[0])
    units = read_hdf5_strings(handle, required[1], len(names))
    values = read_hdf5_float_vector(handle, required[2], len(names))
    rows = [{"kind": kind, "name": name, "unit": unit, "value": float(value)}
            for name, unit, value in zip(names, units, values)]
    for field, path in optional.items():
        if path not in handle:
            continue
        vector = read_hdf5_float_vector(handle, path, len(names))
        for row, value in zip(rows, vector):
            if field == "optimized":
                if value not in (0, 1):
                    raise ValueError(f"Invalid optimized flag in /{path}")
                row[field] = int(value)
            else:
                row[field] = float(value)
    if len(set(names)) != len(names):
        raise ValueError(f"Duplicate metadata name in /{prefix}_names")
    return rows


def _same_value(left, right):
    if isinstance(left, float) and isinstance(right, float):
        if math.isnan(left) and math.isnan(right):
            return True
        if left == right == 0:
            return math.copysign(1, left) == math.copysign(1, right)
    return left == right


def _same_group(left, right):
    by_name = {row["name"]: row for row in right}
    if len(left) != len(right):
        return False
    for row in left:
        other = by_name.get(row["name"])
        if other is None or row.keys() != other.keys():
            return False
        if not all(_same_value(value, other[field])
                   for field, value in row.items()):
            return False
    return True


def read_hdf5_named_values(handle, kind):
    """Read a scalar group, resolving aliases as whole groups."""
    aliases = {"parameter": "param", "fit_parameter": "fit_param",
               "tf_parameter": "tf_param"}
    fields = {}
    if kind == "parameter":
        fields = {"default_value": "default_values"}
    elif kind in ("fit_parameter", "fit_initial_state"):
        fields = DECISION_FIELDS
    elif kind == "initial_state":
        fields = {"fitted_value": "fitted_values"}

    if kind not in aliases:
        return _read_hdf5_group(handle, kind, kind, fields) or []
    canonical = _read_hdf5_group(handle, aliases[kind], kind, fields)
    legacy = _read_hdf5_group(handle, kind, kind, fields)
    if canonical is not None and legacy is not None:
        if not _same_group(canonical, legacy):
            raise ValueError(f"Conflicting HDF5 metadata aliases for {kind}")
    return canonical if canonical is not None else (legacy or [])


def _read_hdf5_text_metadata(handle, kind):
    names_path = f"{kind}_metadata_names"
    values_path = f"{kind}_metadata_values"
    if names_path not in handle and values_path not in handle:
        return []
    if names_path not in handle or values_path not in handle:
        raise ValueError(f"HDF5 file has incomplete /{kind}_metadata_*")
    names = read_hdf5_strings(handle, names_path)
    values = read_hdf5_strings(handle, values_path, len(names))
    return [{"kind": kind, "name": name, "value": value}
            for name, value in zip(names, values)]


def _read_hdf5_fit_inputs(handle):
    names_path = "fit_input_names"
    intervals_path = "fit_input_knot_intervals"
    if names_path not in handle and intervals_path not in handle:
        return []
    if names_path not in handle or intervals_path not in handle:
        raise ValueError("HDF5 file has incomplete /fit_input_* metadata")
    names = read_hdf5_strings(handle, names_path)
    intervals = read_hdf5_float_vector(handle, intervals_path, len(names))
    return [{"kind": "fit_input", "name": name, "unit": "s",
             "value": float(interval)} for name, interval in zip(names, intervals)]


def read_hdf5_metadata(handle):
    """Return normalized scalar rows without reading trajectories or knots."""
    simulation = _read_hdf5_text_metadata(handle, "simulation")
    fit = _read_hdf5_text_metadata(handle, "fit")
    fitted_parameters = read_hdf5_named_values(handle, "fit_parameter")
    fitted_states = read_hdf5_named_values(handle, "fit_initial_state")
    inputs = _read_hdf5_fit_inputs(handle)
    is_fit = bool(fit or fitted_parameters or fitted_states or inputs
                  or "fit_metadata_names" in handle
                  or "initial_state_fitted_values" in handle)
    states = read_hdf5_named_values(handle, "initial_state")
    for row in states:
        if is_fit:
            row["initial_value"] = row["value"]
            # An older fit may provide only the original conditions.
            # Do not claim these are effective replay conditions.
            row["value"] = row.pop("fitted_value", None)
    rows = (simulation + fit + inputs
            + read_hdf5_named_values(handle, "parameter") + states
            + fitted_parameters + fitted_states
            + read_hdf5_named_values(handle, "tf_parameter")
            + read_hdf5_named_values(handle, "constant"))
    return normalize_metadata_rows(rows)


# Extended TSV version 1. The C detector uses these same exact markers.
TSV_PREFIX = "# cystemas-tsv:"
TSV_SIGNATURE = TSV_PREFIX + "1"
TSV_METADATA_MARKER = "# metadata"
TSV_TIMESERIES_MARKER = "# timeseries"
TSV_METADATA_HEADER = "\t".join(METADATA_FIELDS)

TSV_AUX_FIELDS = {
    "simulation": (), "fit": (),
    "parameter": ("unit", "default_value"),
    "constant": ("unit",), "tf_parameter": ("unit",),
    "initial_state": ("unit", "initial_value"),
    "fit_parameter": ("unit", *DECISION_FIELDS),
    "fit_initial_state": ("unit", *DECISION_FIELDS),
    "fit_input": ("unit",),
}
TSV_TEXT_KINDS = ("simulation", "fit")
TSV_KIND_ORDER = ("simulation", "fit", "fit_input", "parameter",
                  "initial_state", "fit_parameter", "fit_initial_state",
                  "tf_parameter", "constant")
TSV_RUN_KEY_ORDER = {
    "simulation": ("simulation_date", "started_at", "ended_at", "elapsed_seconds",
                   "converged", "pre_initialized", "integration_method", "input_file"),
    "fit": ("fit_date", "started_at", "ended_at", "elapsed_seconds", "converged",
            "commit_on_success", "params_committed", "integration_method", "input_file",
            "minimization_method", "simulation_count"),
}


class TsvFormatError(ValueError):
    def __init__(self, code, line, message):
        self.code = code
        self.line = line
        super().__init__(f"Invalid extended TSV at line {line}: {message}")


def _tsv_decode_text(text, line):
    escapes = {"\\": "\\", "t": "\t", "n": "\n", "r": "\r"}
    result = []
    pos = 0
    while pos < len(text):
        char = text[pos]
        if ord(char) < 32 or ord(char) == 127:
            raise TsvFormatError("escape", line, "invalid text control character")
        if char == "\\":
            pos += 1
            if pos == len(text) or text[pos] not in escapes:
                raise TsvFormatError("escape", line, "invalid text escape")
            char = escapes[text[pos]]
        result.append(char)
        pos += 1
    return "".join(result)


def _tsv_number(text, line, required=False):
    if not text:
        if required:
            raise TsvFormatError("missing_numeric_value", line,
                                 "missing numeric metadata value")
        return None
    if text in ("nan", "inf", "-inf"):
        return float(text)
    if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text):
        raise TsvFormatError("numeric_syntax", line, "invalid metadata number")
    value = float(text)
    if not math.isfinite(value):
        raise TsvFormatError("numeric_overflow", line, "metadata number overflows binary64")
    return value


def _tsv_metadata_row(text, line):
    if not text:
        raise TsvFormatError("blank_metadata_line", line, "blank metadata line")
    cells = text.split("\t")
    if len(cells) != len(METADATA_FIELDS):
        raise TsvFormatError("cell_count", line, "expected ten metadata cells")
    kind = cells[0]
    if not re.fullmatch(r"[a-z][a-z0-9_]*", kind):
        raise TsvFormatError("kind", line, "invalid metadata kind")
    name, value, unit = (_tsv_decode_text(cell, line) for cell in cells[1:4])
    if not name:
        raise TsvFormatError("name", line, "empty metadata name")
    if kind in TSV_AUX_FIELDS and kind not in TSV_TEXT_KINDS:
        value = _tsv_number(value, line, required=True)
    row = dict(zip(METADATA_FIELDS[:4], (kind, name, value, unit)))
    for field, cell in zip(METADATA_FIELDS[4:-1], cells[4:-1]):
        row[field] = _tsv_number(cell, line)
    if cells[-1] not in ("", "0", "1"):
        raise TsvFormatError("optimized_flag", line, "invalid optimized flag")
    row["optimized"] = int(cells[-1]) if cells[-1] else None
    if kind in TSV_AUX_FIELDS:
        for field in METADATA_FIELDS[3:]:
            if field not in TSV_AUX_FIELDS[kind] and row[field] not in (None, ""):
                raise TsvFormatError("inapplicable_field", line,
                                     f"inapplicable metadata field {field}")
    if kind == "fit_input" and unit != "s":
        raise TsvFormatError("input_interval_unit", line, "fit input interval unit must be s")
    return row


def _tsv_physical_line(raw, line):
    if raw.endswith(b"\n"):
        raw = raw[:-1]
        if raw.endswith(b"\r"):
            raw = raw[:-1]
    if b"\r" in raw:
        raise TsvFormatError("bare_cr", line, "bare CR")
    if b"\0" in raw:
        raise TsvFormatError("nul", line, "NUL byte")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TsvFormatError("invalid_utf8", line, "invalid UTF-8") from exc


def scan_tsv_sections(stream):
    """Validate extended sections on a binary stream; return variant, rows, offset.

    The offset points to the conventional header, or is None if absent.
    Legacy candidates are left to the unchanged legacy table reader.
    """
    stream.seek(0)
    first = stream.readline()
    if first.startswith(b"\xef\xbb\xbf"):
        first = first[3:]
    if not first.startswith(TSV_PREFIX.encode("ascii")):
        return "legacy", [], 0
    if _tsv_physical_line(first, 1) != TSV_SIGNATURE:
        raise TsvFormatError("unsupported_version", 1, "unsupported or malformed TSV version")
    for line, expected, code in ((2, TSV_METADATA_MARKER, "metadata_marker"),
                                 (3, TSV_METADATA_HEADER, "metadata_header")):
        if _tsv_physical_line(stream.readline(), line) != expected:
            raise TsvFormatError(code, line, f"expected {expected}")
    rows = []
    seen = set()
    offset = None
    header_found = False
    line = 3
    for raw in stream:
        line += 1
        text = _tsv_physical_line(raw, line)
        if offset is None:
            if text == TSV_TIMESERIES_MARKER:
                offset = stream.tell()
                continue
            row = _tsv_metadata_row(text, line)
            key = (row["kind"], row["name"])
            if key in seen:
                raise TsvFormatError("duplicate_key", line, "duplicate metadata key")
            seen.add(key)
            rows.append(row)
        else:
            if (text in (TSV_METADATA_MARKER, TSV_TIMESERIES_MARKER)
                    or text.startswith(TSV_PREFIX)):
                raise TsvFormatError("extra_section", line, "unexpected extra section")
            if not header_found:
                if not text.strip(" \t"):
                    raise TsvFormatError("missing_timeseries_header", line,
                                         "missing time-series header")
                header_found = True
            elif text.startswith("#"):
                raise TsvFormatError("extra_section", line, "unexpected time-series comment")
    if offset is not None and not header_found:
        raise TsvFormatError("missing_timeseries_header", line + 1,
                             "missing time-series header")
    return ("metadata_only" if offset is None else "combined"), rows, offset


def read_result_tsv(filename):
    """Return variant, normalized rows, frame and registry (no table if absent)."""
    from csv_plotter_units import ColumnRegistry, read_delimited

    with open(filename, "rb") as stream:
        variant, rows, offset = scan_tsv_sections(stream)
        if variant == "metadata_only":
            return variant, rows, pd.DataFrame(), ColumnRegistry()
        if variant == "legacy":
            frame, registry = read_delimited(filename, "\t")
        else:
            # Reuse the same file descriptor after validation. TextIOWrapper
            # supports absolute byte offsets at UTF-8 character boundaries.
            stream.seek(offset)
            with io.TextIOWrapper(stream, encoding="utf-8", newline="") as text:
                frame, registry = read_delimited(text, "\t")
    return variant, rows, frame, registry


def _tsv_encode_text(text):
    if not isinstance(text, str):
        raise ValueError("Metadata text must be a string")
    return (text.replace("\\", "\\\\").replace("\t", "\\t")
            .replace("\n", "\\n").replace("\r", "\\r"))


def serialize_tsv_metadata(rows):
    """Produce a validated version-1 metadata preamble before opening output."""
    rows = normalize_metadata_rows(rows)
    order = {kind: index for index, kind in enumerate(TSV_KIND_ORDER)}
    run_order = {kind: {name: index for index, name in enumerate(keys)}
                 for kind, keys in TSV_RUN_KEY_ORDER.items()}

    def sort_key(row):
        kind = row["kind"]
        keys = run_order.get(kind, {})
        return order.get(kind, len(order)), keys.get(row["name"], len(keys))

    rows.sort(key=sort_key)
    lines = [TSV_SIGNATURE, TSV_METADATA_MARKER, TSV_METADATA_HEADER]
    for row in rows:
        kind = row["kind"]
        numeric = kind in TSV_AUX_FIELDS and kind not in TSV_TEXT_KINDS
        cells = [kind, _tsv_encode_text(row["name"]),
                 repr(float(row["value"])) if numeric else _tsv_encode_text(row["value"]),
                 _tsv_encode_text(row["unit"])]
        cells.extend("" if row[field] is None else repr(float(row[field]))
                     for field in METADATA_FIELDS[4:-1])
        flag = row["optimized"]
        if flag is not None and flag not in (0, 1):
            raise ValueError("Invalid optimized flag")
        cells.append("" if flag is None else str(int(flag)))
        line = "\t".join(cells)
        _tsv_metadata_row(line, len(lines) + 1)
        lines.append(line)
    return "\n".join(lines) + "\n"


def write_result_tsv(filename, variant, rows, frame, registry):
    """Retain the loaded file variant; never silently discard metadata."""
    from csv_plotter_units import write_tsv, write_tsv_stream

    if variant == "legacy":
        if rows:
            raise ValueError("Legacy TSV cannot store scalar metadata")
        write_tsv(filename, frame, registry)
        return
    if variant not in ("metadata_only", "combined"):
        raise ValueError(f"Unknown TSV variant {variant!r}")
    preamble = serialize_tsv_metadata(rows)
    if variant == "metadata_only" and len(frame.columns):
        raise ValueError("Metadata-only TSV cannot store time-series columns")
    if variant == "combined":
        header = "\t".join(registry.headers(frame.columns, include_colors=True))
        if (not header.strip(" \t") or any(char in header for char in "\r\n\0")
                or header in (TSV_METADATA_MARKER, TSV_TIMESERIES_MARKER)
                or header.startswith(TSV_PREFIX)):
            raise ValueError("Invalid extended TSV time-series header")
    # Encoding failures are detected before truncating the destination.
    preamble.encode("utf-8")
    with open(filename, "w", encoding="utf-8", newline="") as stream:
        stream.write(preamble)
        if variant == "combined":
            stream.write(TSV_TIMESERIES_MARKER + "\n")
            write_tsv_stream(stream, frame, registry)
