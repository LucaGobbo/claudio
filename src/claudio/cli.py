"""claudio CLI entry point."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from claudio.projects import select_project
from claudio.settings import (
    ConfigError,
    merged_claudio_config,
    highest_claude_env,
    validate_projects,
)


def main() -> None:
    from importlib.metadata import version

    parser = argparse.ArgumentParser(
        prog="claudio",
        description=(
            "Switch between Claude Code projects with different API keys. "
            "All extra arguments are forwarded to the `claude` CLI."
        ),
        add_help=True,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {version('claudio')}"
    )
    # We capture only our own flags; everything else goes to claude.
    args, claude_args = parser.parse_known_args()

    config = merged_claudio_config()

    if not config:
        # No claudio config at all — just launch claude directly.
        _exec_claude(claude_args)

    try:
        projects = validate_projects(config)
    except ConfigError as exc:
        print(f"claudio: config error: {exc}", file=sys.stderr)
        sys.exit(1)

    if len(projects) == 1:
        selected = projects[0]
    else:
        selected = select_project(projects)
        if selected is None:
            sys.exit(130)

    project_env = selected.get("env", {})
    extra_settings_args: list[str] = []
    if project_env:
        _, base_env = highest_claude_env()
        merged = {**base_env, **project_env}
        merged = _resolve_secret_references(merged)
        extra_settings_args = ["--settings", json.dumps({"env": merged})]

    print(f"Using project: {selected['name']}")
    _exec_claude(extra_settings_args + claude_args)


def _resolve_secret_references(env: dict[str, str]) -> dict[str, str]:
    resolved = {}
    for key, value in env.items():
        if value.startswith("op://"):
            resolved[key] = _read_op_secret(key, value)
        elif value.startswith("keychain://"):
            resolved[key] = _read_keychain_secret(key, value)
        else:
            resolved[key] = value
    return resolved


def _read_op_secret(key: str, value: str) -> str:
    result = subprocess.run(
        ["op", "read", value],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"claudio: failed to read 1Password secret for {key}: {result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)
    return result.stdout.strip()


def _read_keychain_secret(key: str, value: str) -> str:
    if sys.platform != "darwin":
        print(
            f"claudio: keychain:// references are only supported on macOS (env var {key})",
            file=sys.stderr,
        )
        sys.exit(1)
    service, _, account = value[len("keychain://") :].partition("/")
    if not service or not account:
        print(
            f"claudio: invalid keychain reference for {key}: expected keychain://<service>/<account>",
            file=sys.stderr,
        )
        sys.exit(1)
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"claudio: failed to read Keychain secret for {key}: {result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)
    return result.stdout.strip()


def _exec_claude(claude_args: list[str]) -> None:
    """Replace the current process with `claude`."""
    if sys.platform == "win32":
        result = subprocess.run(["claude", *claude_args], shell=True)
        sys.exit(result.returncode)
    else:
        os.execvp("claude", ["claude", *claude_args])
