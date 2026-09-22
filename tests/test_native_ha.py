"""Native HA validation tests (require installed homeassistant). Runs same checks as the lint script but as pytest."""
from __future__ import annotations

import pathlib
import unittest.mock as mock

import pytest


BLUEPRINT_PATHS = [
    "blueprints/motion-illuminance.yaml",
    "blueprints/button-sonoff-znzb-01p.yml",
]


def _collect_templates(data: dict) -> list[str]:
    out: list[str] = []
    for c in data.get("conditions") or []:
        if isinstance(c, dict) and "value_template" in c:
            out.append(c["value_template"])
    for a in data.get("actions") or []:
        if not isinstance(a, dict):
            continue
        if "value_template" in a:
            out.append(a["value_template"])
        if "wait_template" in a:
            out.append(a["wait_template"])
        # choose is list-like (NodeListClass) for HA yaml; iterate directly
        choose_val = a.get("choose")
        if isinstance(choose_val, list):
            entries = choose_val
        elif isinstance(choose_val, dict) and "choose" in choose_val:
            entries = choose_val.get("choose", []) or []
        else:
            entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for cond in entry.get("conditions") or []:
                if isinstance(cond, dict) and "value_template" in cond:
                    out.append(cond["value_template"])
        vars_val = a.get("variables")
        if isinstance(vars_val, dict):
            for v in vars_val.values():
                if isinstance(v, str) and "{{" in v:
                    out.append(v)
    vars_top = data.get("variables")
    if isinstance(vars_top, dict):
        for v in vars_top.values():
            if isinstance(v, str) and "{{" in v:
                out.append(v)
    return out


@pytest.mark.parametrize("path", BLUEPRINT_PATHS)
def test_native_blueprint_schema_and_templates(path):
    try:
        import homeassistant.util.yaml as hayaml
        from homeassistant.components.blueprint import BLUEPRINT_SCHEMA
        from homeassistant.helpers.template import Template
    except Exception as e:  # pragma: no cover
        pytest.skip(f"homeassistant not installed: {e}")

    p = pathlib.Path(path)
    data = hayaml.load_yaml(str(p))
    BLUEPRINT_SCHEMA(data)  # raises on invalid blueprint

    templates = _collect_templates(data)
    import logging

    with mock.patch("homeassistant.helpers.frame.report"):
        with mock.patch.object(logging.Logger, "warning"):
            for src in templates:
                Template(src, None).ensure_valid()
    # motion-illuminance has many templates; button blueprint may have none outside actions/variables
    # still assert schema passed; templates check is opportunistic
    assert True
