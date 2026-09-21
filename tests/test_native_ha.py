"""Native HA validation tests (require installed homeassistant). Runs same checks as the lint script but as pytest."""
from __future__ import annotations

import pathlib
import unittest.mock as mock

import pytest


def test_native_blueprint_schema_and_templates():
    try:
        import homeassistant.util.yaml as hayaml
        from homeassistant.components.blueprint import BLUEPRINT_SCHEMA
        from homeassistant.helpers.template import Template
    except Exception as e:  # pragma: no cover
        pytest.skip(f"homeassistant not installed: {e}")

    path = pathlib.Path("motion-illuminance.yaml")
    data = hayaml.load_yaml(str(path))
    BLUEPRINT_SCHEMA(data)  # raises on invalid blueprint

    templates: list[str] = []
    for c in data.get("conditions") or []:
        if "value_template" in c:
            templates.append(c["value_template"])
    for a in data.get("actions") or []:
        if "value_template" in a:
            templates.append(a["value_template"])
        if "wait_template" in a:
            templates.append(a["wait_template"])
    assert templates, "expected templates in blueprint"
    import logging

    with mock.patch("homeassistant.helpers.frame.report"):
        with mock.patch.object(logging.Logger, "warning"):
            for src in templates:
                Template(src, None).ensure_valid()
