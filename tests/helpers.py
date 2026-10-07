from __future__ import annotations

import datetime as dt
import pathlib
import types
import yaml


class InputTag(str):
    pass


def _input_constructor(loader, node):
    if isinstance(node, yaml.ScalarNode):
        return InputTag(loader.construct_scalar(node))
    if isinstance(node, yaml.SequenceNode):
        return InputTag(loader.construct_scalar(node))
    return InputTag(loader.construct_scalar(node))


yaml.SafeLoader.add_constructor("!input", _input_constructor)


def load_blueprint(path: pathlib.Path | str = "blueprints/motion-illuminance.yaml") -> dict:
    text = pathlib.Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return data, text


def extract_value_template(data: dict, index: int = 0) -> str:
    conds = data.get("conditions") or []
    if conds:
        # PyYAML keeps it as plain string
        return conds[index].get("value_template", "")
    # gate lives inside actions[].choose[].conditions[]
    for a in data.get("actions") or []:
        if not isinstance(a, dict):
            continue
        choose_val = a.get("choose")
        entries = choose_val if isinstance(choose_val, list) else (choose_val or {}).get("choose", [])
        for entry in entries or []:
            for c in entry.get("conditions") or []:
                if isinstance(c, dict) and "value_template" in c:
                    return c["value_template"]
    return ""


def extract_wait_template(data: dict) -> str:
    for a in data.get("actions") or []:
        if "wait_template" in a:
            return a["wait_template"]
    return ""


def extract_after_condition_template(data: dict) -> str:
    # second template condition after wait+delay
    conds_in_actions = [a for a in data.get("actions") or [] if "value_template" in a or "condition" in a]
    # fallback: last condition before light.turn_off
    for a in reversed(data.get("actions") or []):
        if a.get("condition") == "template" and "value_template" in a:
            return a["value_template"]
    return ""


def iter_template_conditions(data: dict) -> list[str]:
    """All template-condition texts anywhere in the action tree
    (top-level, choose sequences, if branches, repeat, ...)."""
    out: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if node.get("condition") == "template" and "value_template" in node:
                out.append(node["value_template"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for i in node:
                walk(i)

    walk(data.get("actions") or [])
    return out


class _StatesNS:
    """`states` callable that also exposes `states.light` as state objects."""

    def __init__(self, states: dict[str, str], light_objs: list):
        self._states = states
        self.light = light_objs

    def __call__(self, entity_id: str):
        return self._states.get(entity_id)


def make_light_obj(entity_id: str, state: str, user_id: str | None = None):
    return types.SimpleNamespace(
        entity_id=entity_id,
        state=state,
        context=types.SimpleNamespace(user_id=user_id),
    )


# Button blueprint helpers

def get_press_action(press: str) -> str:
    return {"single": "single_press", "double": "double_press", "hold": "hold"}[press]


def dispatch_button(data: dict, *, command: str, cluster_id: int, endpoint_id: int) -> str | None:
    """Return 'single_press'|'double_press'|'hold' or None (no match).

    Evaluates each choose branch the same way HA does: all 3 template conditions
    (command, cluster_id, endpoint_id) must hold.
    """
    import re as _re

    actions = data.get("actions") or []
    choose = next((a for a in actions if "choose" in a), None)
    if not choose:
        return None

    def eval_value_template(tmpl: str) -> bool:
        s = (tmpl or "").strip()
        if "command ==" in s:
            m = _re.search(r"command\s*==\s*['\"]([^'\"]+)['\"]", s)
            return bool(m) and command == m.group(1)
        if "cluster_id ==" in s:
            m = _re.search(r"cluster_id\s*==\s*(\d+)", s)
            return bool(m) and int(m.group(1)) == cluster_id
        if "endpoint_id ==" in s:
            m = _re.search(r"endpoint_id\s*==\s*(\d+)", s)
            return bool(m) and int(m.group(1)) == endpoint_id
        return False

    for entry in choose.get("choose", []) or []:
        conds = entry.get("conditions") or []

        ok = True
        for c in conds:
            if isinstance(c, str):
                if not eval_value_template(c):
                    ok = False
                    break
            elif isinstance(c, dict) and c.get("condition") == "template":
                if not eval_value_template(c.get("value_template", "")):
                    ok = False
                    break
            else:
                ok = False
                break
        if ok:
            seq = entry.get("sequence")
            name = str(seq).lstrip() if isinstance(seq, str) else str(seq) if seq is not None else ""
            if name in ("single_press", "double_press", "hold"):
                return name
            repr_entry = str(entry)
            for cand in ("single_press", "double_press", "hold"):
                if cand in repr_entry or cand in name:
                    return cand
            return name or None
    return None


def render_template(tmpl_src: str, *, now_dt: dt.datetime, next_rising: dt.datetime | None, next_setting: dt.datetime | None, states: dict[str, str], variables: dict, light_objs: list | None = None) -> bool:
    import jinja2

    env = jinja2.Environment(undefined=jinja2.Undefined)

    # helpers
    def fake_is_state(entity_id: str, state: str) -> bool:
        return states.get(entity_id) == state

    def fake_state_attr(entity_id: str, attr: str):
        if entity_id == "sun.sun" and attr == "next_rising":
            return next_rising.isoformat() if next_rising else None
        if entity_id == "sun.sun" and attr == "next_setting":
            return next_setting.isoformat() if next_setting else None
        return None

    def fake_as_datetime(v):
        if v is None:
            return None
        # HA's as_datetime parses ISO
        try:
            # handle already datetime
            if isinstance(v, dt.datetime):
                return v
            s = str(v)
            # Python 3.12 fromisoformat handles +00:00
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    # timedelta is available via datetime.timedelta in HA templates
    env.globals.update(
        {
            "states": _StatesNS(states, light_objs or []),
            "is_state": fake_is_state,
            "state_attr": fake_state_attr,
            "as_datetime": fake_as_datetime,
            "now": lambda: now_dt,
            "timedelta": dt.timedelta,
            "namespace": jinja2.utils.Namespace if hasattr(jinja2.utils, "Namespace") else _ns,
            "float": float,
            "int": int,
        }
    )
    # Provide filter default for e.g. | default('any', true)
    # Jinja already has it; ensure variables are globals
    for k, v in variables.items():
        env.globals[k] = v

    # HA's template has {% set ... %} etc
    template = env.from_string(tmpl_src)
    rendered = template.render()
    text = rendered.strip().lower()
    # HA truthiness: "true"/"false"
    if "true" in text and "false" not in text:
        return True
    if "false" in text and "true" not in text:
        return False
    # Fallback: if template returned boolean string directly
    return text == "true"


class _ns:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
