from __future__ import annotations

from dataclasses import dataclass

from mcp_strava.types import dc_to_dict, smart_round


def test_smart_round_zero() -> None:
    assert smart_round(0.0) == 0
    assert smart_round(0) == 0


def test_smart_round_large_magnitude() -> None:
    assert smart_round(42.7) == 43
    assert smart_round(10.0) == 10
    assert smart_round(99.99) == 100
    assert smart_round(-42.7) == -43


def test_smart_round_medium_magnitude() -> None:
    assert smart_round(5.5) == 5.5
    assert smart_round(1.0) == 1.0
    assert smart_round(9.99) == 10.0
    assert smart_round(-1.23) == -1.2


def test_smart_round_small_magnitude() -> None:
    assert smart_round(0.5) == 0.5
    assert smart_round(0.12345) == 0.12
    assert smart_round(0.1) == 0.1
    assert smart_round(-0.12345) == -0.12


def test_smart_round_tiny_magnitude() -> None:
    assert smart_round(0.05) == 0.05
    assert smart_round(0.012345) == 0.012
    assert smart_round(0.01) == 0.01
    assert smart_round(-0.012345) == -0.012


def test_smart_round_very_tiny_magnitude() -> None:
    assert smart_round(0.005) == 0.005
    assert smart_round(0.0012345) == 0.0012
    assert smart_round(-0.0012345) == -0.0012


def test_smart_round_boundary_at_ten() -> None:
    assert isinstance(smart_round(10.0), int)
    assert isinstance(smart_round(9.999999), float)


def test_smart_round_boundary_at_one() -> None:
    assert smart_round(1.0) == 1.0
    assert smart_round(0.999999) == 1.0


def test_dc_to_dict_simple() -> None:
    @dataclass
    class Point:
        x: int
        y: int

    result = dc_to_dict(Point(1, 2))
    assert result == {"x": 1, "y": 2}


def test_dc_to_dict_nested() -> None:
    @dataclass
    class Inner:
        value: str

    @dataclass
    class Outer:
        inner: Inner
        label: str

    result = dc_to_dict(Outer(Inner("data"), "test"))
    assert result == {"inner": {"value": "data"}, "label": "test"}


def test_dc_to_dict_list_of_dataclasses() -> None:
    @dataclass
    class Item:
        id: int

    result = dc_to_dict([Item(1), Item(2)])
    assert result == [{"id": 1}, {"id": 2}]


def test_dc_to_dict_dict_of_dataclasses() -> None:
    @dataclass
    class Value:
        n: int

    result = dc_to_dict({"a": Value(1), "b": Value(2)})
    assert result == {"a": {"n": 1}, "b": {"n": 2}}


def test_dc_to_dict_excludes_raw_field() -> None:
    @dataclass
    class WithRaw:
        name: str
        _raw: dict | None = None

    result = dc_to_dict(WithRaw("test", {"api": "data"}))
    assert result == {"name": "test"}
    assert "_raw" not in result


def test_dc_to_dict_primitives_pass_through() -> None:
    assert dc_to_dict(42) == 42
    assert dc_to_dict("hello") == "hello"
    assert dc_to_dict(None) is None
    assert dc_to_dict(True) is True


def test_dc_to_dict_round_floats_default() -> None:
    @dataclass
    class Metric:
        value: float

    result = dc_to_dict(Metric(3.14159265), round_floats=False)
    assert result["value"] == 3.14159265


def test_dc_to_dict_round_floats_enabled() -> None:
    @dataclass
    class Metric:
        value: float

    result = dc_to_dict(Metric(3.14159265), round_floats=True)
    assert result["value"] == 3.1


def test_dc_to_dict_round_floats_list() -> None:
    @dataclass
    class Metric:
        values: list[float]

    result = dc_to_dict(Metric([42.76, 0.123, 0.0012]), round_floats=True)
    assert result["values"] == [43, 0.12, 0.0012]


def test_dc_to_dict_round_floats_nested() -> None:
    @dataclass
    class Inner:
        score: float

    @dataclass
    class Outer:
        inner: Inner
        raw_value: float

    result = dc_to_dict(Outer(Inner(0.5678), 42.7), round_floats=True)
    assert result == {"inner": {"score": 0.57}, "raw_value": 43}
