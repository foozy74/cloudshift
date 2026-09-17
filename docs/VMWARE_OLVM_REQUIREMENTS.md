# VMware vSphere → Oracle OLVM Migration — Requirements

## 1 Source Platform: VMware vSphere 8.x

| Anforderung | Details |
|---|---|
| vCenter URL | `https://vc-mgc.sdn.it.internal/` |
| vCenter Version | 8.x mit ESXi 8.x Hosts |
| Authentifizierung | vCenter SSO (Admin oder mind. Read-Only auf VMs + Datastores) |
| API-Zugriff | VMware vSphere Web Services SDK (SOAP) via `pyvmomi` Python Library |
| SSH-Zugriff | Auf ESXi Hosts für temporäre Worker-VM und Replicator-Deployment |
| VMs im Bestand | Linux (Oracle Linux, RHEL, CentOS, SUSE, Debian, Ubuntu) und Windows |
| Disk-Format | VMDK (Thin/Thick provisioned) |
| Netzwerke | Port Groups / Distributed Port Groups |
| Datastores | VMFS, NFS, vSAN |

### Benötigte Credentials (Source)

- vCenter SSO Benutzername + Passwort
- ESXi Host SSH Key oder Root-Passwort (für Worker-VM Deployment)
- Optional: Barbican Secret zur Speicherung der Credentials

---

## 2 Target Platform: Oracle OLVM 4.5 (oVirt-basiert)

| Anforderung | Details |
|---|---|
| oVirt Engine URL | `https://sb-ovirt.sdn.it.internal/ovirt-engine/` |
| Version | OLVM 4.5 (basiert auf oVirt 4.5) |
| Authentifizierung | oVirt SSO (`admin@internal` oder LDAP-Domain) |
| API-Zugriff | oVirt REST API v4 via `ovirt-engine-sdk-python` |
| SSH-Zugriff | Auf KVM Hosts für Minion-VM Verwaltung |
| Ziel-Disk-Format | raw oder qcow2 (KVM unterstützt beide) |
| Netzwerke | oVirt Logical Networks |
| Storage Domains | NFS, iSCSI, FC, GlusterFS |

### Benötigte Credentials (Target)

- oVirt Admin Benutzername + Passwort (+ Profil/Domain)
- oVirt Engine CA Zertifikat (PEM) für SSL-Verbindung
- KVM Host SSH Key (für Minion-VM Verwaltung)

---

## 3 Coriolis Server

| Anforderung | Details |
|---|---|
| Betriebssystem | Ubuntu 22.04+, Oracle Linux 8/9 oder RHEL 8/9 |
| Python | 3.10+ |
| Datenbank | MariaDB 10.x |
| Messaging | RabbitMQ 3.x |
| Speicher | 50 GB+ für temporäre Disk-Caches und Logs |
| Netzwerk | Erreichbarkeit zu vCenter (443/tcp), ESXi (22/tcp, 902/tcp), oVirt Engine (443/tcp), KVM Hosts (22/tcp) |
| Minion-Kommunikation | Port 6677/tcp für Backup Writer zwischen Source- und Target-Minion |
| Client | `python-coriolisclient` (von GitHub: `python-coriolisclient`) |

### Coriolis Services

| Service | Port | Rolle |
|---|---|---|
| `coriolis-api` | 7667 | REST API |
| `coriolis-conductor` | — | Orchestrierung (Messaging) |
| `coriolis-worker` | — | Task-Ausführung (Messaging) |
| `coriolis-scheduler` | — | Task-Planung (Messaging) |
| `coriolis-minion-manager` | — | Minion Pool Management (Messaging) |
| `coriolis-deployer-manager` | — | Deployment (Messaging) |
| `coriolis-transfer-cron` | — | Geplante Transfers (Messaging) |

---

## 4 Worker/Minion Infrastructure (auf Ziel-KVM)

