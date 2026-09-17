# VMware vSphere → Oracle OLVM Migration — Requirements & Prerequisites

## 1. Source Platform: VMware vSphere 8.x

| Requirement | Details |
|---|---|
| vCenter URL | `https://vc-mgc.sdn.it.internal/` |
| vCenter Version | 8.x with ESXi 8.x Hosts |
| Authentication | vCenter SSO (Administrator or at least Read-Only on VMs + Datastores) |
| API Access | VMware vSphere Web Services SDK (SOAP) via `pyvmomi` Python library |
| Automated HotAdd | Automated disk attach/detach to worker VM `sb-v2v` via vCenter API |
| Discovered VMs | Linux (Oracle Linux, RHEL, CentOS, SUSE, Debian, Ubuntu) and Windows Server |
| Disk Format | VMDK (Thin / Thick provisioned) |
| Networking | Port Groups / Distributed Port Groups |
| Datastores | VMFS, NFS, vSAN |

### Required Credentials (Source)
- vCenter SSO Username + Password
- Worker VM SSH Credentials / Key (`sb-v2v`)
- Optional: Barbican Secret Storage for secure credential caching

---

## 2. Target Platform: Oracle OLVM 4.5 (oVirt-based)

| Requirement | Details |
|---|---|
| oVirt Engine URL | `https://sb-ovirt.sdn.it.internal/ovirt-engine/` |
| Version | OLVM 4.5 (based on oVirt 4.5) |
| Authentication | oVirt SSO (`admin@internal` or Active Directory / LDAP domain) |
| API Access | oVirt REST API v4 via `ovirt-engine-sdk-python` |
| Cluster CPU Type | **Minimum `x86-64-v3`** (AVX/AVX2 support, e.g. Intel Skylake/CascadeLake/IceLake or AMD EPYC) |
| Target Disk Format | RAW or QCOW2 (KVM supports both; sparse enabled for thin provisioning) |
| Networking | oVirt Logical Networks / VNIC Profiles |
| Storage Domains | NFS, iSCSI, FC, GlusterFS |

### Required Credentials (Target)
- oVirt Admin Username + Password
- oVirt Engine CA Certificate (PEM format for TLS verification or `insecure: true`)
- SSH Key for Minion VM communication

---

## 3. Coriolis Control Plane Server (`sb-v2v`)

| Requirement | Details |
|---|---|
| Operating System | Oracle Linux 8/9, RHEL 8/9, or Ubuntu 22.04+ |
| Container Runtime | Podman or Docker (via `docker-compose`) |
| Python Runtime | Python 3.11+ |
| Database | MariaDB 10.x |
| Messaging | RabbitMQ 3.x |
| Storage | 50 GB+ for temporary container logs and image caches |
| Network Connectivity | Direct connectivity to vCenter (443/tcp), oVirt Engine (443/tcp), and OLVM Minions (6677/tcp, 4433/tcp) |
| Proxy Bypass | Internal subnets (`172.23.0.0/16`, `localhost`, `127.0.0.1`) configured in `NO_PROXY` / `no_proxy` |

### Coriolis Services

| Service | Port | Role |
|---|---|---|
| `coriolis-api` | 7667 | REST API Surface |
| `coriolis-conductor` | — | Workflow Orchestration (Messaging) |
| `coriolis-worker` | — | Task Execution: HotAdd, Replicator, OS Morphing |
| `coriolis-scheduler` | — | Scheduled Tasks (Messaging) |
| `coriolis-minion-manager` | — | Minion Lifecycle and Allocation |
| `coriolis-deployer-manager` | — | Deployment Pipelines |
| `coriolis-transfer-cron` | — | Cron-driven Transfer Triggers |

---

## 4. Worker & Minion Infrastructure (Target KVM)

| Requirement | Details |
|---|---|
| Minion Template | Oracle Linux 8/9 minimal cloud image with cloud-init (e.g. `template-sb-Minion`) |
| Minion Specifications | Minimum 2 vCPUs, 4 GB RAM, 20 GB Boot Disk |
| CPU Compatibility | Virtual CPU must expose at least **`x86-64-v3`** (AVX2 instructions) to prevent glibc aborts in modern guest OS |
| Minion Binaries | `coriolis-writer` Binary, `coriolis-replicator` Binary |
| Pre-installed Packages | **sshd** (for Coriolis SSH orchestration)<br>**qemu-guest-agent** (Essential: required by OLVM to detect Minion IP)<br>**cloud-init** (Network configuration and SSH authorized keys)<br>**lvm2** (LVM metadata management for guest disks)<br>**psmisc** (`fuser`/`killall` tools for mount management)<br>**dm-mod** Kernel module |
| Minion Networking | Direct routing to Coriolis server (port 7667) and source replicator (port 4433/6677) |

---

## 5. Pre-Migration Checklist

### Networking
- [ ] Coriolis host can reach vCenter (`vc-mgc.sdn.it.internal:443`)
- [ ] Coriolis host can reach ESXi hosts (Port 902)
- [ ] Coriolis host can reach oVirt Engine (`sb-ovirt.sdn.it.internal:443`)
- [ ] Coriolis host can reach RabbitMQ (Port 5672)
- [ ] Minion VMs can reach Coriolis server (Ports 4433, 6677, 7667)
- [ ] Proxy bypass (`NO_PROXY`) active for all internal IP ranges

### Credentials & Access
- [ ] vCenter Administrator or migration service account active
- [ ] oVirt Engine Administrator account active
- [ ] SSH key for Minion VMs configured in `coriolis.conf` (`~/.ssh`)

### Target Platform (OLVM)
- [ ] Target cluster has sufficient vCPU and RAM capacity
- [ ] Storage domain has adequate free space (Total source disk allocations + overhead)
- [ ] Target logical networks and VNIC profiles configured
- [ ] Cluster CPU compatibility set to modern level (`x86-64-v3` or higher)

### Source Platform (vSphere)
- [ ] VMware Tools running on source VMs (for clean `ShutdownGuest` cutover)
- [ ] Source VM disks accessible (no locked snapshots or unreadable VMDKs)
- [ ] Source VM guest OS supported by Coriolis OS morphing

### Coriolis Stack
- [ ] Database schema upgraded (`coriolis-dbsync`)
- [ ] RabbitMQ healthy
- [ ] All Coriolis containers operational in `podman ps`
- [ ] VMware and OLVM providers successfully registered in worker logs
