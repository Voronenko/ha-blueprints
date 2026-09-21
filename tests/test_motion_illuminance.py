from __future__ import annotations

import datetime as dt
import pathlib

import pytest

from tests.helpers import extract_after_condition_template, extract_wait_template, load_blueprint, render_template

# Fixed fake sun for deterministic tests (Europe/Kyiv-like wall clock)
# We use naive UTC+ offsets via tzinfo=timezone.utc then wall times; simpler: fixed aware UTC
TZ = dt.timezone.utc
# Choose a date where sunrise 06:00 and sunset 18:00 UTC for easy reasoning
SUNRISE = dt.datetime(2026, 3, 20, 6, 0, tzinfo=TZ)
SUNSET = dt.datetime(2026, 3, 20, 18, 0, tzinfo=TZ)


def make_next(sunrise: dt.datetime, sunset: dt.datetime, now_dt: dt.datetime):
    # Emulate HA sun.sun next_rising/next_setting relative to now
    # Simplest: return next event strictly after now - but blueprint handles +/-12h anyway
    if now_dt < sunrise:
        return sunrise, sunset if sunset > now_dt else sunset + dt.timedelta(days=1)
    if now_dt < sunset:
        # next_rising is tomorrow, next_setting today
        return sunrise + dt.timedelta(days=1), sunset
    return sunrise + dt.timedelta(days=1), sunset + dt.timedelta(days=1)


@pytest.fixture(scope="module")
def bp():
    data, text = load_blueprint()
    # keep raw for debug
    return data


@pytest.fixture(scope="module")
def main_template(bp):
    # first (and only) condition
    conds = bp.get("conditions") or []
    assert conds, "no conditions"
    return conds[0]["value_template"]


@pytest.fixture(scope="module")
def wait_template(bp):
    t = extract_wait_template(bp)
    assert t, "no wait_template"
    return t


@pytest.fixture(scope="module")
def turn_off_condition(bp):
    t = extract_after_condition_template(bp)
    assert t, "no turn_off condition"
    return t


def _vars(**overrides):
    base = dict(
        illuminance_entities_raw=[],
        lux_level_var=100,
        illuminance_mode_var="any",
        all_day_var=False,
        hours_after_sunrise_var=2,
        hours_before_sunset_var=2,
    )
    base.update(overrides)
    return base


def test_blueprint_has_expected_inputs(bp):
    inputs = bp["blueprint"]["input"]
    assert "devices" in inputs
    assert "motion_entity" in inputs["devices"]["input"]
    assert "motion_entities" in inputs["devices"]["input"]
    assert "light_target" in inputs["devices"]["input"]
    assert "all_day" in inputs["time_window"]["input"]
    assert inputs["time_window"]["input"]["all_day"]["default"] is False
    assert "hours_after_sunrise" in inputs["time_window"]["input"]
    assert "hours_before_sunset" in inputs["time_window"]["input"]
    assert inputs["time_window"]["input"]["hours_after_sunrise"]["default"] == 2
    assert inputs["time_window"]["input"]["hours_before_sunset"]["default"] == 2
    # illuminance defaults to any (override)
    assert inputs["illuminance"]["input"]["illuminance_mode"]["default"] == "any"
    assert "lux_entity" not in inputs.get("illuminance", {}).get("input", {})


def test_illuminance_any_below_overrides_night(main_template):
    # Daytime (12:00) but dark -> should allow
    now_dt = dt.datetime(2026, 3, 20, 12, 0, tzinfo=TZ)
    nxt_r, nxt_s = make_next(SUNRISE, SUNSET, now_dt)
    ok = render_template(
        main_template,
        now_dt=now_dt,
        next_rising=nxt_r,
        next_setting=nxt_s,
        states={"sensor.lux1": "5", "sensor.lux2": "900"},
        variables=_vars(illuminance_entities_raw=["sensor.lux1", "sensor.lux2"]),
    )
    assert ok is True


