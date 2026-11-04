"""Export and import a Simulink parameter table as CSV.

The table is a classroom convention for block, mask, model, and workspace
parameters. Simulink is not required and is not imported. A checked row's
``value_text`` is what ``set_param`` would receive; workspace and base rows
are also returned as plain dictionaries a script can assign without a model.

The column order written by :func:`write_param_table` is fixed:

    name, value, unit, description, scope, path, dtype, minimum, maximum, group

``dtype`` is ``double``, ``int``, ``logical``, or ``string``. ``scope`` is
``model``, ``block``, ``mask``, ``workspace``, or ``base``. Empty ``scope``
means ``base``. Bounds are inclusive and apply only to ``double`` and ``int``.
The same rules are implemented in ``matlab/simulink_param_export.m``.
"""

from __future__ import annotations

import csv
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

COLUMNS = (
    "name",
    "value",
    "unit",
    "description",
    "scope",
    "path",
    "dtype",
    "minimum",
    "maximum",
    "group",
)

SCOPES = ("model", "block", "mask", "workspace", "base")
DTYPES = ("double", "int", "logical", "string")
INT_LIMIT = 2**53

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_GROUP_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,31}$")
_SEGMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_ -]{0,62}$")
_INT_RE = re.compile(r"^[+-]?\d+$")
_DOUBLE_RE = re.compile(r"^[+-]?(?:\d+\.\d+|\d+|\.\d+)(?:[eE][+-]?\d+)?$")

_SEPARATORS = set("./^·-")
_UNIT_EXTRAS = set("Ωµμ°")
_LOGICAL_TRUE = {"true", "yes", "on", "1"}
_LOGICAL_FALSE = {"false", "no", "off", "0"}
_LOGICAL_WORDS = {"true", "false", "yes", "no", "on", "off"}

_HEADER_ALIAS = {
    "name": "name",
    "param": "name",
    "parameter": "name",
    "parametername": "name",
    "参数": "name",
    "参数名": "name",
    "value": "value",
    "val": "value",
    "值": "value",
    "数值": "value",
    "unit": "unit",
    "units": "unit",
    "单位": "unit",
    "description": "description",
    "desc": "description",
    "comment": "description",
    "说明": "description",
    "描述": "description",
    "scope": "scope",
    "target": "scope",
    "作用域": "scope",
    "path": "path",
    "block": "path",
    "blockpath": "path",
    "路径": "path",
    "dtype": "dtype",
    "type": "dtype",
    "datatype": "dtype",
    "类型": "dtype",
    "minimum": "minimum",
    "min": "minimum",
    "lower": "minimum",
    "下限": "minimum",
    "maximum": "maximum",
    "max": "maximum",
    "upper": "maximum",
    "上限": "maximum",
    "group": "group",
    "category": "group",
    "分组": "group",
    "类别": "group",
}

_FIELD_RANK = {
    "header": 0,
    "name": 1,
    "scope": 2,
    "path": 3,
    "dtype": 4,
    "value": 5,
    "unit": 6,
    "description": 7,
    "group": 8,
    "minimum": 9,
    "maximum": 10,
    "duplicate": 11,
}


@dataclass(frozen=True)
class ParamRow:
    """One checked parameter.

    ``value`` is a float, int, bool, or str. ``value_text`` is the canonical
    CSV spelling. ``minimum`` and ``maximum`` are ``None`` when unbounded.
    ``row_number`` is the CSV line number, or the 1-based index of an
    in-memory row. MATLAB stores ``int`` values as double and uses NaN for an
    unbounded bound; the other fields match.
    """

    name: str
    value: int | float | bool | str
    value_text: str
    unit: str
    description: str
    scope: str
    path: str
    dtype: str
    minimum: float | None
    maximum: float | None
    group: str
    row_number: int


@dataclass(frozen=True)
class ParamIssue:
    """One rejected row. ``message`` is ``field: row N detail``."""

    row_number: int
    field: str
    message: str


