#!/usr/bin/env python3
"""Check that workflow actions and Docker image refs are pinned."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
DOCKERFILE = ROOT / "deploy" / "Dockerfile"

USES_REF_RE = re.compile(r"^[^/\s]+/[^@\s]+@[0-9a-f]{40}$")
IMAGE_REF_RE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")


def main() -> int:
    errors: list[str] = []
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        errors.extend(check_workflow(path))
    errors.extend(check_dockerfile(DOCKERFILE))

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    return 0


def check_workflow(path: Path) -> list[str]:
    errors: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        workflow = yaml.safe_load(handle)
    for job_name, job in (workflow.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            uses = step.get("uses")
            if uses and not USES_REF_RE.match(uses):
                errors.append(f"{path}: job {job_name} step uses mutable action ref: {uses}")
    return errors


def check_dockerfile(path: Path) -> list[str]:
    errors: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("FROM "):
            ref = stripped.split(None, 1)[1]
            if "@" not in ref or not IMAGE_REF_RE.match(ref):
                errors.append(f"{path}:{lineno} FROM must use digest pin: {ref}")
        elif stripped.startswith("COPY ") and "--from=" in stripped:
            match = re.search(r"--from=([^\s]+)", stripped)
            if match:
                ref = match.group(1)
                if "@" not in ref or not IMAGE_REF_RE.match(ref):
                    errors.append(f"{path}:{lineno} COPY --from must use digest pin: {ref}")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