def test_illuminance_any_all_bright_blocks_day(main_template):
    now_dt = dt.datetime(2026, 3, 20, 12, 0, tzinfo=TZ)
    nxt_r, nxt_s = make_next(SUNRISE, SUNSET, now_dt)
    ok = render_template(
        main_template,
        now_dt=now_dt,
        next_rising=nxt_r,
        next_setting=nxt_s,
        states={"sensor.lux1": "500", "sensor.lux2": "600"},
        variables=_vars(illuminance_entities_raw=["sensor.lux1", "sensor.lux2"]),
    )
    assert ok is False


def test_illuminance_all_mode_requires_all_dark(main_template):
    now_dt = dt.datetime(2026, 3, 20, 12, 0, tzinfo=TZ)
    nxt_r, nxt_s = make_next(SUNRISE, SUNSET, now_dt)
    # one dark, one bright -> should NOT pass when mode=all
    ok = render_template(
        main_template,
        now_dt=now_dt,
        next_rising=nxt_r,
        next_setting=nxt_s,
        states={"sensor.lux1": "5", "sensor.lux2": "500"},
        variables=_vars(illuminance_entities_raw=["sensor.lux1", "sensor.lux2"], illuminance_mode_var="all"),
    )
    assert ok is False
    # both dark -> pass even at noon
    ok2 = render_template(
        main_template,
        now_dt=now_dt,
        next_rising=nxt_r,
        next_setting=nxt_s,
        states={"sensor.lux1": "5", "sensor.lux2": "50"},
        variables=_vars(illuminance_entities_raw=["sensor.lux1", "sensor.lux2"], illuminance_mode_var="all"),
    )
    assert ok2 is True


def test_no_illuminance_sensors_uses_time_window_day_vs_night(main_template):
    # noon inside 06-18 day -> outside window [16:00, 08:00] ? window is sunset-2=16:00 .. sunrise+2=08:00 => wraps overnight. Noon not in window
    noon = dt.datetime(2026, 3, 20, 12, 0, tzinfo=TZ)
    nxt_r, nxt_s = make_next(SUNRISE, SUNSET, noon)
    ok_day = render_template(
        main_template,
        now_dt=noon,
        next_rising=nxt_r,
        next_setting=nxt_s,
        states={},
        variables=_vars(),
    )
    assert ok_day is False

    night = dt.datetime(2026, 3, 20, 22, 0, tzinfo=TZ)
    nxt_r2, nxt_s2 = make_next(SUNRISE, SUNSET, night)
    ok_night = render_template(
        main_template,
        now_dt=night,
        next_rising=nxt_r2,
        next_setting=nxt_s2,
        states={},
        variables=_vars(),
    )
    assert ok_night is True

    early = dt.datetime(2026, 3, 20, 7, 0, tzinfo=TZ)  # within sunrise+2
    nxt_r3, nxt_s3 = make_next(SUNRISE, SUNSET, early)
    ok_early = render_template(
        main_template,
        now_dt=early,
        next_rising=nxt_r3,
        next_setting=nxt_s3,
        states={},
        variables=_vars(),
    )
    assert ok_early is True


def test_0_sensors_or_unavailable_counts_as_no_dark(main_template):
    now_dt = dt.datetime(2026, 3, 20, 12, 0, tzinfo=TZ)
    nxt_r, nxt_s = make_next(SUNRISE, SUNSET, now_dt)
    # unavailable should not count as dark
    ok = render_template(
        main_template,
        now_dt=now_dt,
        next_rising=nxt_r,
        next_setting=nxt_s,
        states={"sensor.lux1": "unavailable"},
        variables=_vars(illuminance_entities_raw=["sensor.lux1"]),
    )
    assert ok is False


