# CloudShift

> **Workload Migration as a Service — by [thesolution.at](https://cloudshift.thesolution.at)**

CloudShift is a production-ready, enterprise-grade migration engine designed to automate the replication, OS adaptation, and deployment of virtual machines across heterogeneous virtualization platforms and hypervisors.

Originally derived from and fully compatible with the OpenStack-based [Coriolis](https://github.com/cloudbase/coriolis) architecture, CloudShift provides native support for **VMware vSphere**, **Oracle OLVM / oVirt**, **Microsoft Hyper-V**, and **Proxmox VE** with bi-directional migration capabilities, fine-grained Role-Based Access Control (RBAC), and enterprise LDAPS / Active Directory integration.

---

## Key Features

- **Multi-Hypervisor Support**:
  - **VMware vSphere** (Export & Import)
  - **Oracle OLVM / oVirt** (Import & Export with dynamic block/file storage allocation)
  - **Microsoft Hyper-V** (Direct WinRM / PowerShell import with Gen1 & Gen2 VM support)
  - **Proxmox VE** (Import via Proxmox REST API with QEMU / KVM target deployment)
- **Incremental Replication**: Live, block-level incremental disk synchronization minimizing guest downtime before cutover.
- **Automated OS Morphing**: Automatic injection and reconfiguration of hypervisor drivers (KVM VirtIO, Hyper-V Integration Services, LIS), network interfaces, fstab, bootloaders (GRUB / UEFI), and cloud-init.
- **Enterprise Authentication & RBAC**:
  - Native **JWT (JSON Web Token)** authentication over HTTP Bearer headers.
  - **Local User Backend** (`/etc/coriolis/users.yaml`) with salted PBKDF2 and bcrypt password hashing.
  - **LDAPS (Active Directory / OpenLDAP)** over secure TLS/SSL (Port 636) with automatic group-to-role mapping via `memberOf`.
  - **Hybrid Authentication Strategy**: Fallback to LDAPS if user is not found locally, guaranteeing high availability even during domain outages.
  - **Role-Based Access Control (RBAC)** in `policy.yaml`: Enforces permissions for `admin`, `operator`, and `viewer` roles across the REST API and Dashboard.
- **Network Auto-Provisioning**: Automatically extracts VLAN-IDs from VMware Distributed Portgroups and provisions matching logical networks and VNIC profiles on Oracle OLVM.
- **VLAN Conflict Prevention**: Aborts migration safely if a target network already exists under the same name but with a mismatched VLAN-ID.
- **Interactive Swagger API Explorer**: Built-in Swagger UI with live API testing and JWT authorization support.
- **Modern Responsive Dashboard**: Containerized Dark-Mode web interface with real-time migration status, session management, role badges, and internationalization (DE / EN).
- **Per-Migration Logging**: Structured JSON-Lines logs capturing granular step milestones and end-to-end migration duration metrics.

---

## Supported Migration Paths

| Source Hypervisor (Origin) | Target Platform (Destination) | Features |
| :--- | :--- | :--- |
| **VMware vSphere** | **Oracle OLVM / oVirt** | Incremental sync, network auto-provisioning, block/file storage, OS morphing |
| **VMware vSphere** | **Microsoft Hyper-V** | WinRM connection, Gen1/Gen2 VMs, vSwitch binding, Hyper-V Integration Services |
| **VMware vSphere** | **Proxmox VE** | Proxmox API integration, QEMU guest agent, VirtIO storage & network |
| **Oracle OLVM / oVirt** | **VMware vSphere** | Reverse migration / rollback capability |

---

## Quick Start (Docker Compose)

The entire CloudShift stack can be deployed with Docker and Docker Compose.

### 1. Start the Complete Stack (Core Services + Dashboard)

```bash
docker-compose --profile dashboard up -d
```

### 2. Service Endpoints

Once started, the services are available at:

| Service | URL | Description |
| :--- | :--- | :--- |
| **Web Dashboard** | `http://localhost:8080` | Modern Web UI for migrations, endpoints, and monitoring |
| **Swagger UI** | `http://localhost:8080/dashboard/swagger.html` | Interactive OpenAPI / Swagger API explorer |
| **Coriolis REST API** | `http://localhost:7667` | Core REST API endpoint |

### 3. Preconfigured Login Accounts

The default configuration includes three local accounts in `/etc/coriolis/users.yaml`:

| Username | Role | Permissions |
| :--- | :--- | :--- |
| `admin` | `admin` | Full control: manage endpoints, jobs, system config, users, and services |
| `operator` | `operator` | Operational control: create, edit, run, cancel, and deploy migrations |
| `viewer` | `viewer` | Read-only: inspect migrations, endpoints, logs, and services (UI action-safe) |

> [!IMPORTANT]
> Change default passwords before deploying to production environments by updating `/etc/coriolis/users.yaml` or using the Configuration API.

---

## Authentication & Authorization (RBAC)

CloudShift supports modern, secure token authentication directly out-of-the-box without requiring OpenStack Keystone.

### Authentication Flow
1. **Login Request**: Send credentials to `POST /v1/auth/login`:
   ```bash
   curl -X POST http://localhost:7667/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "<your-password>"}'
   ```
   **Response**:
   ```json
   {
     "token": "<jwt-token>",
     "user": {
       "username": "admin",
       "display_name": "System Administrator",
       "roles": ["admin"],
       "auth_backend": "local"
     },
     "expires_in": 86400
   }
   ```

2. **Authenticated API Calls**: Pass the returned JWT in the `Authorization` header:
   ```bash
   curl -H "Authorization: Bearer <jwt-token>" \
     http://localhost:7667/v1/endpoints
   ```

3. **Current User Profile**:
   ```bash
   curl -H "Authorization: Bearer <jwt-token>" \
     http://localhost:7667/v1/auth/me
   ```

### LDAPS / Active Directory Integration

To enable LDAPS authentication, edit `/etc/coriolis/coriolis.conf`:

```ini
[auth]
strategy = hybrid
token_secret = your-secure-random-secret-key-min-32-chars
token_expiration_seconds = 86400

[ldap]
url = ldaps://dc01.corp.example.com:636
bind_dn = CN=svc-coriolis,OU=ServiceAccounts,DC=corp,DC=example,DC=com
bind_password = SecretServicePassword!
user_search_base = OU=Users,DC=corp,DC=example,DC=com
user_search_filter = (&(objectClass=user)(sAMAccountName={username}))
group_search_base = OU=Groups,DC=corp,DC=example,DC=com
insecure = false
ca_cert_file = /etc/coriolis/ca.crt

# Map Active Directory security groups to CloudShift roles:
role_mapping = CN=CloudShift-Admins,OU=Groups,DC=corp,DC=example,DC=com:admin,CN=CloudShift-Operators,OU=Groups,DC=corp,DC=example,DC=com:operator,CN=Domain Users,CN=Users,DC=corp,DC=example,DC=com:viewer
```

### WSGI Pipelines

The authentication filter is defined in `/etc/coriolis/api-paste.ini`:

```ini
# Recommended default: TokenAuth (JWT + Local / LDAPS + RBAC)
[pipeline:coriolis-api-v1]
pipeline = request_id faultwrap tokenauth apiv1

# Standalone unauthenticated development mode:
# pipeline = request_id faultwrap noauth apiv1

# Legacy OpenStack Keystone mode:
# pipeline = request_id faultwrap authtoken apiv1
```

---

## Configuration API

CloudShift allows authorized administrators to inspect and modify configuration files dynamically through the REST API:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/v1/configs` | List editable config files |
| `GET` | `/v1/configs/{config_file}` | Read content of `coriolis.conf`, `policy.yaml`, `users.yaml`, or `api-paste.ini` |
| `PUT` | `/v1/configs/{config_file}` | Update configuration content (`admin` role required) |

---

## Per-Migration Logging & Metrics

Detailed migration executions are stored in structured JSON-Lines format:
- **Default Path**: `/var/log/coriolis/migrations/<instance_name>_<timestamp>.log`
- **Configurable**: Via `olvm.migration_log_dir` in `coriolis.conf`.
- **Logged Milestones**:
  - `migration_start`: Initial job initiation timestamp
  - `network_provisioned`: Logical network creation and VLAN binding
  - `vm_create_start` / `vm_created`: Target VM shell definition
  - `disk_transfer`: Storage volume mapping and block replication
  - `migration_end`: Completion state and `duration_seconds` total runtime metric.

---

## Architecture

```
                                  +-----------------------+
                                  |   Web Dashboard &     |
                                  |   Swagger Explorer    |
                                  |     (Port 8080)       |
                                  +-----------+-----------+
                                              |
                                              | REST + JWT Bearer
                                              v
+------------------------+        +-----------------------+        +------------------------+
|   Local Users DB       | <----> |     Coriolis API      | <----> |   LDAPS / Active       |
| (/etc/coriolis/users)  |        |     (Port 7667)       |        |   Directory (Port 636) |
+------------------------+        +-----------+-----------+        +------------------------+
                                              |
                                              | RPC / oslo.messaging
                                              v
                                  +-----------------------+
                                  |  RabbitMQ Message Bus |
                                  +-----------+-----------+
                                              |
                   +--------------------------+--------------------------+
                   |                          |                          |
                   v                          v                          v
        +--------------------+     +--------------------+     +--------------------+
        | Coriolis Conductor |     |  Coriolis Worker   |     | Coriolis Scheduler |
        +--------------------+     +--------------------+     +--------------------+
                   |                          |                          |
                   +--------------------------+--------------------------+
                                              |
                                              v
               +-------------------------------------------------------------+
               |                    Hypervisor Providers                     |
               |  VMware vSphere  |  Oracle OLVM  |  Hyper-V  |  Proxmox VE  |
               +-------------------------------------------------------------+
```

---

## License & Credits

CloudShift is licensed under the **Apache License 2.0**.
Based on and extends the [Coriolis](https://github.com/cloudbase/coriolis) project developed by Cloudbase Solutions SRL. Developed and maintained by [thesolution.at](https://cloudshift.thesolution.at).
