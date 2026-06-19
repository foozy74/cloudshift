# CloudShift

> **Workload Migration as a Service — by [thesolution.at](https://cloudshift.thesolution.at)**

CloudShift is a production-ready migration engine designed to automate the transfer and deployment of virtual machines from **VMware vSphere** (Origin) into **Oracle OLVM/oVirt** and **Microsoft Hyper-V** (Destination) environments.

It supports incremental disk replication, automated operating system adaptation (OS morphing/driver injections), and full web-based dashboard management.

---

## Key Features

- **Replication**: Live incremental disk synchronization minimizing guest downtime.
- **Automated OS Morphing**: Injects KVM VirtIO, Hyper-V Integration Services, GRUB modifications, and network mappings automatically during cutover.
- **Hyper-V Import**: Imports directly to Hyper-V hosts/clusters via WinRM/PowerShell.
- **OLVM/oVirt Import**: Dynamic sparse/raw disk allocation based on destination storage domains (block vs. file).
- **Network Auto-Provisioning**: Automates logical network and VNIC profile creation on OLVM based on source VMware VLAN-IDs.
- **VLAN Conflict Prevention**: Halts migration with safe error messages if a network exists under the same name but with a mismatched VLAN-ID.
- **Per-Migration Logging**: Creates structured JSON-Lines logs tracking migration steps and precise duration metrics.
- **Web-Based GUI**: Clean and premium responsive dashboard containerized out-of-the-box.
- **Standalone (NoAuth) Mode**: Built-in support to run without an active OpenStack Keystone instance.

---

## Oracle OLVM Network Auto-Provisioning

CloudShift automatically provisions logical networks and VNIC profiles in the target Oracle OLVM/oVirt environment during import:
- **VLAN ID Extraction**: VLAN-IDs are fetched directly from source VMware Distributed Portgroups during replication.
- **Idempotency**: Existing networks are re-used. If a network name is not found, a new logical network with the correct VLAN-ID is created, attached to the Datacenter and Cluster, and assigned a default VNIC profile.
- **Safety check**: If a network name matches but has a different VLAN-ID on OLVM, the migration aborts with a validation error (`InvalidInput`) to prevent misconfigured traffic.
- **Override**: Explicit mappings in the migration `network_map` skip auto-provisioning.

---

## Per-Migration Logging

Detailed migration execution states are logged in structured JSON-Lines format:
- **Path**: Logs are written to `/var/log/coriolis/migrations/<instance_name>_<timestamp>.log` (configurable via `olvm.migration_log_dir` in `/etc/coriolis/coriolis.conf`).
- **Events**: Tracked events include `migration_start`, `network_provisioned`, `vm_create_start`, `vm_created`, `disk_transfer`, and `migration_end` (including total migration duration in seconds).

---

## Quick Start (Docker Compose)

Start the entire CloudShift suite including the web dashboard and DB schema migrations:

```bash
docker-compose --profile dashboard up -d
```

Access the Web-Dashboard at `http://localhost:8080`.

To run only the Core Migration services (API, Conductor, Worker, Scheduler, Minion/Deployer Managers):

```bash
docker-compose up -d
```

---

## Standalone (NoAuth) Mode

For isolated deployments without Keystone authentication, enable Standalone Mode in `/etc/coriolis/api-paste.ini`:

```ini
[pipeline:coriolis-api-v1]
pipeline = request_id faultwrap noauth apiv1
```

---

## License & Credits

CloudShift is licensed under the Apache License 2.0. It is based on and extends the [Coriolis](https://github.com/cloudbase/coriolis) open-source project by Cloudbase Solutions SRL.