@dataclass
class ParamExportResult:
    """Checked rows plus the workspace and base assignments."""

    rows: list[ParamRow]
    errors: list[ParamIssue]
    workspace: dict[str, dict[str, int | float | bool | str]]
    base: dict[str, int | float | bool | str]
    output_csv: str | None
    n_rows: int
    n_errors: int
    table_text: str
    assignment_text: str


@dataclass
class _Record:
    line: int
    name: str = ""
    value: str = ""
    unit: str = ""
    description: str = ""
    scope: str = ""
    path: str = ""
    dtype: str = ""
    minimum: str = ""
    maximum: str = ""
    group: str = ""
    error_field: str = ""
    error_detail: str = ""


def simulink_param_export(
    source: str | Path | Mapping | Sequence | None = None,
    *,
    rows: Sequence | None = None,
    csv_path: str | Path | None = None,
    output_csv: str | Path | None = None,
    strict: bool = True,
) -> ParamExportResult:
    """Read, check, and optionally write a parameter table.

    ``source`` is a CSV path, one mapping, or a sequence of mappings. ``rows``
    and ``csv_path`` are the keyword forms of that input. Pass only one input.
    ``strict`` raises ``ValueError`` on the first row issue. A bad header
    always raises, because the file has no column layout to recover.
    """

    records = _resolve_records(source, rows, csv_path)
    good, errors = _validate_records(records)
    if strict and errors:
        raise ValueError(errors[0].message)
    written: str | None = None
    if output_csv is not None and str(output_csv) != "":
        destination = Path(output_csv)
        _write_rows(destination, good)
        written = str(destination)
    workspace, base = _assignments(good)
    return ParamExportResult(
        rows=good,
        errors=errors,
        workspace=workspace,
        base=base,
        output_csv=written,
        n_rows=len(good),
        n_errors=len(errors),
        table_text=format_param_table(good),
        assignment_text=format_assignments(good),
    )


def read_param_table(csv_path: str | Path) -> list[ParamRow]:
    """Read a CSV and return the checked rows. Raises on the first issue."""

    return simulink_param_export(csv_path, strict=True).rows


def write_param_table(rows: Sequence, csv_path: str | Path) -> str:
    """Check ``rows`` and write the canonical CSV. Returns the path written."""

    result = simulink_param_export(rows, output_csv=csv_path, strict=True)
    return result.output_csv or ""


def validate_param_table(
    source: str | Path | Mapping | Sequence,
) -> list[ParamIssue]:
    """Return row issues without raising. A bad header still raises."""

    return simulink_param_export(source, strict=False).errors


def format_param_table(rows: Sequence[ParamRow]) -> str:
    """Text table in file order: name, dtype, value, unit, scope, path, group."""

    header = (
        f"{'name':<12} {'dtype':<8} {'value':<10} {'unit':<12} "
        f"{'scope':<10} {'path':<22} {'group':<12}"
    )
    lines = [header]
    for row in rows:
        lines.append(
            f"{row.name:<12} {row.dtype:<8} {row.value_text:<10} {row.unit:<12} "
            f"{row.scope:<10} {row.path:<22} {row.group:<12}"
        )
    return "\n".join(lines)


def format_assignments(rows: Sequence[ParamRow]) -> str:
    """Workspace lines sorted by model and name, then one sorted base line."""

    models = sorted({row.path for row in rows if row.scope == "workspace"})
    lines: list[str] = []
    for model in models:
        pairs = sorted(
            (row.name, row.value_text)
            for row in rows
            if row.scope == "workspace" and row.path == model
        )
        body = ", ".join(f"{name}={text}" for name, text in pairs)
        lines.append(f"workspace {model}: {body}")
    base_pairs = sorted(
        (row.name, row.value_text) for row in rows if row.scope == "base"
    )
    if base_pairs:
        body = ", ".join(f"{name}={text}" for name, text in base_pairs)
        lines.append(f"base: {body}")
    return "\n".join(lines)