| Anforderung | Details |
|---|---|
| Minion-Template | Oracle Linux 8/9 Cloud-Image mit cloud-init |
| Minion-Spezifikation | Min. 2 vCPU, 4 GB RAM, 20 GB Boot-Disk |
| CPU-Architektur | **Mindestens `x86-64-v3`** (AVX/AVX2 support, z. B. Intel Skylake/CascadeLake/IceLake oder AMD EPYC), damit moderne glibc-Binaries (Oracle Linux 9 / RHEL 9) beim OS-Morphing fehlerfrei ausgeführt werden. |
| Minion-Software | `coriolis-writer` Binary, `coriolis-replicator` Binary |
| Benötigte Pakete (Pre-installed) | **sshd** (für SSH-Verbindung von Coriolis)<br>**qemu-guest-agent** (Essentiell: wird von OLVM zur Erkennung der Minion-IP benötigt)<br>**cloud-init** (Netzwerkkonfiguration und SSH-Schlüssel)<br>**lvm2** (LVM-Verwaltung für Dateisysteme)<br>**psmisc** (Tools wie `fuser`/`killall` für Mounts)<br>**dm-mod** Kernel-Modul |
| Minion-Netzwerk | Muss Coriolis-Server (Port 7667) und Korrespondenz-Minion (Port 6677/4433) erreichen |
| Proxy-Zugriff / Repositories | Falls `lvm2` und `psmisc` nicht vorinstalliert sind, muss die Minion-VM während des OSMorphing-Setups Zugriff auf Paket-Repositories (ggf. über Proxy) haben, um diese dynamisch via `yum`/`dnf`/`zypper`/`apt-get` zu installieren. |

---

## 5 Pre-Migration Checkliste

### Netzwerk

- [ ] Coriolis-Server kann vCenter `vc-mgc.sdn.it.internal:443` erreichen
- [ ] Coriolis-Server kann ESXi Hosts (Port 22, 902) erreichen
- [ ] Coriolis-Server kann oVirt Engine `sb-ovirt.sdn.it.internal:443` erreichen
- [ ] Coriolis-Server kann KVM Hosts (Port 22) erreichen
- [ ] Coriolis kann RabbitMQ (Port 5672) erreichen
- [ ] Minions können untereinander kommunizieren (Port 6677 TCP)

### Credentials

- [ ] vCenter Administrator Account aktiv
- [ ] oVirt Engine Administrator Account aktiv
- [ ] SSH-Key für ESXi Hosts vorhanden und getestet
- [ ] SSH-Key für KVM Hosts vorhanden und getestet
- [ ] SSH-Key für Minion-VMs vorhanden

### Ziel-Plattform (OLVM)

- [ ] Ziel-Cluster hat genug CPU-Kapazität (Summe aller Quell-VM vCPUs + Overhead)
- [ ] Ziel-Cluster hat genug RAM (Summe aller Quell-VM RAM + Overhead)
- [ ] Ziel-Storage-Domain hat genug freien Speicher (Summe aller Quell-Disk-Größen + Snapshots)
- [ ] Ziel-Netzwerke/Logical Networks sind definiert
- [ ] oVirt Instance Types oder CPU-Profil konfiguriert
- [ ] DNS: Ziel-VM-Namen werden korrekt aufgelöst

### Quell-Plattform (vSphere)

- [ ] VMware Tools sind auf den Quell-VMs installiert (für sauberes Shutdown)
- [ ] Quell-VMs haben statische IPs dokumentiert (für OS-Morphing)
- [ ] Quell-VM Guest OS ist von Coriolis unterstützt (Linux: RHEL/Oracle/CentOS/Ubuntu/Debian/SUSE, Windows Server)
- [ ] Quell-VM-Disks sind zugänglich (keine verschlüsselten VMDKs ohne Schlüssel)

### Coriolis

- [ ] Provider-Liste in `coriolis.conf` korrekt konfiguriert
- [ ] Datenbank initialisiert (`coriolis-dbsync upgrade head`)
- [ ] RabbitMQ läuft und erreichbar
- [ ] Alle Coriolis-Services laufen (`coriolis-api`, `conductor`, `worker`, `scheduler`, `minion-manager`)
- [ ] Provider wurden beim Worker registriert (Worker-Log prüfen)

---