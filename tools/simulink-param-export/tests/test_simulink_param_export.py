"""Smoke tests for the simulink-param-export Python tool."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "python"))

from simulink_param_export import param_rows_equal, simulink_param_export

CSV = TOOL / "examples" / "data" / "dc_speed_params.csv"
INT_LIMIT = 2**53


def _by_name(result, name: str):
    hits = [row for row in result.rows if row.name == name]
    assert len(hits) == 1
    return hits[0]


def test_example_round_trip_assignments_and_schema(tmp_path: Path) -> None:
    out = tmp_path / "canonical.csv"
    result = simulink_param_export(CSV, output_csv=out, strict=True)
    again = simulink_param_export(out, strict=True)

    assert result.n_rows == 17
    assert result.n_errors == 0
    assert result.errors == []
    assert param_rows_equal(result.rows, again.rows)
    assert _by_name(result, "Kp").row_number == 4
    assert _by_name(result, "Kp").value == pytest.approx(1.8)
    assert _by_name(result, "Kp").minimum == 0.0
    assert _by_name(result, "Kp").maximum == 100.0
    assert _by_name(result, "Ts").value_text == "0.0001"
    assert _by_name(result, "Ts").minimum == pytest.approx(1e-6)
    assert _by_name(result, "Decimation").dtype == "int"
    assert type(_by_name(result, "Decimation").value) is int
    assert _by_name(result, "Decimation").value == 10
    gain = _by_name(result, "Gain")
    assert gain.scope == "block"
    assert gain.path == "dc_speed/Speed Ref"
    assert _by_name(result, "UseFilter").value is True
    assert _by_name(result, "UseFilter").value_text == "true"
    assert _by_name(result, "UseFilter").minimum is None
    assert _by_name(result, "J").value == pytest.approx(0.002)
    assert _by_name(result, "B").unit == "N.m/rad/s"
    note = _by_name(result, "Note")
    assert note.value == "class-demo"
    assert note.description == "Label, not a measurement"
    assert result.base["ModelName"] == "dc_speed"
    assert type(result.base["RatedRpm"]) is float
    assert result.base["RatedRpm"] == 1500
    assert set(result.workspace["dc_speed"]) == {
        "B",
        "FilterHz",
        "J",
        "Ke",
        "Ki",
        "Kp",
        "Kt",
        "L",
        "R",
    }
    assert "Ts" not in result.workspace["dc_speed"]
    assert "Gain" not in result.workspace["dc_speed"]
    assert result.assignment_text == (
        "workspace dc_speed: B=0.0002, FilterHz=50, J=0.002, Ke=0.4, "
        "Ki=12, Kp=1.8, Kt=0.4, L=0.005, R=0.8\n"
        "base: ModelName=dc_speed, Note=class-demo, RatedRpm=1500"
    )
    text = out.read_text(encoding="utf-8")
    assert text.startswith(
        "name,value,unit,description,scope,path,dtype,minimum,maximum,group\n"
    )
    assert "UseFilter,true," in text
    assert '"Label, not a measurement"' in text
    assert "参数名" not in text
    source = CSV.read_text(encoding="utf-8-sig").splitlines()
    assert source[0].startswith("#")
    assert source[2].split(";")[0] == "参数名"


def test_inference_quoting_and_helpers(tmp_path: Path) -> None:
    messy = tmp_path / "messy.csv"
    messy.write_bytes(
        "\ufeffname,value,dtype\n"
        "RatedRpm,1500,\n"
        "Enabled,yes,\n"
        "Note,hello,\n"
        "Gain,1.5,\n"
        'Slogan,"say ""hi""",string\n'.encode("utf-8")
    )
    out = tmp_path / "out.csv"
    result = simulink_param_export(messy, output_csv=out)
    assert [row.dtype for row in result.rows] == [
        "int",
        "logical",
        "string",
        "double",
        "string",
    ]
    assert [row.scope for row in result.rows] == ["base"] * 5
    assert result.rows[1].value is True
    assert result.rows[1].value_text == "true"
    assert result.rows[3].value == pytest.approx(1.5)
    assert result.rows[4].value == 'say "hi"'
    again = simulink_param_export(out)
    assert param_rows_equal(result.rows, again.rows)

    empty = tmp_path / "header.csv"
    empty.write_text("name,value\n", encoding="utf-8")
    blank = simulink_param_export(empty, output_csv=tmp_path / "blank.csv")
    assert blank.n_rows == 0
    assert blank.assignment_text == ""
    assert (tmp_path / "blank.csv").read_text(encoding="utf-8") == (
        "name,value,unit,description,scope,path,dtype,minimum,maximum,group\n"
    )

    written = simulink_param_export(
        [
            {
                "name": "Note",
                "value": "",
                "dtype": "string",
                "description": "a, b",
            }
        ],
        output_csv=tmp_path / "quote.csv",
    )
    assert written.rows[0].value == ""
    assert simulink_param_export(tmp_path / "quote.csv").rows[0].description == "a, b"


