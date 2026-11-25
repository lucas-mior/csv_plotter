"""Shared scalar result metadata and the Cystemas HDF5 adapter.

The normalized rows follow tsv-format.md. Missing auxiliary fields are None;
run metadata is text, and scalar values are native-unit binary64 numbers.
The adapter needs only an open HDF5 handle, not GTK or a time-series table.
"""

import math
import numpy as np


METADATA_FIELDS = (
    "kind", "name", "value", "unit", "default_value", "initial_value",
    "original_initial_value", "lower_bound", "upper_bound", "optimized",
)

SCALAR_NAMESPACES = {
    "parameter": "parameters",
    "constant": "constants",
    "fit_parameter": "fit_parameters",
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

    The canonical rows retain all metadata, including state snapshots and
    unknown kinds. These views expose the pre-existing pane sections only;
    additional state sections will be added alongside TSV pane parity.
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
