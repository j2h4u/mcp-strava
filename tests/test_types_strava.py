"""Тесты парсинга сырых ответов Strava API в типизированные датаклассы.

Проверяет функции parse_strava_streams, parse_strava_stream_channels
и parse_strava_athlete — все являются чистыми и детерминированными.
"""

from mcp_strava.types_strava import (
    StravaStreamChannel,
    StravaStreams,
    parse_strava_athlete,
    parse_strava_stream_channels,
    parse_strava_streams,
)


def _make_stream_channel(data=None, original_size=None, resolution=None, series_type=None):
    return {"data": data or [], "original_size": original_size, "resolution": resolution, "series_type": series_type}


def test_parse_strava_streams_all_channels():
    """parse_strava_streams: все 10 каналов парсятся корректно."""
    raw = {
        "time": _make_stream_channel([0, 60, 120, 180, 240], original_size=5, resolution="low", series_type="time"),
        "heartrate": _make_stream_channel([72, 140, 155, 160, 152], original_size=5),
        "velocity_smooth": _make_stream_channel([0.0, 3.1, 3.5, 3.3, 2.9], original_size=5),
        "altitude": _make_stream_channel([100.0, 101.0, 103.0, 106.0, 110.0], original_size=5),
        "cadence": _make_stream_channel([0, 85, 88, 86, 84], original_size=5),
        "latlng": _make_stream_channel([[43.0, 76.0], [43.1, 76.1], [43.2, 76.2]], original_size=3),
        "grade_smooth": _make_stream_channel([0.5, 1.0, 1.5, 2.0, 2.5], original_size=5),
        "moving": _make_stream_channel([False, True, True, True, True], original_size=5),
        "grade_adjusted_speed": _make_stream_channel([0.0, 3.0, 3.4, 3.2, 2.8], original_size=5),
        "grade_adjusted_distance": _make_stream_channel([0.0, 51.7, 110.1, 165.0, 213.5], original_size=5),
    }

    result = parse_strava_streams(raw)
    assert isinstance(result, StravaStreams)
    assert isinstance(result.time, StravaStreamChannel)
    assert result.time.data == [0, 60, 120, 180, 240]
    assert result.time.resolution == "low"
    assert result.time.series_type == "time"
    assert result.heartrate is not None
    assert result.heartrate.data == [72, 140, 155, 160, 152]
    assert result.velocity_smooth is not None
    assert result.velocity_smooth.data == [0.0, 3.1, 3.5, 3.3, 2.9]
    assert result.altitude is not None
    assert result.altitude.data == [100.0, 101.0, 103.0, 106.0, 110.0]
    assert result.cadence is not None
    assert result.cadence.data == [0, 85, 88, 86, 84]
    assert result.latlng is not None
    assert result.latlng.data == [[43.0, 76.0], [43.1, 76.1], [43.2, 76.2]]
    assert result.grade_smooth is not None
    assert result.grade_smooth.data == [0.5, 1.0, 1.5, 2.0, 2.5]
    assert result.moving is not None
    assert result.moving.data == [False, True, True, True, True]
    assert result.grade_adjusted_speed is not None
    assert result.grade_adjusted_speed.data == [0.0, 3.0, 3.4, 3.2, 2.8]
    assert result.grade_adjusted_distance is not None
    assert result.grade_adjusted_distance.data == [0.0, 51.7, 110.1, 165.0, 213.5]


def test_parse_strava_streams_missing_optional_channels():
    """parse_strava_streams: отсутствующие опциональные каналы — None."""
    raw = {
        "time": _make_stream_channel([0, 60, 120], original_size=3),
    }
    result = parse_strava_streams(raw)
    assert isinstance(result, StravaStreams)
    assert result.time.data == [0, 60, 120]
    assert result.heartrate is None
    assert result.velocity_smooth is None
    assert result.altitude is None
    assert result.cadence is None
    assert result.latlng is None
    assert result.grade_smooth is None
    assert result.moving is None
    assert result.grade_adjusted_speed is None
    assert result.grade_adjusted_distance is None


