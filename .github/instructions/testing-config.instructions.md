---
applyTo: "**/{tox.ini,.stestr.conf,test-requirements.txt}"
description: "Use when editing Coriolis test configuration files, tox envs, stestr settings, or test dependency pins."
---

# Coriolis Test Config Instructions

- Treat tox and stestr files as the source of truth for test execution behavior.
- Keep changes minimal and scoped to the target env or runner behavior.
- Preserve stestr-first execution model; do not introduce pytest-specific config.
- For tox changes:
  - Keep `py3`, `pep8`, and `cover` behavior aligned with existing CI expectations.
  - Do not lower coverage thresholds without explicit request.
  - Keep integration env root requirements and notes intact unless intentionally updated.
- For test dependency changes:
  - Avoid casual unpins/upgrades in core tooling without explaining compatibility impact.
  - Keep ordering constraints/comments in `test-requirements.txt` when present.
- When changing test config semantics, include at least one validating command in your verification plan.
