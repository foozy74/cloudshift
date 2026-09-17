# Coriolis Command-Line Interface (CLI) How-To

This guide provides a comprehensive walkthrough for installing, configuring, and using the Coriolis CLI client (`python-coriolisclient`) to orchestrate virtual machine migrations.

---

## 1. Installation

The Coriolis CLI is provided by the `python-coriolisclient` package. You can install it directly from GitHub using `pip`:

```bash
pip install git+https://github.com/cloudbase/python-coriolisclient.git
```

This installs the `coriolis` executable into your environment. To verify the installation, check the help menu:

```bash
coriolis --help
```

---

## 2. Authentication & Configuration

The Coriolis client communicates with the Coriolis API (`coriolis-api`). Depending on your deployment mode (Keystone-authenticated or Standalone/NoAuth mode), you must configure the client accordingly.

### Option A: Standalone (NoAuth) Mode
If Coriolis is running in standalone mode (where requests bypass Keystone authentication):
1. Use the `--no-auth` (or `-N`) flag.
2. Specify the Coriolis endpoint URL using the `--endpoint` (or `-E`) flag or the `CORIOLIS_ENDPOINT` environment variable.

```bash
export CORIOLIS_ENDPOINT="http://<coriolis-api-host>:7667/v1"

# Verify connection
coriolis -N provider list
```

### Option B: Keystone Authentication Mode
In standard OpenStack-style environments, Coriolis leverages Keystone for tenant isolation and authentication. Define the standard OpenStack environment variables:

```bash
export OS_AUTH_URL="http://<keystone-host>:5000/v3"
export OS_USERNAME="admin"
export OS_PASSWORD="your-secure-password"
export OS_PROJECT_NAME="admin"
export OS_USER_DOMAIN_NAME="Default"
export OS_PROJECT_DOMAIN_NAME="Default"
export OS_IDENTITY_API_VERSION=3
export CORIOLIS_ENDPOINT="http://<coriolis-api-host>:7667/v1"

# Verify connection
coriolis provider list
```

---

## 3. Managing Endpoints

Endpoints represent the source and destination virtualization platforms. Coriolis supports `vmware_vsphere` (source/export), `olvm` (destination/import), and `hyperv` (destination/import).

### 3.1 Registering a VMware vSphere Endpoint (Source)
Create a JSON file (e.g., `vsphere_conn.json`) containing the connection parameters:

```json
{
  "host": "vcenter.domain.local",
  "username": "administrator@vsphere.local",
  "password": "vcenter-password",
  "allow_untrusted": true
}
```

Register the endpoint via the CLI:
```bash
coriolis -N endpoint create \
  --name "vsphere-source" \
  --provider "vmware_vsphere" \
  --description "Production vCenter Source" \
  --connection-file vsphere_conn.json
```

### 3.2 Registering an Oracle OLVM / oVirt Endpoint (Destination)
Create a JSON file (e.g., `olvm_conn.json`) containing the connection parameters:

```json
{
  "url": "https://olvm-engine.domain.local/ovirt-engine/",
  "username": "admin@internal",
  "password": "olvm-password",
  "insecure": true
}
```

Register the endpoint via the CLI:
```bash
coriolis -N endpoint create \
  --name "olvm-target" \
  --provider "olvm" \
  --description "Oracle OLVM Destination" \
  --connection-file olvm_conn.json
```

### 3.3 Registering a Microsoft Hyper-V Endpoint (Destination)
Create a JSON file (e.g., `hyperv_conn.json`) containing the connection parameters:

```json
{
  "host": "hyperv-host.domain.local",
  "username": "administrator",
  "password": "hyperv-password",
  "transport": "ntlm"
}
```

Register the endpoint via the CLI:
```bash
coriolis -N endpoint create \
  --name "hyperv-target" \
  --provider "hyperv" \
  --description "Hyper-V Destination Host" \
  --connection-file hyperv_conn.json
```

### 3.4 Validating and Querying Endpoints
List registered endpoints:
```bash
coriolis -N endpoint list
```

Validate connectivity to a specific endpoint:
```bash
coriolis -N endpoint validate connection <endpoint-uuid>
```

Query information directly from the endpoint inventory:
```bash
# List virtual machines on the source endpoint
coriolis -N endpoint instance list <vsphere-endpoint-uuid>

# List logical networks on the destination endpoint
coriolis -N endpoint network list <olvm-endpoint-uuid>

# List storage domains/backends on the destination endpoint
coriolis -N endpoint storage list <olvm-endpoint-uuid>
```

---

## 4. Orchestrating Migrations

