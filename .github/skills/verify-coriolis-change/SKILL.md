---
name: verify-coriolis-change
description: "Verify a Coriolis code change with the smallest correct tox scope first, then expand checks based on risk. USE FOR: verify change, what tests should I run, validate PR, pre-commit verification, minimal tox command selection, Coriolis test strategy."
---

# Verify Coriolis Change

Use this skill to select and run the smallest valid verification commands first, then expand only when needed.

## Inputs

- Changed files list (or git diff scope).
- Change type: provider, API, taskflow, tests only, config only, integration-sensitive.
- Time budget: quick, standard, thorough.

## Decision Flow

1. Identify touched areas:
   - `coriolis/providers/**` -> provider-focused validation.
   - `coriolis/tests/**` -> targeted test validation.
   - `tox.ini`, `.stestr.conf`, `test-requirements.txt` -> test-config validation.
   - cross-service/runtime code (`coriolis/api/`, `coriolis/conductor/`, `coriolis/worker/`, `coriolis/taskflow/`) -> broader validation.

2. Start with the smallest meaningful command:
   - Single test method/module if change is localized.
   - `tox -e py3 -- <target>` for most code changes.
   - `tox -e pep8` when style/lint-sensitive files are changed.

3. Expand only if risk or scope requires it:
   - `tox -e cover` for non-trivial behavior changes or refactors.
   - `tox -e py3,pep8,cover` for release/merge confidence.
   - Integration tests only when integration behavior is touched and prerequisites are available.

## Canonical Commands

```bash
# Focused unit/integration-excluding run
tox -e py3 -- coriolis.tests.<module>

# Lint
tox -e pep8

# Coverage gate (>= 82%)
tox -e cover

# CI-equivalent confidence
tox -e py3,pep8,cover

# Heavy integration (root + system prerequisites)
sudo -E tox -e integration
```

## Output Template

Provide:
- Recommended command sequence (smallest -> broadest).
- Which risks are covered by each step.
- What was not executed and why (especially integration constraints).

## Guardrails

- Do not claim integration execution unless it was actually run.
- Do not switch the test runner model away from stestr.
- Keep verification proportionate to change risk and blast radius.
