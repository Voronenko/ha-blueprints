# ha-blueprints

Home Assistant blueprints — validated with lightweight Jinja tests, native `BLUEPRINT_SCHEMA` checks, and CI on every push.

## Import a blueprint

Click **Import Blueprint** — it opens your Home Assistant (via [My Home Assistant](https://my.home-assistant.io/)) with the import dialog pre-filled. Requires My Home Assistant linked to your instance. Alternatively, open **Settings → Automations & Scenes → Blueprints → Import Blueprint** in HA and paste the import URL.

To update an imported blueprint: **Settings → Automations & Scenes → Blueprints → ⋯ → Re-import blueprint**.

## Automation blueprints

### [Motion-activated Light](docs/motion-illuminance.md) — `motion-illuminance.yaml`

Turn on a light on motion when dark by illuminance **or** inside the sun window (or when `All day` is enabled). Any configured illuminance sensor below threshold overrides the time check.

[![Import motion-illuminance](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://raw.githubusercontent.com/Voronenko/ha-blueprints/master/blueprints/motion-illuminance.yaml)

[Code](blueprints/motion-illuminance.yaml) · [Docs](docs/motion-illuminance.md)

### [ZHA — Sonoff SNZB-01P Button](docs/button-sonoff-znzb-01p.md) — `button-sonoff-znzb-01p.yml`

ZHA `zha_event` from a Sonoff SNZB-01P button → 3 actions (single press / double press / hold) gated on `command`/`cluster_id: 6`/`endpoint_id: 1`.

[![Import SNZB-01P button](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://raw.githubusercontent.com/Voronenko/ha-blueprints/master/blueprints/button-sonoff-znzb-01p.yml)

[Code](blueprints/button-sonoff-znzb-01p.yml) · [Docs](docs/button-sonoff-znzb-01p.md)

## Development

```sh
make lint            # yamllint + blueprint semantic lint
make lint-native     # BLUEPRINT_SCHEMA + template compilation (needs .venv)
make test-native     # pytest (JUnit junit.xml, published in CI)
pre-commit install   # actionlint hook for .github/workflows/*.yml
```

CI (`actions/checkout@v6`, `setup-python@v6`, `dorny/test-reporter@v3`/`upload-artifact@v6`, all Node 24) publishes JUnit results as a Check + artifact on every push/PR.