A migration is a multi-step orchestration job represented by a **Transfer**. Disks are copied while the source VM is running (Replication), followed by one or more incremental syncs, and finally a Cutover (Deployment) where the source VM is shut down, a final differential sync is performed, target resources are configured, and OS morphing is executed.

### 4.1 Step 1: Create a Migration Job (Transfer)

To define a transfer, you must specify:
* `--origin-endpoint`: The source endpoint UUID
* `--destination-endpoint`: The target endpoint UUID
* `--instance`: The name of the VM to migrate (can be specified multiple times for bulk migrations)
* `--scenario`: Set to `replica` (retains disks and supports incremental synchronization)
* `--network-map`: Mapping of source networks/port groups to destination networks
* `--destination-environment`: Storage domains, target cluster and minion template
* `--source-environment`: VMware worker VM and automated HotAdd options

Create a destination environment JSON file (e.g., `dest_env.json`):
```json
{
  "cluster_name": "Default",
  "storage_domain": "data",
  "minion_template_name": "sb-minion-template"
}
```

Create a source environment JSON file (e.g., `source_env.json`):
```json
{
  "worker_vm_name": "sb-v2v",
  "worker_ip": "172.23.219.61",
  "auto_attach_disks": true
}
```

Create a network mapping JSON file (e.g., `net_map.json`):
```json
{
  "VM Network": "ovirtmgmt"
}
```

Create the transfer job:
```bash
coriolis -N transfer create \
  --origin-endpoint "<vsphere-endpoint-uuid>" \
  --destination-endpoint "<olvm-endpoint-uuid>" \
  --instance "web-server-prod" \
  --scenario "replica" \
  --source-environment-file source_env.json \
  --destination-environment-file dest_env.json \
  --network-map-file net_map.json
```

*Note: Record the created Transfer ID (e.g. `a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6`) from the output.*

### 4.2 Step 2: Execute Initial Replication (Disk Sync)

Start the first full replication sync. This deploys temporary helper VMs (minions) and copies disk blocks without interrupting the running source VM.

```bash
coriolis -N transfer execute <transfer-uuid>
```

Monitor the progress of the execution:
```bash
# List all executions for this transfer
coriolis -N transfer execution list <transfer-uuid>

# Check details/status of the transfer
coriolis -N transfer show <transfer-uuid>
```

Wait until the execution status reaches `COMPLETED`.

### 4.3 Step 3: Run Incremental Syncs (Optional but Recommended)
To minimize downtime during final cutover, run differential syncs as the VM continues to run. Coriolis will only transfer changed disk blocks.

```bash
coriolis -N transfer execute <transfer-uuid>
```

### 4.4 Step 4: Perform the Final Cutover (Deployment)

Once you are ready for final cutover:
1. Trigger the deployment.
2. If `--dont-clone-disks` is omitted, Coriolis clones the sync target disks to preserve the transfer state, allowing rollback.
3. If OS morphing is needed (driver injecting, guest customization), keep it enabled (default behavior).

```bash
coriolis -N deployment create \
  --force \
  --dont-clone-disks \
  <transfer-uuid>
```

*Note: The `--force` flag allows deploying even if some past incremental executions failed. Use with care. To automatically shut down the source VM before the final sync during deployment, ensure the transfer was configured with source shutdown settings, or use the appropriate CLI deployment options.*

Verify the deployment status:
```bash
coriolis -N deployment list <transfer-uuid>
coriolis -N deployment show <deployment-uuid>
```

Once the status is `COMPLETED`, the VM will be powered on and running in the destination platform (e.g. Oracle OLVM or Hyper-V).

---

## 5. Troubleshooting & Logs

To diagnose issues with transfers or deployments:

1. **List and Stream Logs**:
   Retrieve the list of logs available for migrations:
   ```bash
   coriolis -N log list
   ```

2. **Server-Side Container Logs**:
   If you have shell access to the Coriolis hosting server, inspect the stdout/stderr logs of the respective microservices:
   ```bash
   # API request handling logs
   podman logs -f coriolis-api

   # Orchestration workflow engine logs
   podman logs -f coriolis-conductor

   # Worker operations (disk mirroring & copying) logs
   podman logs -f coriolis-worker

   # Helper VM pools lifecycle logs
   podman logs -f coriolis-minion-manager
   ```

3. **Per-Migration Structured Logs**:
   By default, Coriolis writes structured JSON-Lines logs for each migration containing milestone events and duration metrics:
   ```bash
   cat /var/log/coriolis/migrations/<instance_name>_<timestamp>.log
   ```
