CloudShift (Coriolis)
=====================

*Workload Migration as a Service — by thesolution.at (https://cloudshift.thesolution.at)*

CloudShift is a production-ready, enterprise-grade migration engine designed to automate the replication, OS adaptation, and deployment of virtual machines across heterogeneous virtualization platforms and hypervisors.

Derived from and built upon the OpenStack-based Coriolis architecture, CloudShift provides native support for **VMware vSphere**, **Oracle OLVM / oVirt**, **Microsoft Hyper-V**, and **Proxmox VE** with bi-directional migration capabilities, fine-grained Role-Based Access Control (RBAC), and enterprise LDAPS / Active Directory integration.

Key Features
------------

- **Multi-Hypervisor Support**:
  - **VMware vSphere** (Export & Import)
  - **Oracle OLVM / oVirt** (Import & Export with dynamic block/file storage allocation)
  - **Microsoft Hyper-V** (Direct WinRM / PowerShell import with Gen1 & Gen2 VM support)
  - **Proxmox VE** (Import via Proxmox REST API with QEMU / KVM target deployment)
- **Incremental Replication**: Live, block-level incremental disk synchronization minimizing guest downtime before cutover.
- **Automated OS Morphing**: Automatic injection and reconfiguration of hypervisor drivers (KVM VirtIO, Hyper-V Integration Services, LIS), network interfaces, fstab, bootloaders (GRUB / UEFI), and cloud-init.
- **Enterprise Authentication & RBAC**:
  - Native **JWT (JSON Web Token)** authentication over HTTP Bearer headers.
  - **Local User Backend** (``/etc/coriolis/users.yaml``) with salted PBKDF2 and bcrypt password hashing.
  - **LDAPS (Active Directory / OpenLDAP)** over secure TLS/SSL (Port 636) with automatic group-to-role mapping via ``memberOf``.
  - **Hybrid Authentication Strategy**: Fallback to LDAPS if user is not found locally, guaranteeing high availability even during domain outages.
  - **Role-Based Access Control (RBAC)** in ``policy.yaml``: Enforces permissions for ``admin``, ``operator``, and ``viewer`` roles across the REST API and Dashboard.
- **Network Auto-Provisioning**: Automatically extracts VLAN-IDs from VMware Distributed Portgroups and provisions matching logical networks and VNIC profiles on Oracle OLVM.
- **VLAN Conflict Prevention**: Aborts migration safely if a target network already exists under the same name but with a mismatched VLAN-ID.
- **Interactive Swagger API Explorer**: Built-in Swagger UI with live API testing and JWT authorization support.
- **Modern Responsive Dashboard**: Containerized Dark-Mode web interface with real-time migration status, session management, role badges, and internationalization (DE / EN).
- **Per-Migration Logging**: Structured JSON-Lines logs capturing granular step milestones and end-to-end migration duration metrics.

Architecture
------------

CloudShift is architected as an asynchronous, microservice-based system utilizing OpenStack Oslo libraries and standard message brokers:

- **coriolis-api**: REST API / WSGI surface with JWT authentication, RBAC policy enforcement, and CORS support.
- **coriolis-conductor**: Orchestrates end-to-end migration pipelines, state transitions, and task dependencies using TaskFlow.
- **coriolis-worker**: Executes disk transfers, data replications, and OS morphing tasks.
- **coriolis-scheduler**: Dispatches and balances tasks across available worker nodes.
- **coriolis-minion-manager**: Manages temporary worker/minion VM pools on target virtualization platforms.
- **coriolis-deployer-manager**: Coordinates target VM deployment and hypervisor registration.
- **coriolis-transfer-cron**: Automates scheduled recurring disk synchronization.
- **Web Dashboard & Swagger UI**: Nginx-based responsive single-page web console and API documentation.

Quick Start (Docker Compose)
----------------------------

Deploy the entire CloudShift suite including the API, background services, MariaDB, RabbitMQ, and the Web Dashboard:

1. Launch All Services:
::

    docker-compose --profile dashboard up -d

2. Service URLs:

- **Web Dashboard**: ``http://localhost:8080``
- **Swagger UI**: ``http://localhost:8080/dashboard/swagger.html``
- **Coriolis REST API**: ``http://localhost:7667``

3. User Accounts:

Users and their password hashes are defined in ``docker/users.yaml`` (not tracked in git). Create it from ``docker/users.yaml.example``, which explains how to generate the hashes. Typical roles:

- ``admin``: Full system administration, endpoint management, config editing, and user management (Role: ``admin``)
- ``operator``: Operational control: create, edit, run, cancel, and deploy migrations (Role: ``operator``)
- ``viewer``: Read-only inspection mode: browse migrations, endpoints, logs, and system status (Role: ``viewer``)

Authentication & Authorization (RBAC)
-------------------------------------

JWT Token Authentication
~~~~~~~~~~~~~~~~~~~~~~~~

Authentication is handled natively without requiring Keystone.

Login:
::

    curl -X POST http://localhost:7667/v1/auth/login \
      -H "Content-Type: application/json" \
      -d '{"username": "admin", "password": "<your-password>"}'

Calling Protected APIs:
::

    curl -H "Authorization: Bearer <token>" \
      http://localhost:7667/v1/endpoints

Current User Information:
::

    curl -H "Authorization: Bearer <token>" \
      http://localhost:7667/v1/auth/me

LDAPS / Active Directory Setup
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Configure ``coriolis.conf`` under ``/etc/coriolis/coriolis.conf``:
::

    [auth]
    strategy = hybrid
    token_secret = your-secure-secret-key-change-in-production
    token_expiration_seconds = 86400

    [ldap]
    url = ldaps://dc01.corp.example.com:636
    bind_dn = CN=svc-coriolis,OU=ServiceAccounts,DC=corp,DC=example,DC=com
    bind_password = SecretPassword!
    user_search_base = OU=Users,DC=corp,DC=example,DC=com
    user_search_filter = (&(objectClass=user)(sAMAccountName={username}))
    group_search_base = OU=Groups,DC=corp,DC=example,DC=com
    insecure = false
    ca_cert_file = /etc/coriolis/ca.crt
    role_mapping = CN=CloudShift-Admins,OU=Groups,DC=corp,DC=example,DC=com:admin,CN=CloudShift-Operators,OU=Groups,DC=corp,DC=example,DC=com:operator,CN=Domain Users,CN=Users,DC=corp,DC=example,DC=com:viewer

WSGI Pipelines
~~~~~~~~~~~~~~

Configured in ``/etc/coriolis/api-paste.ini``:
::

    # Recommended: TokenAuth with JWT & Local/LDAPS RBAC
    [pipeline:coriolis-api-v1]
    pipeline = request_id faultwrap tokenauth apiv1

    # Unauthenticated Development Mode:
    # pipeline = request_id faultwrap noauth apiv1

Supported Hypervisors & Providers
---------------------------------

VMware vSphere
~~~~~~~~~~~~~~
- **Export Provider**: VM, disk, snapshot, and metadata extraction via pyVmomi.
- **Import Provider**: Full reverse migration path to import workloads back into vSphere.

Oracle OLVM / oVirt
~~~~~~~~~~~~~~~~~~~
- **Import Provider**: Creates target VMs, disks (sparse/raw), vNICs, and performs automated KVM VirtIO morphing.
- **Export Provider**: Reverse migration support to replicate OLVM workloads back to other platforms.
- **Network Auto-Provisioning**: Extracts VLAN-IDs from VMware Distributed Portgroups and provisions matching networks and VNIC profiles automatically.
- **VLAN Conflict Prevention**: Halts migration safely if a logical network exists with a conflicting VLAN-ID.

Microsoft Hyper-V
~~~~~~~~~~~~~~~~~
- **Import Provider**: Connects via WinRM (PowerShell) supporting NTLM, Kerberos, CredSSP, and Basic auth.
- **Dynamic Configuration**: Supports Gen1 and Gen2 VMs, Virtual Switch mapping, and storage path selection.
- **OS Morphing**: Injects Hyper-V Integration Services, configures network adapters, and updates boot configs.

Proxmox VE
~~~~~~~~~~
- **Import Provider**: Direct migration into Proxmox VE clusters via Proxmox REST API.
- **Storage & Network**: Configures Proxmox storage pools (ZFS, LVM-thin, Ceph, directory), VirtIO disks, and bridge networks.

Configuration API
-----------------

Authorized administrators (``admin`` role) can inspect and update configuration files live via the REST API:

- **List Configuration Files**: ``GET /v1/configs``
- **Read Configuration Content**: ``GET /v1/configs/{config_name}``
- **Update Configuration Content**: ``PUT /v1/configs/{config_name}``

Per-Migration Logging
---------------------

Structured migration logs in JSON-Lines format are automatically generated for auditing and performance analysis:

- **Default Location**: ``/var/log/coriolis/migrations/<instance_name>_<timestamp>.log``
- **Config Option**: ``olvm.migration_log_dir`` in ``/etc/coriolis/coriolis.conf``
- **Tracked Events**: ``migration_start``, ``network_provisioned``, ``vm_create_start``, ``vm_created``, ``disk_transfer``, and ``migration_end`` with total execution ``duration_seconds``.

License & Credits
-----------------

CloudShift is licensed under the **Apache License 2.0**.
Based on and extends the Coriolis open-source project by Cloudbase Solutions SRL. Developed and maintained by thesolution.at (https://cloudshift.thesolution.at).
