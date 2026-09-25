# CloudShift (Coriolis) — Agent Guide

OpenStack-style migration service in Python. Packaged as `cloudshift` (see [setup.cfg](setup.cfg)) but the Python package and all imports are still `coriolis` — use `coriolis.*` in code, not `cloudshift`. Keep changes minimal, local, and consistent with existing `oslo.*` and taskflow patterns.

Scope is specifically **VMware vSphere → Oracle OLVM/oVirt** and **VMware vSphere → Microsoft Hyper-V** migration; these are the in-scope paths, even though more providers are registered (see Service Boundaries). Treat broader multi-cloud claims in prose as legacy/aspirational, not implemented.

## Start Here

- Read [README.md](README.md) for project basics (README.rst is the same content kept for packaging).
- Use [tox.ini](tox.ini) as source of truth for test/lint behavior.
- For integration harness details, read [coriolis/tests/integration/README.md](coriolis/tests/integration/README.md).
- For operational migration docs, prefer linking to [docs/MIGRATION_HOWTO.md](docs/MIGRATION_HOWTO.md) and [docs/VMWARE_OLVM_HOWTO.md](docs/VMWARE_OLVM_HOWTO.md) instead of duplicating instructions.

## Service Boundaries

Entrypoints are defined in [setup.cfg](setup.cfg) under `console_scripts`:

- `coriolis-api`: REST/WSGI surface.
- `coriolis-conductor`: orchestration and workflow coordination.
- `coriolis-worker`: task execution.
- `coriolis-scheduler`: scheduled task orchestration.
- `coriolis-minion-manager`: minion lifecycle and pools.
- `coriolis-deployer-manager`: deployment pipeline orchestration.
- `coriolis-transfer-cron`: cron-driven transfer triggers.
- `coriolis-dbsync`: DB schema migrations.

Provider classes are registered under `coriolis.providers` in [setup.cfg](setup.cfg): `vmware_vsphere` (export, [coriolis/providers/vmware/](coriolis/providers/vmware/)), `vmware_import`, `olvm` (import, [coriolis/providers/olvm/](coriolis/providers/olvm/)), `olvm_export`, `hyperv` (import via WinRM/PowerShell, [coriolis/providers/hyperv/](coriolis/providers/hyperv/)), and `proxmox` (import, [coriolis/providers/proxmox/](coriolis/providers/proxmox/)). These entry points are **not** read at runtime: [coriolis/providers/factory.py](coriolis/providers/factory.py) loads only the class paths listed in the `providers` option of `coriolis.conf` (e.g. [docker/coriolis.conf](docker/coriolis.conf)), so a new provider must be added there to be found. New import providers should mirror the OLVM single-file `imp.py` pattern (same 8 base classes, reuse `backup_writers.HTTPBackupWriterBootstrapper` and `provider_utils`). The `hyperv` provider supports the full transfer + deploy + OS-morphing flow; disk snapshots are deliberate no-ops (fall back to `clone_disks=True`), matching OLVM.

Messaging is `oslo.messaging` (RabbitMQ in normal deployments). Auth path uses Keystone and Barbican abstractions, but a standalone `noauth` API pipeline mode also exists (see README).

## Build, Test, Lint

Use these commands by default:

```bash
# Unit/integration-excluding test run
tox -e py3

# Flake8 lint
tox -e pep8

# Coverage (gate: >= 75%, see tox.ini)
tox -e cover

# CI-equivalent local run
tox -e py3,pep8,cover
```

Targeted test runs:

```bash
tox -e py3 -- coriolis.tests.test_foo
tox -e py3 -- coriolis.tests.test_foo.TestClass.test_method
```

Integration tests (heavy, root-required):

```bash
sudo -E tox -e integration
sudo -E tox -e integration -- --no-discover coriolis/tests/integration/test_smoke.py
```

## Project-Specific Pitfalls