def param_rows_equal(left: Sequence[ParamRow], right: Sequence[ParamRow]) -> bool:
    """Compare two tables, ignoring ``row_number``."""

    if len(left) != len(right):
        return False
    return all(_same_row(a, b) for a, b in zip(left, right))


def format_double(value: float) -> str:
    """Shortest classroom spelling that parses back to the same float.

    Prefers 16 significant digits, the same idea as MATLAB ``sprintf('%.16g')``.
    Uses 17 digits only when 16 would not round-trip.
    """

    number = float(value)
    if not math.isfinite(number):
        raise ValueError("value: not finite")
    if number == 0.0:
        return "0"
    short = format(number, ".16g")
    if float(short) == number:
        return short
    return format(number, ".17g")


def _resolve_records(
    source: str | Path | Mapping | Sequence | None,
    rows: Sequence | None,
    csv_path: str | Path | None,
) -> list[_Record]:
    if source is not None and rows is not None:
        raise ValueError("rows: not both source and rows")
    if csv_path is not None and source is not None:
        raise ValueError("csv_path: not both source and csv_path")
    if csv_path is not None and rows is not None:
        raise ValueError("csv_path: not both rows and csv_path")
    if source is None and rows is None and csv_path is None:
        raise ValueError("source: required")
    if csv_path is not None:
        return _read_csv_records(Path(csv_path))
    if rows is not None:
        if isinstance(rows, (str, Path)) or not isinstance(rows, Sequence):
            raise ValueError("rows: expected a sequence of mappings")
        return _records_from_items(rows)
    if isinstance(source, (str, Path)):
        return _read_csv_records(Path(source))
    if isinstance(source, ParamRow):
        return _records_from_items([source])
    if isinstance(source, Mapping):
        return _records_from_items([source])
    if isinstance(source, Sequence):
        return _records_from_items(source)
    raise ValueError("source: expected a CSV path or rows")


def _read_csv_records(path: Path) -> list[_Record]:
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8-sig")
    kept_lines: list[str] = []
    kept_numbers: list[int] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            continue
        kept_lines.append(line)
        kept_numbers.append(number)
    if not kept_lines:
        raise ValueError("header: missing name column")
    delimiter = ";" if kept_lines[0].count(";") > kept_lines[0].count(",") else ","
    try:
        parsed = list(csv.reader(kept_lines, delimiter=delimiter))
    except csv.Error as exc:
        raise ValueError("header: unclosed quote") from exc
    columns = _map_header(parsed[0])
    records: list[_Record] = []
    for line_number, cells in zip(kept_numbers[1:], parsed[1:]):
        if len(cells) != len(columns):
            records.append(
                _Record(line=line_number, error_field="header", error_detail="field count")
            )
            continue
        data = {
            key: value.strip()
            for key, value in zip(columns, cells)
        }
        records.append(
            _Record(
                line=line_number,
                name=data.get("name", ""),
                value=data.get("value", ""),
                unit=data.get("unit", ""),
                description=data.get("description", ""),
                scope=data.get("scope", ""),
                path=data.get("path", ""),
                dtype=data.get("dtype", ""),
                minimum=data.get("minimum", ""),
                maximum=data.get("maximum", ""),
                group=data.get("group", ""),
            )
        )
    return records


def _map_header(cells: list[str]) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    for index, cell in enumerate(cells):
        label = cell.strip().lstrip("\ufeff") if index == 0 else cell.strip()
        canon = _HEADER_ALIAS.get(_norm_key(label))
        if canon is None:
            raise ValueError(f"header: unknown column {label}")
        if canon in seen:
            raise ValueError(f"header: duplicate column {canon}")
        seen.add(canon)
        columns.append(canon)
    if "name" not in seen:
        raise ValueError("header: missing name column")
    if "value" not in seen:
        raise ValueError("header: missing value column")
    return columns