def test_defaults_2h_each_match_description(main_template):
    # From description: window active sunset-2 .. sunrise+2 ; test boundaries
    # 15:59 just before 16:00 -> not in window, 16:00 in, 07:59 in, 08:00 not
    for h, expected in [(15, False), (16, True), (7, True), (8, False)]:
        now_dt = dt.datetime(2026, 3, 20, h, 0, tzinfo=TZ)
        nxt_r, nxt_s = make_next(SUNRISE, SUNSET, now_dt)
        ok = render_template(
            main_template,
            now_dt=now_dt,
            next_rising=nxt_r,
            next_setting=nxt_s,
            states={},
            variables=_vars(),
        )
        assert ok is expected, f"hour {h}: got {ok} expected {expected}"


def test_all_day_covers_full_day(main_template):
    # When all_day=true, time window is ignored -> even bright sensors at noon pass
    for h in [0, 12, 15, 22]:
        now_dt = dt.datetime(2026, 3, 20, h, 0, tzinfo=TZ)
        nxt_r, nxt_s = make_next(SUNRISE, SUNSET, now_dt)
        ok = render_template(
            main_template,
            now_dt=now_dt,
            next_rising=nxt_r,
            next_setting=nxt_s,
            states={"sensor.lux1": "500"},
            variables=_vars(illuminance_entities_raw=["sensor.lux1"], all_day_var=True),
        )
        assert ok is True, f"hour {h} should pass with all_day=True (got {ok})"
    # and also with no sensors
    noon = dt.datetime(2026, 3, 20, 12, 0, tzinfo=TZ)
    nxt_r, nxt_s = make_next(SUNRISE, SUNSET, noon)
    assert render_template(main_template, now_dt=noon, next_rising=nxt_r, next_setting=nxt_s, states={}, variables=_vars(all_day_var=True)) is True


def test_all_day_false_still_respects_window(main_template):
    # sanity: all_day=False must still block bright noon
    noon = dt.datetime(2026, 3, 20, 12, 0, tzinfo=TZ)
    nxt_r, nxt_s = make_next(SUNRISE, SUNSET, noon)
    ok = render_template(
        main_template, now_dt=noon, next_rising=nxt_r, next_setting=nxt_s, states={"sensor.lux1": "500"}, variables=_vars(illuminance_entities_raw=["sensor.lux1"], all_day_var=False)
    )
    assert ok is False


def test_motion_wait_and_turn_off_requires_all_off(wait_template, turn_off_condition):
    # Same logic for both templates: true only if all motions are off
    for tmpl in (wait_template, turn_off_condition):
        assert render_template(tmpl, now_dt=SUNRISE, next_rising=None, next_setting=None, states={"binary_sensor.m1": "off", "binary_sensor.m2": "off"}, variables={"motion_entities_raw": ["binary_sensor.m1", "binary_sensor.m2"], "legacy_motion_entity": None}) is True
        assert render_template(tmpl, now_dt=SUNRISE, next_rising=None, next_setting=None, states={"binary_sensor.m1": "on", "binary_sensor.m2": "off"}, variables={"motion_entities_raw": ["binary_sensor.m1", "binary_sensor.m2"], "legacy_motion_entity": None}) is False
        # legacy fallback
        assert render_template(tmpl, now_dt=SUNRISE, next_rising=None, next_setting=None, states={"binary_sensor.m1": "off"}, variables={"motion_entities_raw": [], "legacy_motion_entity": "binary_sensor.m1"}) is True


def test_legacy_motion_single_sensor_triggers(wait_template):
    # legacy single sensor, off -> true, on -> false
    assert render_template(wait_template, now_dt=SUNRISE, next_rising=None, next_setting=None, states={"binary_sensor.m1": "off"}, variables={"motion_entities_raw": [], "legacy_motion_entity": "binary_sensor.m1"}) is True
    assert render_template(wait_template, now_dt=SUNRISE, next_rising=None, next_setting=None, states={"binary_sensor.m1": "on"}, variables={"motion_entities_raw": [], "legacy_motion_entity": "binary_sensor.m1"}) is False
