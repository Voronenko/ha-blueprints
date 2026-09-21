#!/usr/bin/env python3
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from dataclasses import dataclass

import yaml


@dataclass
class Issue:
    level: str  # error | warning
    code: str
    message: str
    line: int | None = None
    col: int | None = None

    def format(self, path: pathlib.Path) -> str:
        loc = f"{path}:{self.line}:{self.col}" if self.line else str(path)
        return f"{loc}: [{self.level}] [{self.code}] {self.message}"


class InputTag(str):
    pass


def input_constructor(loader, node):
    if isinstance(node, yaml.ScalarNode):
        return InputTag(loader.construct_scalar(node))
    if isinstance(node, yaml.SequenceNode):
        return [InputTag(v) if isinstance(v, str) else v for v in loader.construct_sequence(node)]
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return InputTag(loader.construct_scalar(node))


yaml.SafeLoader.add_constructor("!input", input_constructor)


def find_inputs(node, out: set[str]):
    if isinstance(node, InputTag):
        out.add(str(node))
    elif isinstance(node, dict):
        for v in node.values():
            find_inputs(v, out)
    elif isinstance(node, list):
        for v in node:
            find_inputs(v, out)


def check_jinja_input(text: str) -> list[Issue]:
    issues: list[Issue] = []
    for i, ln in enumerate(text.splitlines(), 1):
        if "{{" in ln and "!input" in ln:
            issues.append(Issue("warning", "BP012", "!input inside Jinja {{ }} is invalid; bind via variables: first", i, ln.find("!input") + 1))
            break
        if "{%" in ln and "!input" in ln:
            issues.append(Issue("warning", "BP012", "!input inside Jinja {% %} is invalid; bind via variables: first", i, ln.find("!input") + 1))
            break
    return issues


def check_quoted_input(text: str) -> list[Issue]:
    issues: list[Issue] = []
    for i, ln in enumerate(text.splitlines(), 1):
        for m in re.finditer(r"!input\s+'[^']+'", ln):
            issues.append(Issue("warning", "BP011", "!input uses quoted name (!input 'x'); prefer !input x (HA guide style)", i, m.start() + 1))
            break
    return issues


def walk_raw_text_issues(text: str, data: dict) -> list[Issue]:
    issues: list[Issue] = []
    lines = text.splitlines()

    def line_of(pattern: str) -> int | None:
        for i, ln in enumerate(lines, 1):
            if re.search(pattern, ln):
                return i
        return None

    if "blueprint:" in text:
        bp = data.get("blueprint") if isinstance(data, dict) else None
        if isinstance(bp, dict):
            if "source_url" not in bp:
                issues.append(Issue("warning", "BP002", "blueprint.source_url is missing (needed for re-import/updates)"))
            if "author" not in bp:
                issues.append(Issue("warning", "BP003", "blueprint.author is missing"))
            if "homeassistant" not in bp or not isinstance(bp.get("homeassistant"), dict) or "min_version" not in bp["homeassistant"]:
                has_modern = any(k in text for k in ["triggers:", "conditions:", "actions:", "trigger: state", "action: light"])
                if has_modern or "min_version" not in text:
                    issues.append(Issue("warning", "BP004", 'blueprint.homeassistant.min_version is missing (e.g. "2024.10.0" for triggers/actions syntax)'))
            domain = bp.get("domain")
            if domain not in ("automation", "script", "template"):
                issues.append(Issue("warning", "BP005", f'blueprint.domain should be automation|script|template, got: {domain!r}'))

            inputs = bp.get("input")
            if not isinstance(inputs, dict) or not inputs:
                issues.append(Issue("warning", "BP006", "blueprint.input is empty or not a mapping"))
            else:
                for k, v in inputs.items():
                    if not isinstance(v, dict):
                        issues.append(Issue("warning", "BP007", f"input '{k}' should be a mapping with name/selector"))
                        continue
                    if "selector" not in v and "input" not in v:
                        issues.append(Issue("warning", "BP007", f"input '{k}' has no selector (and is not a section with input:)"))
                    sel = v.get("selector")
                    if isinstance(sel, dict) and "text" in sel:
                        issues.append(Issue("warning", "BP008", f"input '{k}' uses text selector; prefer entity/target/device with filters"))
    return issues


def check_deprecated_keys(text: str, data: dict) -> list[Issue]:
    issues: list[Issue] = []
    lines = text.splitlines()

    def has_top_level(key: str) -> bool:
        return bool(re.search(rf"^{re.escape(key)}\s*:", text, re.MULTILINE))

    if has_top_level("trigger"):
        ln = next((i for i, l in enumerate(lines, 1) if re.search(r"^trigger\s*:", l)), None)
        issues.append(Issue("warning", "HA100", "top-level 'trigger:' is deprecated, use 'triggers:' (HA 2024.10+)", ln, 1))
    if has_top_level("condition"):
        ln = next((i for i, l in enumerate(lines, 1) if re.search(r"^condition\s*:", l)), None)
        issues.append(Issue("warning", "HA101", "top-level 'condition:' is deprecated, use 'conditions:' (HA 2024.10+)", ln, 1))
    if has_top_level("action"):
        ln = next((i for i, l in enumerate(lines, 1) if re.search(r"^action\s*:", l)), None)
        issues.append(Issue("warning", "HA102", "top-level 'action:' is deprecated, use 'actions:' (HA 2024.10+)", ln, 1))

    for i, ln in enumerate(lines, 1):
        stripped = ln.lstrip()
        norm = re.sub(r"^-\s*", "", stripped)
        if re.match(r"platform\s*:\s*state\b", norm):
            issues.append(Issue("warning", "HA110", "platform: state is deprecated, use trigger: state / triggers: - trigger: state", i, len(ln) - len(stripped) + 1))
        if re.match(r"service\s*:\s*\S+", norm) and "action:" not in norm:
            issues.append(Issue("warning", "HA111", "service: is deprecated since HA 2024.8, use action: (e.g. action: light.turn_on)", i, len(ln) - len(stripped) + 1))
        if re.match(r"delay\s*:\s*!input\b", norm):
            issues.append(Issue("warning", "HA120", "delay: !input X should be delay: {seconds: !input X} (structured delay)", i, len(ln) - len(stripped) + 1))

    return issues