def _records_from_items(items: Sequence[object]) -> list[_Record]:
    return [_record_from_item(item, index) for index, item in enumerate(items, start=1)]


def _record_from_item(item: object, line: int) -> _Record:
    if isinstance(item, ParamRow):
        item = _param_row_to_mapping(item)
    if not isinstance(item, Mapping):
        return _Record(line=line, error_field="header", error_detail="expected a mapping")
    record = _Record(line=line)
    hint = ""
    for key, raw in item.items():
        canon = _HEADER_ALIAS.get(_norm_key(str(key)))
        if canon is None:
            return _Record(line=line, error_field="header", error_detail=f"unknown field {key}")
        if canon == "value":
            text, value_hint, problem = _value_to_text(raw)
            if problem:
                return _Record(line=line, error_field="value", error_detail=problem)
            record.value = text
            hint = value_hint
            continue
        text, problem = _field_to_text(canon, raw)
        if problem:
            return _Record(line=line, error_field=canon, error_detail=problem)
        setattr(record, canon, text)
    if record.dtype.strip() == "" and hint:
        record.dtype = hint
    return record


def _param_row_to_mapping(row: ParamRow) -> dict[str, object]:
    return {
        "name": row.name,
        "value": row.value,
        "unit": row.unit,
        "description": row.description,
        "scope": row.scope,
        "path": row.path,
        "dtype": row.dtype,
        "minimum": "" if row.minimum is None else row.minimum,
        "maximum": "" if row.maximum is None else row.maximum,
        "group": row.group,
    }


def _value_to_text(raw: object) -> tuple[str, str, str]:
    if isinstance(raw, bool):
        return ("true" if raw else "false", "logical", "")
    if isinstance(raw, int):
        if abs(raw) > INT_LIMIT:
            return ("", "", "out of int range")
        return (str(raw), "int", "")
    if isinstance(raw, float):
        if not math.isfinite(raw):
            return ("", "", "not finite")
        if raw.is_integer() and abs(raw) <= INT_LIMIT:
            return (str(int(raw)), "int", "")
        return (format_double(raw), "double", "")
    if isinstance(raw, str):
        return (raw.strip(), "", "")
    return ("", "", "unsupported value class")


def _field_to_text(canon: str, raw: object) -> tuple[str, str]:
    if raw is None:
        return ("", "")
    if isinstance(raw, bool):
        return ("", "unsupported field class")
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and not math.isfinite(raw):
            if math.isnan(raw) and canon in {"minimum", "maximum"}:
                return ("", "")
            return ("", "not finite")
        if canon in {"minimum", "maximum"}:
            return (format_double(float(raw)), "")
        return (str(raw).strip(), "")
    if isinstance(raw, str):
        return (raw.strip(), "")
    return ("", "unsupported field class")


def _validate_records(records: list[_Record]) -> tuple[list[ParamRow], list[ParamIssue]]:
    good: list[ParamRow] = []
    errors: list[ParamIssue] = []
    for record in records:
        row, issue = _interpret_record(record)
        if issue is not None:
            errors.append(issue)
        elif row is not None:
            good.append(row)
    seen: set[tuple[str, str, str]] = set()
    kept: list[ParamRow] = []
    for row in good:
        key = (row.scope, row.path, row.name)
        if key in seen:
            errors.append(
                _issue(
                    "duplicate",
                    row.row_number,
                    f"key {row.scope}|{row.path}|{row.name}",
                )
            )
            continue
        seen.add(key)
        kept.append(row)
    return kept, _sort_issues(errors)


