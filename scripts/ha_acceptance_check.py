#!/usr/bin/env python3
"""Optional containerized check: starts a HA config check in Docker against this blueprint.
Useful as a full-stack smoke test (mirrors what HA core imports).
Requires Docker; falls back to native check if Docker unavailable."""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import tempfile


def _have_docker() -> bool:
    return shutil.which("docker") is not None


def main() -> int:
    p = argparse.ArgumentParser(description="Dockerized HA blueprint acceptance (opt-in)")
    p.add_argument("--image", default="ghcr.io/home-assistant/home-assistant:2025.1")
    p.add_argument("--blueprint", default="motion-illuminance.yaml")
    p.add_argument("--timeout", type=int, default=120)
    args = p.parse_args()

    bp_path = pathlib.Path(args.blueprint)
    if not bp_path.is_file():
        print(f"Blueprint not found: {bp_path}", file=sys.stderr)
        return 2
    if not _have_docker():
        print("Docker not found; running native check instead.", file=sys.stderr)
        r = subprocess.run([sys.executable, "scripts/ha_blueprint_native_check.py", str(bp_path)])
        return r.returncode

    # Build minimal HA config with this blueprint imported
    with tempfile.TemporaryDirectory() as tmp:
        cfg = pathlib.Path(tmp) / "config"
        bp_dir = cfg / "blueprints" / "automation" / "homatorium"
        bp_dir.mkdir(parents=True, exist_ok=True)
        bp_dir.joinpath("motion-illuminance.yaml").write_text(bp_path.read_text(encoding="utf-8"), encoding="utf-8")
        # Minimal configuration.yaml that loads blueprint domain
        cfg.joinpath("configuration.yaml").write_text(
            """
default_config:
automation: !include automations.yaml
""".lstrip(),
            encoding="utf-8",
        )
        cfg.joinpath("automations.yaml").write_text("[]\n", encoding="utf-8")
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{cfg}:/config",
            args.image,
            "python",
            "-m",
            "homeassistant",
            "--script",
            "check_config",
            "--config",
            "/config",
        ]
        print(f"Running dockerized acceptance: {' '.join(cmd)}")
        r = subprocess.run(cmd, timeout=args.timeout)
        if r.returncode == 0:
            print("Dockerized HA check_config: PASS")
        else:
            print(f"Dockerized HA check_config: FAIL ({r.returncode})", file=sys.stderr)
        return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
