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
- **Web-Based GUI**: Clean and premium responsive dashboard containerized out-of-the-box.
- **Standalone (NoAuth) Mode**: Built-in support to run without an active OpenStack Keystone instance.

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