def _interpret_record(record: _Record) -> tuple[ParamRow | None, ParamIssue | None]:
    if record.error_field:
        return None, _issue(record.error_field, record.line, record.error_detail)
    name = record.name.strip()
    if name == "":
        return None, _issue("name", record.line, "empty")
    if _NAME_RE.match(name) is None:
        return None, _issue("name", record.line, "not an identifier")

    scope = record.scope.strip().lower()
    if scope == "":
        scope = "base"
    if scope not in SCOPES:
        return None, _issue("scope", record.line, "unknown")
    path = record.path.strip()
    path_detail = _check_path(scope, path)
    if path_detail:
        return None, _issue("path", record.line, path_detail)

    raw_dtype = record.dtype.strip()
    explicit_dtype = raw_dtype != ""
    value_in = record.value.strip()
    dtype = raw_dtype.lower()
    if dtype == "":
        if value_in == "":
            return None, _issue("value", record.line, "empty")
        dtype = _infer_dtype(value_in)
    if dtype not in DTYPES:
        return None, _issue("dtype", record.line, "unknown")
    if value_in == "" and not (explicit_dtype and dtype == "string"):
        return None, _issue("value", record.line, "empty")

    typed, canonical, value_detail = _parse_value(dtype, value_in)
    if value_detail:
        return None, _issue("value", record.line, value_detail)

    unit = record.unit.strip()
    if not _is_unit(unit):
        return None, _issue("unit", record.line, "illegal")
    description = record.description.strip()
    if len(description) > 240:
        return None, _issue("description", record.line, "too long")
    if any(ord(char) < 32 for char in description):
        return None, _issue("description", record.line, "illegal character")
    group = record.group.strip()
    if group and _GROUP_RE.match(group) is None:
        return None, _issue("group", record.line, "illegal")

    minimum, minimum_detail = _parse_bound(record.minimum.strip())
    if minimum_detail:
        return None, _issue("minimum", record.line, minimum_detail)
    maximum, maximum_detail = _parse_bound(record.maximum.strip())
    if maximum_detail:
        return None, _issue("maximum", record.line, maximum_detail)
    if minimum is not None and maximum is not None and minimum > maximum:
        return None, _issue("minimum", record.line, "greater than maximum")
    if dtype not in {"double", "int"} and (minimum is not None or maximum is not None):
        field = "minimum" if minimum is not None else "maximum"
        return None, _issue(field, record.line, "not allowed for this dtype")
    if isinstance(typed, (int, float)) and not isinstance(typed, bool):
        number = float(typed)
        if minimum is not None and number < minimum:
            return None, _issue("minimum", record.line, "value is below minimum")
        if maximum is not None and number > maximum:
            return None, _issue("maximum", record.line, "value is above maximum")

    return (
        ParamRow(
            name=name,
            value=typed,
            value_text=canonical,
            unit=unit,
            description=description,
            scope=scope,
            path=path,
            dtype=dtype,
            minimum=minimum,
            maximum=maximum,
            group=group,
            row_number=record.line,
        ),
        None,
    )


def _parse_value(dtype: str, text: str) -> tuple[int | float | bool | str, str, str]:
    if dtype == "double":
        if _DOUBLE_RE.match(text) is None:
            return 0.0, "", "not a double"
        value = float(text)
        if not math.isfinite(value):
            return 0.0, "", "not finite"
        return value, format_double(value), ""
    if dtype == "int":
        if _INT_RE.match(text) is None:
            return 0, "", "not an int"
        number = int(text, 10)
        if abs(number) > INT_LIMIT:
            return 0, "", "out of int range"
        return number, str(number), ""
    if dtype == "logical":
        key = text.lower()
        if key in _LOGICAL_TRUE:
            return True, "true", ""
        if key in _LOGICAL_FALSE:
            return False, "false", ""
        return False, "", "not a logical"
    if len(text) > 240:
        return "", "", "too long"
    if any(ord(char) < 32 for char in text):
        return "", "", "illegal character"
    return text, text, ""


def _parse_bound(text: str) -> tuple[float | None, str]:
    if text == "":
        return None, ""
    if _DOUBLE_RE.match(text) is None:
        return None, "not a double"
    value = float(text)
    if not math.isfinite(value):
        return None, "not finite"
    return value, ""