def check_inputs_resolve(text: str, data: dict) -> list[Issue]:
    issues: list[Issue] = []
    bp = data.get("blueprint") if isinstance(data, dict) else None
    declared: set[str] = set()
    if isinstance(bp, dict) and isinstance(bp.get("input"), dict):
        for k, v in bp["input"].items():
            if isinstance(v, dict) and "input" in v and isinstance(v["input"], dict):
                declared.update(v["input"].keys())
            else:
                declared.add(k)

    referenced: set[str] = set()
    find_inputs(data, referenced)

    for ref in sorted(referenced):
        if ref not in declared:
            issues.append(Issue("error", "BP010", f"!input '{ref}' has no matching blueprint.input entry (declared: {sorted(declared)})"))

    raw_refs = re.findall(r"!input\s+'?([A-Za-z0-9_]+)'?", text)
    for ref in raw_refs:
        if ref not in declared:
            pass

    return issues


def check_selector_target_vs_entity(text: str, data: dict) -> list[Issue]:
    issues: list[Issue] = []
    bp = data.get("blueprint") if isinstance(data, dict) else None
    if not isinstance(bp, dict) or not isinstance(bp.get("input"), dict):
        return issues
    selectors: dict[str, str] = {}
    for k, v in bp["input"].items():
        if isinstance(v, dict) and "input" in v and isinstance(v["input"], dict):
            for kk, vv in v["input"].items():
                if isinstance(vv, dict) and isinstance(vv.get("selector"), dict):
                    sel = vv["selector"]
                    selectors[kk] = next(iter(sel.keys())) if sel else "unknown"
        elif isinstance(v, dict) and isinstance(v.get("selector"), dict):
            sel = v["selector"]
            selectors[k] = next(iter(sel.keys())) if sel else "unknown"

    if "target:" in text and re.search(r"entity_id\s*:\s*!input", text):
        for sel_name, sel_type in selectors.items():
            if sel_type == "target" and re.search(rf"entity_id\s*:\s*!input\s+'?{re.escape(sel_name)}'?", text):
                issues.append(Issue("warning", "BP020", f"!input '{sel_name}' is a target selector but used as entity_id; use target: !input {sel_name} or switch to entity selector"))
    return issues


def lint_one(path: pathlib.Path) -> list[Issue]:
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        line = getattr(mark, "line", None)
        col = getattr(mark, "column", None)
        if line is not None:
            line += 1
        if col is not None:
            col += 1
        return [Issue("error", "YAML001", f"YAML parse error: {e}", line, col)]

    if not isinstance(data, dict):
        return [Issue("error", "YAML002", "Top-level YAML is not a mapping")]

    issues: list[Issue] = []
    issues.extend(walk_raw_text_issues(text, data))
    issues.extend(check_deprecated_keys(text, data))
    issues.extend(check_inputs_resolve(text, data))
    issues.extend(check_selector_target_vs_entity(text, data))
    issues.extend(check_quoted_input(text))
    issues.extend(check_jinja_input(text))
    return issues


def main() -> int:
    p = argparse.ArgumentParser(description="HA blueprint linter (no HA core dependency)")
    p.add_argument("paths", nargs="+", help="YAML files to lint (supports globs)")
    p.add_argument("--warn-as-error", action="store_true", help="exit non-zero on warnings too")
    p.add_argument("--format", choices=["text", "parsable"], default="text")
    args = p.parse_args()

    expanded: list[pathlib.Path] = []
    for pat in args.paths:
        for m in pathlib.Path(".").glob(pat):
            if m.is_file():
                expanded.append(m)
        direct = pathlib.Path(pat)
        if direct.is_file() and direct not in expanded:
            expanded.append(direct)

    if not expanded:
        print("No files matched", file=sys.stderr)
        return 2

    all_issues: list[tuple[pathlib.Path, Issue]] = []
    for path in sorted(set(expanded)):
        for iss in lint_one(path):
            all_issues.append((path, iss))

    for path, iss in all_issues:
        if args.format == "parsable":
            line = iss.line or 0
            col = iss.col or 0
            print(f"{path}:{line}:{col}: [{iss.level}] [{iss.code}] {iss.message}")
        else:
            print(iss.format(path))

    has_error = any(iss.level == "error" for _, iss in all_issues)
    has_warning = any(iss.level == "warning" for _, iss in all_issues)
    if has_error or (args.warn_as_error and has_warning):
        return 1
    if has_warning:
        return 0 if not args.warn_as_error else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