def test_validation_errors(tmp_path: Path) -> None:
    def row(**kwargs):
        base = {"name": "Kp", "value": 1.5, "dtype": "double", "scope": "base"}
        base.update(kwargs)
        return base

    with pytest.raises(ValueError, match="maximum"):
        simulink_param_export(
            [row(scope="workspace", path="dc_speed", value=5, minimum=0, maximum=1)]
        )
    with pytest.raises(ValueError, match="greater than maximum"):
        simulink_param_export([row(value=3, minimum=5, maximum=1)])
    with pytest.raises(ValueError, match="not allowed"):
        simulink_param_export(
            [{"name": "Note", "value": "x", "dtype": "string", "minimum": 0}]
        )
    with pytest.raises(ValueError, match="duplicate"):
        simulink_param_export(
            [
                row(name="Kp", scope="workspace", path="dc_speed"),
                row(name="Kp", scope="workspace", path="dc_speed", value=2),
            ]
        )
    with pytest.raises(ValueError, match="needs a slash"):
        simulink_param_export([row(name="Gain", scope="block", path="Gain")])
    with pytest.raises(ValueError, match="must be empty"):
        simulink_param_export([row(scope="base", path="dc_speed")])
    with pytest.raises(ValueError, match="not an int"):
        simulink_param_export([row(name="N", value="2.5", dtype="int")])
    with pytest.raises(ValueError, match="out of int range"):
        simulink_param_export(
            [row(name="N", value=str(INT_LIMIT + 1), dtype="int")]
        )
    with pytest.raises(ValueError, match="scope"):
        simulink_param_export([row(scope="dialog")])
    with pytest.raises(ValueError, match="unit"):
        simulink_param_export([row(unit="ohm meter")])
    with pytest.raises(ValueError, match="not a logical"):
        simulink_param_export([row(name="Flag", value="maybe", dtype="logical")])
    with pytest.raises(ValueError, match="empty"):
        simulink_param_export([row(value="", dtype="double")])

    out = tmp_path / "skipped.csv"
    with pytest.raises(ValueError, match="maximum"):
        simulink_param_export([row(value=9, maximum=1)], output_csv=out)
    assert not out.exists()

    kept = simulink_param_export(
        [row(name="A", value=1), row(name="B", value=5, maximum=1)],
        strict=False,
        output_csv=tmp_path / "partial.csv",
    )
    assert kept.n_rows == 1
    assert kept.n_errors == 1
    assert kept.rows[0].name == "A"
    assert "B" not in (tmp_path / "partial.csv").read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="not both"):
        simulink_param_export(CSV, csv_path=CSV)
    with pytest.raises(ValueError, match="source: required"):
        simulink_param_export()
    with pytest.raises(FileNotFoundError):
        simulink_param_export(tmp_path / "missing.csv")
    with pytest.raises(ValueError, match="missing value column"):
        bad = tmp_path / "bad.csv"
        bad.write_text("name,unit\nKp,1\n", encoding="utf-8")
        simulink_param_export(bad)


def test_matlab_alias_codepoints_are_ascii() -> None:
    source = (TOOL / "matlab" / "simulink_param_export.m").read_text(encoding="utf-8")
    assert source.isascii()
    literals = {
        "参数名": "char([21442 25968 21517])",
        "参数": "char([21442 25968])",
        "值": "char(20540)",
        "数值": "char([25968 20540])",
        "单位": "char([21333 20301])",
        "说明": "char([35828 26126])",
        "描述": "char([25551 36848])",
        "作用域": "char([20316 29992 22495])",
        "路径": "char([36335 24452])",
        "类型": "char([31867 22411])",
        "下限": "char([19979 38480])",
        "上限": "char([19978 38480])",
        "分组": "char([20998 32452])",
        "类别": "char([31867 21035])",
    }
    for word, literal in literals.items():
        assert literal in source
        assert [ord(char) for char in word] == [
            int(part) for part in literal.split("[")[-1].split("]")[0].split()
        ] if "[" in literal else [int(literal.removeprefix("char(").removesuffix(")"))]


def test_run_demo_script() -> None:
    script = TOOL / "examples" / "run_demo.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "rows=17 errors=0" in completed.stdout
    assert "round-trip ok: 17 rows" in completed.stdout
    assert "Kp=1.8" in completed.stdout
    assert "workspace dc_speed:" in completed.stdout
    out = TOOL / "examples" / "output" / "simulink_param_export_demo.csv"
    assert out.is_file()
    assert "UseFilter,true," in out.read_text(encoding="utf-8")
