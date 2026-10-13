"""Column names, units and delimited-file I/O for csv_plotter."""

import csv
from collections import Counter
from dataclasses import dataclass
import re
import unicodedata

import pandas as pd


@dataclass
class ColumnInfo:
    """Keep source, expression and user-interface identities separate."""

    source_name: str
    internal_name: str
    unit: str = ""
    color: str = ""

    @property
    def display_label(self):
        if self.unit:
            if self.unit.startswith("[") and self.unit.endswith("]"):
                return f"{self.source_name} {self.unit}"
            return f"{self.source_name} [{self.unit}]"
        return self.source_name


def split_tsv_header(header):
    """Split a trailing Cystemas-style ``[unit]`` from a column header."""
    trimmed = header.rstrip(" \t\r")
    if not trimmed.endswith("]"):
        return header, ""

    opening = trimmed.rfind("[")
    if opening < 0:
        return header, ""

    name = trimmed[:opening].rstrip(" \t")
    unit = trimmed[opening + 1:-1].strip(" \t")
    return name, unit


def unit_suffix(unit):
    """Create a predictable, identifier-safe component from a unit."""
    unit = unit.replace("°", "deg").replace("%", "percent")
    unit = unit.replace("µ", "u").replace("μ", "u")
    unit = unit.replace("Ω", "ohm").replace("^", "")
    unit = unicodedata.normalize("NFKD", unit)
    unit = unit.encode("ascii", errors="ignore").decode("ascii")
    suffix = re.sub(r"[^a-zA-Z0-9]+", "_", unit).strip("_").lower()
    return suffix or "unit"


def unique_name(candidate, used):
    """Avoid replacing an existing variable, including a real suffixed name."""
    if candidate not in used:
        return candidate

    serial = 2
    while f"{candidate}_{serial}" in used:
        serial += 1
    return f"{candidate}_{serial}"


def resolve_column_names(source_names, units):
    """Assign stable internal names, suffixing only duplicate source names.

    Existing distinct names take precedence over generated names, and the
    assignment among different units does not depend on column order.
    """
    if len(source_names) != len(units):
        raise ValueError("Column names and units must have the same length")
    if any(not name for name in source_names):
        raise ValueError("File contains an empty column name")

    counts = Counter(source_names)
    used = {name for name, count in counts.items() if count == 1}
    resolved = [None] * len(source_names)
    duplicate_indices = [i for i, name in enumerate(source_names)
                         if counts[name] > 1]

    for i, name in enumerate(source_names):
        if counts[name] == 1:
            resolved[i] = name

    # Make the suffix allocation deterministic for distinct units. Repeated
    # entries with the same source name AND unit necessarily need ordinals.
    duplicate_indices.sort(key=lambda i: (
        source_names[i], unit_suffix(units[i]), units[i], i))
    for i in duplicate_indices:
        candidate = f"{source_names[i]}_{unit_suffix(units[i])}"
        resolved[i] = unique_name(candidate, used)
        used.add(resolved[i])

    return resolved


class ColumnRegistry:
    """Metadata keyed by the unique names used in the Pandas DataFrame."""

    def __init__(self, entries=()):
        self._entries = {entry.internal_name: entry for entry in entries}
        if len(self._entries) != len(entries):
            raise ValueError("Duplicate internal column names")

    @classmethod
    def from_columns(cls, names, units, colors=None):
        names = [str(name) for name in names]
        units = [str(unit).strip() for unit in units]
        if colors is None:
            colors = [""] * len(names)
        if len(colors) != len(names):
            raise ValueError("Column names and colors must have the same length")
        colors = [str(color) for color in colors]
        internal_names = resolve_column_names(names, units)
        return cls([ColumnInfo(source, internal, unit, color)
                    for source, internal, unit, color in zip(
                        names, internal_names, units, colors)])

    def names(self):
        return list(self._entries)

    def get(self, name):
        return self._entries.get(name)

    def units(self):
        return {name: info.unit for name, info in self._entries.items()}

    def colors(self, names):
        """Return optional color metadata in the exact DataFrame column order."""
        return [self._entries[name].color for name in names]

    def headers(self, names):
        result = []
        for name in names:
            info = self._entries[name]
            if info.unit:
                result.append(f"{info.source_name}[{info.unit}]")
            else:
                result.append(info.source_name)
        return result

    def source_names(self, names):
        return [self._entries[name].source_name for name in names]

    def add(self, source_name, unit=""):
        if not source_name:
            raise ValueError("Column name cannot be empty")
        candidate = source_name
        if candidate in self._entries:
            candidate = f"{source_name}_{unit_suffix(unit)}"
        internal = unique_name(candidate, self._entries)
        info = ColumnInfo(source_name, internal, unit)
        self._entries[internal] = info
        return info

    def rename(self, old_name, new_source_name, unit=None):
        if not new_source_name:
            raise ValueError("Column name cannot be empty")
        info = self._entries[old_name]
        if unit is None:
            unit = info.unit
        if new_source_name == info.source_name and unit == info.unit:
            return info
        self._entries.pop(old_name)
        try:
            new_name = new_source_name
            if (new_name in self._entries or any(
                    entry.source_name == new_source_name
                    for entry in self._entries.values())):
                new_name = f"{new_source_name}_{unit_suffix(unit)}"
            new_name = unique_name(new_name, self._entries)
            info = ColumnInfo(new_source_name, new_name, unit, info.color)
            self._entries[new_name] = info
            return info
        except Exception:
            self._entries[old_name] = info
            raise

    def remove(self, name):
        self._entries.pop(name, None)

    def resolve_reference(self, label):
        """Resolve backtick names, allowing human-readable labels with units."""
        if label in self._entries:
            return label

        matches = [name for name, info in self._entries.items()
                   if info.display_label == label]
        if len(matches) == 1:
            return matches[0]

        matches = [name for name, info in self._entries.items()
                   if info.source_name == label]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise ValueError(
                f"Ambiguous variable {label!r}; use its unit-qualified "
                "label in backticks or its internal name")
        return None


def read_delimited(filename, delimiter):
    """Preserve duplicate raw headers before Pandas can mangle their names."""
    with open(filename, "r", encoding="utf-8-sig", newline="") as stream:
        try:
            header = next(csv.reader(stream, delimiter=delimiter))
        except StopIteration as exception:
            raise ValueError("File has no header") from exception

    parsed = [split_tsv_header(header_name) for header_name in header]
    registry = ColumnRegistry.from_columns(
        [name for name, _ in parsed], [unit for _, unit in parsed])
    frame = pd.read_csv(filename, sep=delimiter)
    if len(frame.columns) != len(header):
        raise ValueError("Header does not match the number of data columns")
    frame.columns = registry.names()
    return frame, registry


def read_tsv(filename):
    """Load Cystemas TSV column names and units separately."""
    return read_delimited(filename, "\t")


def read_csv(filename):
    """Accept optional Cystemas-style units in CSV headers as well."""
    return read_delimited(filename, ",")


def write_delimited(filename, frame, registry, delimiter):
    """Save original (possibly duplicate) source names and unit metadata."""
    frame.to_csv(filename, sep=delimiter, index=False,
                 header=registry.headers(frame.columns))


def write_tsv(filename, frame, registry):
    write_delimited(filename, frame, registry, "\t")


def write_csv(filename, frame, registry):
    write_delimited(filename, frame, registry, ",")
