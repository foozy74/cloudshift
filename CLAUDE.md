# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

The imported `AGENTS.md` is the primary guide (commands, pins, pitfalls, editing rules). This file adds architecture context. Code changes originate in the upstream sister repo `../coriolis` and are transferred here (see "Relationship to coriolis (upstream)" in `AGENTS.md`).

## Architecture: How a Transfer Executes

1. **API** (`coriolis/api/v1/`) validates the request against the JSON schemas in `coriolis/schemas/` and the policies in `coriolis/policies/`, then makes an RPC call to the conductor.
2. **Conductor** (`coriolis/conductor/rpc/server.py`, about 3.7k lines, the core of the system) builds the execution as a DB-persisted dependency graph of tasks (`_create_task(..., depends_on=...)`). It asks the minion-manager to allocate minions and dispatches ready tasks to workers (`_begin_tasks`). Workers report back through `task_completed` / `set_task_error`, and `_advance_execution_state` then schedules the next tasks, including on-error cleanup tasks.
3. **Worker** (`coriolis/worker/rpc/server.py`) runs each task in a **separate `spawn` subprocess**. Logs and results come back over multiprocessing queues, and `LD_LIBRARY_PATH` is extended from the provider's `get_shared_library_directories`. Task code therefore must be picklable and must not rely on in-process state from the worker service.
4. **Tasks** (`coriolis/tasks/`) map a `constants.TASK_TYPE_*` to a `TaskRunner` subclass through `_TASKS_MAP` in `tasks/factory.py`. Each runner declares its required/returned `task_info` keys and its required provider types, and calls into the provider.
5. **Providers** (`coriolis/providers/`) implement capability ABCs from `providers/base.py`. `factory.PROVIDER_TYPE_MAP` maps `constants.PROVIDER_TYPE_*` to a base class, and `get_provider(platform, type, ...)` picks the class via `cls.platform` + `issubclass`. A provider's capabilities are therefore exactly the base classes it inherits.
6. **OS morphing** (`coriolis/osmorphing/`) runs on a temporary minion attached to the target disks. `osdetect/` identifies the guest OS, `osmount/` mounts it, and the per-distro modules (`redhat.py`, `ubuntu.py`, `windows.py`, …) inject drivers and fix the network config. Providers can supply their own tools through `get_os_morphing_tools` / `get_custom_os_detect_tools`.

Other components: `minion_manager/` (minion pools, allocation and healthchecks, uses taskflow from `coriolis/taskflow/`), `transfer_cron/` + `scheduler/` (scheduled transfer executions), `deployer_manager/`, and `db/` (SQLAlchemy models + `sqlalchemy-migrate` repo).

Adding a new task type touches several places at once: `constants.TASK_TYPE_*`, `_TASKS_MAP`, the TaskRunner, the conductor's task-graph construction, and tests.

## Local Stack / Dashboard

- `docker-compose up -d` starts MariaDB, RabbitMQ, all Coriolis services and the Nginx dashboard (`docker/dashboard/`, ports 80/443; API on 7667). `DASHBOARD_README.md` still mentions port 8080, but `docker-compose.yml` maps 80/443. See `DASHBOARD_README.md`.
- The compose file bind-mounts `./coriolis` read-only into most service containers, so code changes usually take effect after a container restart, without a rebuild. Check the service in `docker-compose.yml` to be sure.
- Runtime config: `docker/coriolis.conf`. Policies: `etc/coriolis/policy.yaml`.

## Testing Notes

- Unit tests mirror the package layout under `coriolis/tests/` (e.g. provider tests in `coriolis/tests/providers/`).
- Path-scoped rules also live in `.github/instructions/` (providers, tests, test config), and a verification skill lives in `.github/skills/verify-coriolis-change/SKILL.md`. Start with the smallest tox scope and widen from there.