def _check_path(scope: str, path: str) -> str:
    if scope == "base":
        if path != "":
            return "must be empty for base"
        return ""
    if scope in {"model", "workspace"}:
        if path == "":
            return "required"
        if _NAME_RE.match(path) is None:
            return "not a model name"
        return ""
    if "/" not in path:
        return "needs a slash"
    parts = path.split("/")
    if len(parts) < 2 or any(not _segment_ok(part) for part in parts):
        return "bad segment"
    return ""


def _segment_ok(part: str) -> bool:
    return part != "" and part == part.strip() and _SEGMENT_RE.match(part) is not None


def _infer_dtype(text: str) -> str:
    if text.lower() in _LOGICAL_WORDS:
        return "logical"
    if _INT_RE.match(text) is not None:
        return "int"
    if _DOUBLE_RE.match(text) is not None:
        return "double"
    return "string"


def _is_unit(text: str) -> bool:
    if text == "":
        return True
    if len(text) > 32:
        return False
    tokens: list[str] = []
    current: list[str] = []
    for char in text:
        if char in _SEPARATORS:
            if not current:
                return False
            tokens.append("".join(current))
            current = []
            continue
        current.append(char)
    if not current:
        return False
    tokens.append("".join(current))
    return all(_unit_token_ok(token, index == 0) for index, token in enumerate(tokens))


def _unit_token_ok(token: str, first: bool) -> bool:
    if first and token in {"1", "%"}:
        return True
    if token.isdigit():
        return not first
    first_char = token[0]
    if not _is_unit_letter(first_char):
        return False
    return all(_is_unit_body(char) for char in token[1:])


def _is_unit_letter(char: str) -> bool:
    return (char.isascii() and char.isalpha()) or char in _UNIT_EXTRAS


def _is_unit_body(char: str) -> bool:
    return (char.isascii() and char.isalnum()) or char in _UNIT_EXTRAS


def _assignments(
    rows: list[ParamRow],
) -> tuple[dict[str, dict[str, int | float | bool | str]], dict[str, int | float | bool | str]]:
    workspace: dict[str, dict[str, int | float | bool | str]] = {}
    base: dict[str, int | float | bool | str] = {}
    for row in rows:
        if row.scope == "workspace":
            workspace.setdefault(row.path, {})[row.name] = row.value
        elif row.scope == "base":
            base[row.name] = row.value
    return workspace, base


def _write_rows(path: Path, rows: list[ParamRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow(
                [
                    row.name,
                    row.value_text,
                    row.unit,
                    row.description,
                    row.scope,
                    row.path,
                    row.dtype,
                    "" if row.minimum is None else format_double(row.minimum),
                    "" if row.maximum is None else format_double(row.maximum),
                    row.group,
                ]
            )


def _issue(field: str, line: int, detail: str) -> ParamIssue:
    if line > 0:
        message = f"{field}: row {line} {detail}"
    else:
        message = f"{field}: {detail}"
    return ParamIssue(line, field, message)


def _sort_issues(issues: list[ParamIssue]) -> list[ParamIssue]:
    return sorted(
        issues,
        key=lambda item: (item.row_number, _FIELD_RANK.get(item.field, 99), item.message),
    )


def _same_row(left: ParamRow, right: ParamRow) -> bool:
    identity = (
        left.name,
        left.value_text,
        left.unit,
        left.description,
        left.scope,
        left.path,
        left.dtype,
        left.group,
        left.value,
    )
    other = (
        right.name,
        right.value_text,
        right.unit,
        right.description,
        right.scope,
        right.path,
        right.dtype,
        right.group,
        right.value,
    )
    return identity == other and _bound_equal(left.minimum, right.minimum) and _bound_equal(
        left.maximum, right.maximum
    )


def _bound_equal(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return left == right


def _norm_key(text: str) -> str:
    return re.sub(r"[\s_]+", "", text.strip().lower())
