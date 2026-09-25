---
applyTo: "coriolis/tests/**/*.py"
description: "Use when editing or adding Coriolis tests, stestr test paths, tox test commands, or integration-test related test code."
---

# Coriolis Testing Instructions

- Use stestr-compatible naming and paths. Do not assume pytest conventions.
- Prefer running focused tests first:
  - tox -e py3 -- coriolis.tests.<module>
  - tox -e py3 -- coriolis.tests.<module>.<Class>.<method>
- For integration tests under coriolis/tests/integration/, treat them as privileged tests:
  - Require root execution and environment support (scsi_debug, Docker).
  - Do not claim they were run unless they were actually executed.
- Keep test structure aligned with existing folders:
  - API and management behavior near existing management/ and top-level integration modules.
  - Transfer/deployment behavior under transfers/ or deployments/ integration folders.
- When behavior changes, update or add tests in the nearest existing module before creating new test layout patterns.
- Avoid introducing pytest-only helpers, markers, or fixtures.
- Keep assertions deterministic; avoid time-sensitive sleeps when a polling helper already exists in the codebase.