def test_parse_strava_stream_channels_normal():
    """parse_strava_stream_channels: валидные каналы парсятся корректно."""
    raw = {
        "time": _make_stream_channel([1, 2, 3], original_size=3),
        "heartrate": _make_stream_channel([140, 150, 160], original_size=3),
        "velocity_smooth": _make_stream_channel([2.5, 3.0, 3.5], original_size=3),
    }
    result = parse_strava_stream_channels(raw)
    assert len(result) == 3
    assert "time" in result
    assert result["time"].data == [1, 2, 3]
    assert "heartrate" in result
    assert result["heartrate"].data == [140, 150, 160]
    assert "velocity_smooth" in result
    assert result["velocity_smooth"].data == [2.5, 3.0, 3.5]


def test_parse_strava_stream_channels_skips_non_dict_entries():
    """parse_strava_stream_channels: не-словарь пропускается."""
    raw: dict[str, object] = {
        "time": _make_stream_channel([1, 2], original_size=2),
        "garbage": "not-a-dict",
        "heartrate": _make_stream_channel([140, 150], original_size=2),
    }
    result = parse_strava_stream_channels(raw)
    assert len(result) == 2
    assert "time" in result
    assert "heartrate" in result
    assert "garbage" not in result


def test_parse_strava_stream_channels_skips_non_list_data():
    """parse_strava_stream_channels: data не-список — пропускается."""
    raw: dict[str, object] = {
        "time": _make_stream_channel([1, 2], original_size=2),
        "broken": {"data": "not-a-list-string", "original_size": 5},
        "heartrate": _make_stream_channel([140, 150], original_size=2),
    }
    result = parse_strava_stream_channels(raw)
    assert len(result) == 2
    assert "time" in result
    assert "heartrate" in result
    assert "broken" not in result


def test_parse_strava_stream_channels_empty():
    """parse_strava_stream_channels: пустой вход — пустой результат."""
    assert parse_strava_stream_channels({}) == {}


def test_parse_strava_athlete_minimal():
    """parse_strava_athlete: минимальные данные атлета без обуви."""
    raw = {"id": 12345}
    result = parse_strava_athlete(raw)
    assert result.id == 12345
    assert result.shoes == []


def test_parse_strava_athlete_with_shoes():
    """parse_strava_athlete: данные атлета с одной парой кроссовок."""
    raw = {
        "id": 12345,
        "shoes": [
            {
                "id": 99,
                "name": "Nike Pegasus",
                "distance": 250000.0,
                "primary": True,
            }
        ],
    }
    result = parse_strava_athlete(raw)
    assert result.id == 12345
    assert len(result.shoes) == 1
    shoe = result.shoes[0]
    assert shoe.id == 99
    assert shoe.name == "Nike Pegasus"
    assert shoe.distance == 250000.0
    assert shoe.primary is True


def test_parse_strava_athlete_with_multiple_shoes():
    """parse_strava_athlete: несколько пар кроссовок, одна основная."""
    raw = {
        "id": 999,
        "shoes": [
            {"id": 1, "name": "Race Flat", "distance": 50000.0, "primary": False},
            {"id": 2, "name": "Daily Trainer", "distance": 400000.0, "primary": True},
            {"id": 3, "name": "Trail Shoe", "distance": 100000.0, "primary": False},
        ],
    }
    result = parse_strava_athlete(raw)
    assert len(result.shoes) == 3
    assert result.shoes[0].name == "Race Flat"
    assert result.shoes[1].name == "Daily Trainer"
    assert result.shoes[1].primary is True
    assert result.shoes[2].name == "Trail Shoe"


def test_parse_strava_athlete_shoe_defaults():
    """parse_strava_athlete: shoe без name/distance/primary получает значения по умолчанию."""
    raw = {
        "id": 1,
        "shoes": [
            {"id": 42},
        ],
    }
    result = parse_strava_athlete(raw)
    shoe = result.shoes[0]
    assert shoe.id == 42
    assert shoe.name == ""
    assert shoe.distance == 0
    assert shoe.primary is False
