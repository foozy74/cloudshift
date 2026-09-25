---
name: cloudshift-release
description: "Prepare, verify and publish a CloudShift release and update servers safely. USE FOR: release, new version, tag a version, build and push images, Docker Hub push, image check before push, changelog upgrade notes, upgrade/update a server, rollback."
---

# CloudShift Release and Upgrade

Every step here exists because it failed at least once. A broken or leaking
image reaches every server through the internal registry
(`docker.registry.it.internal` mirrors Docker Hub), so the checks are not
optional.

## Inputs

- Version, e.g. `1.4.0` (semver, no `v` prefix, like the existing git tags).
- Repos: `coriolis` (development, remote `fork`, branch `master`) and
  `../cloudshift` (deployment, remote `origin`, branch `main`). Releases are
  built from cloudshift.

## 1. Preconditions

- Working trees clean, `master`/`main` pushed. **Never force-push** `master`/`main`:
  servers cannot pull a rewritten history.
- Python code identical in both repos (develop in coriolis, then transfer):
  ```bash
  diff -rq --exclude=__pycache__ coriolis/coriolis ../cloudshift/coriolis
  ```
  Environment-specific files differ on purpose: `Dockerfile`,
  `docker-compose*.yml`, `setup.cfg`, `GEMINI.md`/`.gemini/`.
- New files are tracked in git, new Python packages have an `__init__.py`,
  new non-Python runtime files are listed in `MANIFEST.in`. The local stack
  bind-mounts the source tree and hides these mistakes; images do not.

## 2. Rules for the change itself

- New config option: safe default in code (`cfg.*Opt(default=...)`) and an
  entry in `docker/coriolis.conf.example`. New `.env` key: `.env.example`.
- DB migrations additive only (add tables/columns; no rename/drop in the same
  release), so the previous version still runs against the new schema.
- API changes backwards compatible (add fields, do not remove/rename).
- No secrets in tracked files or images (`.env`, `docker/coriolis.conf`,
  `docker/users.yaml`, `docker/dashboard/ssl/`, `secrets/` stay untracked).

## 3. Tests

```bash
.venv/bin/python -m stestr run --exclude-regex coriolis.tests.integration
.venv/bin/python -m flake8 coriolis
shellcheck -S warning docker/*.sh
```
`tox -e py3,pep8,cover` is the reference where tox is installed.

## 4. Local image check (before tagging)

In cloudshift, build like CI does and verify:
```bash
docker build --build-arg PBR_VERSION=<version> --build-arg PIP_INDEX_URL=https://pypi.org/simple \
  -t cloudshift-verify:core .
docker build -t cloudshift-verify:dashboard docker/dashboard
sh docker/verify-images.sh cloudshift-verify:core cloudshift-verify:dashboard   # must print OK
```
Then start an isolated stack from these images (own compose project, container
names and ports so the local stack is untouched) on a **fresh database** and
check: `db-sync` exits 0, all services running, login and
`GET /v1/<project>/transfers` return 200. Test `sh docker/upgrade.sh` from the
previous version to the new one (overrides: `COMPOSE`, `RT`,
`CONTAINER_PREFIX`, `API_URL`, `DASHBOARD_URL`).

## 5. Changelog, tag, publish

1. `CHANGELOG.md`: `## [<version>] - <date>` with `### Upgrade-Hinweise`
   (new options, manual steps, breaking changes). `docker/upgrade.sh` prints
   this section on the server before updating.
2. Tag both repos (normal push):
   ```bash
   git tag <version> && git push origin main <version>     # cloudshift -> triggers the release workflow
   git tag <version> && git push fork master <version>     # coriolis
   ```
3. `.github/workflows/docker-build.yml` builds amd64, runs
   `docker/verify-images.sh`, and only then pushes multi-arch images
   (`<version>`, `<major>.<minor>`, `sha-<commit>`, `latest`) to Docker Hub.
   Needs the repository secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`.
4. Confirm: `docker buildx imagetools inspect thesolution/cloudshift:<version>`
   lists linux/amd64 and linux/arm64.

Manual pushes are the exception; if unavoidable, run
`docker/verify-images.sh` against the exact image before `--push`.

## 6. Update servers

```bash
cd /appl/containers/cloudshift
git pull
sh docker/upgrade.sh <version>
```
The script refuses to run with active executions, missing `.env` keys or an
unavailable image; it backs up the database and config to `backups/`, updates,
health-checks and rolls back automatically (images and, if the schema changed,
the database dump). Details:
`docs/HOWTO_RUN_PODMAN_ROOTLESS_INTERNAL_REGISTRY.md`, section 9.1.

Installations older than 2026-09-25 need the one-off
`docker/migrate-untracked-config.sh` first (same HOWTO, section 10).

## Never

- Force-push `master`/`main`.
- Commit secrets or runtime config; pass credentials as `--build-arg`.
- Publish an image that did not pass `docker/verify-images.sh` and the
  fresh-database stack test.
- Update a server with `pull` + `up` by hand instead of `docker/upgrade.sh`.
