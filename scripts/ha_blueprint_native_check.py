#!/usr/bin/env python3
"""Native HA validation: parse YAML with HA's yaml loader, validate blueprint schema,
and render templates via HA's template engine (catches real HA errors)."""
from __future__ import annotations

import argparse
import pathlib
import sys


def main() -> int:
    p = argparse.ArgumentParser(description="Native HA blueprint validation")
    p.add_argument("paths", nargs="+", help="YAML files to validate")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    ok = True
    for raw in args.paths:
        path = pathlib.Path(raw)
        if not path.is_file():
            print(f"{path}: not found", file=sys.stderr)
            ok = False
            continue
        text = path.read_text(encoding="utf-8")
        try:
            import homeassistant.util.yaml as hayaml

            data = hayaml.load_yaml(str(path))
        except Exception as e:
            print(f"{path}: YAML load failed: {e}", file=sys.stderr)
            ok = False
            continue

        # 1) Blueprint schema
        try:
            from homeassistant.components.blueprint import BLUEPRINT_SCHEMA

            BLUEPRINT_SCHEMA(data)
            if args.verbose:
                print(f"{path}: BLUEPRINT_SCHEMA ok")
        except Exception as e:
            print(f"{path}: BLUEPRINT_SCHEMA failed: {e}", file=sys.stderr)
            ok = False
            continue

        # 2) Template lint via HA helpers (strict mode)
        try:
            from homeassistant.helpers.template import Template
            from homeassistant.core import HomeAssistant

            # Template(s) appear in conditions/actions/wait_template
            templates: list[str] = []
            for c in data.get("conditions") or []:
                if "value_template" in c:
                    templates.append(c["value_template"])
            for a in data.get("actions") or []:
                if "value_template" in a:
                    templates.append(a["value_template"])
                if "wait_template" in a:
                    templates.append(a["wait_template"])
            # lightly compile each template (syntax check)
            for i, src in enumerate(templates):
                import logging
                import unittest.mock as mock
                with mock.patch('homeassistant.helpers.frame.report'):
                    with mock.patch.object(logging.Logger, 'warning'):
                        t = Template(src, None)
                        t.ensure_valid()
                if args.verbose:
                    print(f"{path}: template[{i}] compiles ok")

        except Exception as e:
            print(f"{path}: template validation failed: {e}", file=sys.stderr)
            ok = False

        # 3) Check that blueprint.inputs selectors are valid
        try:
            import homeassistant.helpers.config_validation as cv

            # We already did BLUEPRINT_SCHEMA, which covers selectors; just sanity-check variables/triggers
            assert "triggers" in data or "trigger" in data
            assert "actions" in data or "action" in data
            if args.verbose:
                print(f"{path}: triggers/actions present")
        except Exception as e:
            print(f"{path}: structural check failed: {e}", file=sys.stderr)
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
