# Changelog

All notable changes to the CloudShift project will be documented in this file.

Each release has an **Upgrade-Hinweise** section (new options, manual steps,
breaking changes). `docker/upgrade.sh` shows it before updating a server.

## [1.3.1] - 2026-09-25
### Upgrade-Hinweise
- **Einmalig für Installationen vor dem 25.09.2026:** zuerst `docker/migrate-untracked-config.sh` ausführen (HOWTO Podman, Abschnitt 10). Danach Updates nur noch mit `sh docker/upgrade.sh <version>`.
- `.env` neu: `CLOUDSHIFT_VERSION` (Release-Tag statt `latest` eintragen) und optional `CLOUDSHIFT_REGISTRY`.
- `docker/coriolis.conf`, `docker/users.yaml`, `docker/dashboard/ssl/` und `.env` liegen nicht mehr im Git; Vorlagen: `*.example`.
- Worker: Minion-SSH-Key als Compose-Secret `secrets/olvm_minion_ssh_key` statt `~/.ssh`.
- Zugangsdaten, die früher im Repository standen (JWT-Schlüssel, Benutzer-, DB-, RabbitMQ-, VMware-Worker-Passwörter, TLS-Schlüssel), tauschen.

### Added
- `docker/upgrade.sh`: Update mit Vorabprüfung, Backup, Healthcheck und automatischem Rollback.
- `docker/verify-images.sh`: prüft Images vor dem Push auf Geheimnisse und fehlende Laufzeitdateien.
- `docker/migrate-untracked-config.sh`: einmalige Umstellung bestehender Installationen.
- Release-Workflow: Build bei Git-Tag, Prüfung, Multi-Arch-Push nach Docker Hub.

### Changed
- Images versioniert über `CLOUDSHIFT_VERSION`; alle Dauerdienste mit `restart: unless-stopped`.
- Artifactory-Zugangsdaten nur noch als BuildKit-Secret.
- Dashboard lädt Executions nur für aufgeklappte Transfers statt `include_task_info` im Polling.

### Fixed
- Images ohne `.git`-Build-Kontext: `migrate.cfg` und `coriolis.api.middleware` fehlten (DB-Migration und API defekt).
- API gibt SSH-Keys und Passwörter in der Task-Info nicht mehr im Klartext aus.

### Security
- Keine Geheimnisse mehr im Image oder im Repository (`.dockerignore`, Vorlagen, `.env`).

## [1.0.0] - 2026-06-19
### Added
- Branded CloudShift package name mapped in `setup.cfg`.
- Support for VMware vSphere to Oracle OLVM/oVirt migrations.
- Support for VMware vSphere to Microsoft Hyper-V migrations (WinRM).
- Added `cloudshift-*` console entrypoints for all core services alongside legacy `coriolis-*`.
- Fully integrated web-dashboard deployed via Docker Compose profile `dashboard`.
- Comprehensive guides for VMware-to-OLVM, VMware-to-HyperV, and Air-Gapped Deployments.
