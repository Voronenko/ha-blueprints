from __future__ import annotations

import pathlib

import pytest

from tests.helpers import InputTag, dispatch_button, load_blueprint

BP_PATH = "blueprints/button-sonoff-znzb-01p.yml"


@pytest.fixture(scope="module")
def bp():
    data, text = load_blueprint(BP_PATH)
    return data, text


@pytest.fixture(scope="module")
def data(bp):
    return bp[0]


@pytest.fixture(scope="module")
def text(bp):
    return bp[1]


def test_blueprint_has_expected_inputs(data):
    inputs = data["blueprint"]["input"]
    assert "remote" in inputs
    sel = inputs["remote"]["selector"]["device"]
    assert sel["integration"] == "zha"
    assert sel["manufacturer"] == "eWeLink"
    assert sel["model"] == "SNZB-01P"
    assert sel["multiple"] is False
    assert inputs["single_press"]["selector"] == {"action": {}}
    assert inputs["double_press"]["selector"] == {"action": {}}
    assert inputs["hold"]["selector"] == {"action": {}}
    assert inputs["single_press"]["default"] == []
    assert data["blueprint"]["domain"] == "automation"
    assert data["blueprint"]["homeassistant"]["min_version"] == "2025.1.0"
    assert "author" in data["blueprint"] and "source_url" in data["blueprint"]


def test_triggers_zha_event_scoped_to_device(data):
    assert "triggers" in data and "trigger" not in data
    assert "actions" in data and "action" not in data
    trig = data["triggers"][0]
    assert trig["trigger"] == "event"
    assert trig["event_type"] == "zha_event"
    dev = trig["event_data"]["device_id"]
    assert isinstance(dev, InputTag)
    assert str(dev) == "remote"
    assert data.get("variables", {}).get("remote_device_id") is not None
    assert str(data["variables"]["remote_device_id"]) == "remote"


def test_mode_restart(data):
    assert data["mode"] == "restart"
    assert data["max_exceeded"] == "silent"


def test_single_press_routed_on_toggle(data):
    assert dispatch_button(data, command="toggle", cluster_id=6, endpoint_id=1) == "single_press"


def test_double_press_routed_on_on(data):
    assert dispatch_button(data, command="on", cluster_id=6, endpoint_id=1) == "double_press"


def test_hold_routed_on_off(data):
    assert dispatch_button(data, command="off", cluster_id=6, endpoint_id=1) == "hold"


def test_cluster_endpoint_guard_blocks(data):
    # Wrong cluster or endpoint -> no dispatch even if command matches
    assert dispatch_button(data, command="toggle", cluster_id=5, endpoint_id=1) is None
    assert dispatch_button(data, command="toggle", cluster_id=6, endpoint_id=2) is None
    assert dispatch_button(data, command="on", cluster_id=6, endpoint_id=2) is None
    assert dispatch_button(data, command="off", cluster_id=7, endpoint_id=1) is None


def test_unknown_command_falls_through(data):
    assert dispatch_button(data, command="press", cluster_id=6, endpoint_id=1) is None
    assert dispatch_button(data, command="", cluster_id=6, endpoint_id=1) is None


def test_choose_branches_use_template_conditions(data):
    actions = data.get("actions") or []
    choose = next(a for a in actions if "choose" in a)
    for entry in choose["choose"]:
        for cond in entry["conditions"]:
            assert isinstance(cond, dict)
            assert cond.get("condition") == "template"
            assert "value_template" in cond
            vt = cond["value_template"]
            assert "{{" in vt and "}}" in vt


def test_no_raw_template_strings_in_conditions(data):
    # Upgraded from legacy list ['{{ command == "toggle" }}', ...] to condition: template entries
    actions = data.get("actions") or []
    choose = next(a for a in actions if "choose" in a)
    for entry in choose["choose"]:
        # No raw '{{ ... }}' strings — every condition must be a dict with condition: template
        assert not any(isinstance(c, str) for c in entry.get("conditions") or [])
