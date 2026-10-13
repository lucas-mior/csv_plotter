"""Cystemas-style units in TSV column headers."""

import pandas as pd


def split_tsv_header(header):
    """Split a trailing ``[unit]`` suffix from a TSV column name."""
    trimmed = header.rstrip(" \t\r")
    if not trimmed.endswith("]"):
        return header, ""

    opening = trimmed.rfind("[")
    if opening < 0:
        return header, ""

    name = trimmed[:opening].rstrip(" \t")
    unit = trimmed[opening + 1:-1].strip(" \t")
    return name, unit


def read_tsv(filename):
    """Load a TSV with column names and units stored separately."""
    data_frame = pd.read_csv(filename, sep="\t")
    parsed = [split_tsv_header(str(name)) for name in data_frame.columns]
    names = [name for name, _ in parsed]

    if any(not name for name in names):
        raise ValueError("TSV contains an empty column name")
    if len(names) != len(set(names)):
        duplicates = sorted({name for name in names if names.count(name) > 1})
        raise ValueError(
            "TSV contains duplicate column names after removing units: "
            + ", ".join(duplicates))

    data_frame.columns = names
    units = {name: unit for name, unit in parsed}
    return data_frame, units


def write_tsv(filename, data_frame, column_units):
    """Save column names and units using the Cystemas TSV convention."""
    headers = []
    for name in data_frame.columns:
        name = str(name)
        unit = str(column_units.get(name, "")).strip()
        headers.append(f"{name}[{unit}]" if unit else name)

    data_frame.to_csv(filename, sep="\t", index=False, header=headers)