- Test runner is `stestr`, not `pytest`.
- CI (`.github/workflows/ci.yml`) runs on `main` pushes/PRs on Python 3.10–3.13; `tox -e py3,pep8,cover` is the unit gate.
- Integration suite requires root, the `scsi_debug` kernel module (kernel 5.11+ for `per_host_store=1`), Docker, and the `coriolis-data-minion:test` image (build from `coriolis/tests/integration/dockerfiles/data-minion/`).
- Test an external provider via `CORIOLIS_PROVIDER_PACKAGE=<path|git+...> sudo -E tox -e integration`.
- Coverage gate is enforced by `tox -e cover` at 75% (`--fail-under=75` in [tox.ini](tox.ini)).
- DB migrations are `sqlalchemy-migrate`-based in [coriolis/db/sqlalchemy/migrate_repo/](coriolis/db/sqlalchemy/migrate_repo/) (not Alembic).
- Dependency pins are intentional; do not casually unpin:
	- `kombu==4.6.10`
	- `sqlalchemy<2.0.0`
	- `oslo.config<9.8.0`, `oslo.context<6.0.0`, `oslo.db<=12.3.2`, `oslo.messaging==12.2.0`
- Packaging uses `pbr` and includes non-Python assets via [MANIFEST.in](MANIFEST.in). Resource omissions can break runtime behavior.

## Relationship to coriolis (upstream)

Repository chain:

```
cloudbase/coriolis        (remote `origin` in coriolis — original upstream)
  └─ foozy74/coriolios    (remote `fork` in coriolis — note the "io" spelling; local: ../coriolis, development happens here)
       └─ foozy74/cloudshift  (remote `origin` in cloudshift, which has coriolis as remote `local-coriolis`; local: ../cloudshift)
```

In coriolis, local `master` tracks `origin/master` (cloudbase), so a bare `git push` targets cloudbase; push to the fork explicitly with `git push fork master`. cloudshift works on `main`.

This repo is the deployment variant for the internal Drei/three.com environment. Development happens first in the sister repo `../coriolis` (added here as git remote `local-coriolis`); changes are then carried over to this repo. The Python code under `coriolis/` should stay identical to coriolis, so prefer transferring changes from there over editing code here directly. These environment-specific files exist only here or differ from coriolis and must be preserved when transferring:

- `Dockerfile`: `BASE_IMAGE` build arg, PyPI via the `artifactory.three.com` proxy (`ARTIFACTORY_USER`/`ARTIFACTORY_PW`), `CMD cloudshift-api`.
- `docker-compose.yml` (images from `docker.registry.it.internal`, `NO_PROXY` for `.three.com`/`.internal`) and `docker-compose.podman.yml`.
- `setup.cfg`: additional `cloudshift-*` console scripts alongside `coriolis-*`.
- `.github/workflows/`: `ci.yml` on `main` (Python 3.10–3.13) and `docker-build.yml` (publishes `ghcr.io/thesolution/cloudshift` and `-dashboard` on `v*` tags); no integration-test workflow.
- `GEMINI.md` / `.gemini/`: a graphify knowledge graph lives in `graphify-out/`. If `graphify-out/graph.json` exists, `graphify query "<question>"` can answer codebase questions; after code changes run `graphify update .`.

## Editing Guidelines For Agents

- Prefer small patches in existing modules over broad refactors.
- Preserve RPC/service boundaries; avoid cross-service shortcut calls.
- Reuse existing patterns from sibling modules in the same package.
- Keep provider work isolated to [coriolis/providers/](coriolis/providers/).
- For schema or API changes, update both implementation and corresponding schema/policy/test files in the same change.
- Do not introduce new frameworks, formatters, or test runners unless explicitly requested.

## Validation Checklist Before Finishing

- Run relevant `tox` envs for touched code.
- For non-trivial behavior changes, add or update tests first in [coriolis/tests/](coriolis/tests/).
- If touching integration-only behavior, document what was not executed locally and why.