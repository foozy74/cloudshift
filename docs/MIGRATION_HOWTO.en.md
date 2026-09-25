# How-To: VMware vSphere to Oracle OLVM Migration with Coriolis

This guide provides a step-by-step walkthrough for migrating virtual machines from VMware vSphere (source) to Oracle OLVM (target) using CloudShift / Coriolis running on `sb-v2v` (`172.23.219.61`).

---

## 1. Prerequisites & Preparation

### A. Network & Access Requirements
* Coriolis containers must be able to reach vCenter on port `443` and ESXi hosts on port `902`.
* Coriolis containers must be able to reach the OLVM/oVirt Engine on port `443`.
* Temporary Minion VMs on OLVM must be able to communicate with Coriolis containers over ports `6677` and `4433`.
* **Proxy Bypass:** Internal subnets (`172.23.0.0/16`) must be included in `NO_PROXY` (in `ProviderSession`, proxy redirection is automatically bypassed).

### B. Provide OLVM Minion Template
Coriolis requires a minimal OS template on the target OLVM platform to instantiate temporary worker VMs (Minions):
1. Create a minimal VM in OLVM (e.g. running Oracle Linux 8/9) with `qemu-guest-agent` installed.
2. **CPU Compatibility:** Ensure the cluster (e.g. `sb1`) or template provides a CPU model supporting at least **`x86-64-v3`** (AVX2, e.g. Intel Skylake/CascadeLake/IceLake or AMD EPYC) so modern guest operating systems (`glibc`) run seamlessly during OS morphing.
3. **SSH access for Coriolis:** Coriolis connects to the minion as `root` using an SSH key. The key is not injected via cloud-init, so it must be baked into the template:
   ```bash
   # Generate a key pair without passphrase (RSA, Ed25519 or ECDSA)
   ssh-keygen -t ed25519 -f secrets/olvm_minion_ssh_key -N ""

   # Inside the template VM: add the public key for root
   mkdir -p /root/.ssh && chmod 700 /root/.ssh
   cat olvm_minion_ssh_key.pub >> /root/.ssh/authorized_keys
   chmod 600 /root/.ssh/authorized_keys
   restorecon -Rv /root/.ssh   # set SELinux context ssh_home_t
   ```
   * `sshd -T` must report `permitrootlogin yes` (or `prohibit-password`) and `pubkeyauthentication yes`.
   * If an SSH key for root is set under "Initial Run" in OLVM, set `disable_root: 0` in `/etc/cloud/cloud.cfg`, otherwise cloud-init blocks root login.
   * The **private key** goes on the Docker host at `secrets/olvm_minion_ssh_key` (`chmod 600`, excluded via `.gitignore`). `docker-compose.yml` mounts it as a Compose secret into the worker only (`/run/secrets/olvm_minion_ssh_key`). Override the location with `OLVM_MINION_SSH_KEY_FILE`.
   * Test from the Docker host: `ssh -i secrets/olvm_minion_ssh_key -o IdentitiesOnly=yes root@<vm-ip> hostname`
4. Shut down the VM and convert it into an OLVM **Template** (e.g. named `template-sb-Minion`).
5. **Configure template name and SSH key:**
   * **Globally in `docker/coriolis.conf`:**
     ```ini
     [olvm]
     minion_template_name = template-sb-Minion
     minion_ssh_key_path = /run/secrets/olvm_minion_ssh_key
     minion_vcpus = 2
     minion_memory_mb = 4096
     ```
   * **Or per transfer in `destination_environment`:**
     ```json
     "destination_environment": {
       "cluster_id": "sb1",
       "storage_domain_id": "olvm-sb1",
       "minion_template_name": "template-sb-Minion"
     }
     ```

### C. VMware Worker VM & Automated HotAdd
On the VMware side, an existing worker VM (`sb-v2v`) serves as the data proxy. Coriolis automatically attaches the source VM's VMDK disks to this worker VM via HotAdd and reads them consistently from a temporary snapshot:
```ini
[vmware]
worker_ip = 172.23.219.61
worker_vm_name = sb-v2v
auto_attach_disks = True
worker_ssh_password = VMware.99
```

---

## 2. Step-by-Step Migration Guide

### Step 2.1: Register VMware Source Endpoint

Register your VMware vSphere environment:

```bash
curl -i -X POST "http://172.23.219.61:7667/v1/endpoints" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: fake-admin-token" \
  -d '{
    "endpoint": {
      "name": "vsphere-source",
      "type": "vmware_vsphere",
      "description": "VMware vCenter Source Environment",
      "connection_info": {
        "host": "vc-mgc.sdn.it.internal",
        "username": "administrator@vsphere.local",
        "password": "your-vcenter-password",
        "allow_untrusted": true
      }
    }
  }'
```
*Note the returned endpoint ID (`"id": "<vsphere-endpoint-uuid>"`).*

---

### Step 2.2: Register Oracle OLVM Target Endpoint

Register your Oracle OLVM environment:

```bash
curl -i -X POST "http://172.23.219.61:7667/v1/endpoints" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: fake-admin-token" \
  -d '{
    "endpoint": {
      "name": "olvm-destination",
      "type": "olvm",
      "description": "Oracle OLVM Target Environment",
      "connection_info": {
        "url": "https://sb-ovirt.sdn.it.internal/ovirt-engine/",
        "username": "admin@internal",
        "password": "your-olvm-password",
        "insecure": true
      }
    }
  }'
```
*Note the returned endpoint ID (`"id": "<olvm-endpoint-uuid>"`).*

---

### Step 2.3: Create Migration Job (Transfer)

Define the transfer job with cluster, storage domain, and network mappings:

```bash
curl -i -X POST "http://172.23.219.61:7667/v1/transfers" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: fake-admin-token" \
  -d '{
    "transfer": {
      "name": "migration-sbl13155t",
      "scenario": "replica",
      "origin_endpoint_id": "<vsphere-endpoint-uuid>",
      "destination_endpoint_id": "<olvm-endpoint-uuid>",
      "instances": ["sbl13155t"],
      "source_environment": {
        "shutdown_instances": true
      },
      "destination_environment": {
        "cluster_id": "sb1",
        "storage_domain_id": "olvm-sb1",
        "network_map": {
          "sb_3tier_mgc_appl": "sb_3tier_appl"
        }
      }
    }
  }'
```
*Note the transfer ID (`"id": "<transfer-uuid>"`).*

---

### Step 2.4: Trigger Initial Replication (Full Sync)

Starts the baseline disk replication while the source VM remains active and online:

```bash
curl -i -X POST "http://172.23.219.61:7667/v1/transfers/<transfer-uuid>/executions" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: fake-admin-token" \
  -d '{"execution": {}}'
```

---

### Step 2.5: Monitor Transfer Progress

```bash
curl -s "http://172.23.219.61:7667/v1/transfers/<transfer-uuid>" \
  -H "X-Auth-Token: fake-admin-token" | python3 -m json.tool
```
Once replication completes, the execution status switches to `COMPLETED`.

---

### Step 2.6: Final Cutover (Shutdown, Delta Sync & OS Morphing)

Execute the cutover during the maintenance window with automated source VM shutdown and target deployment:

```bash
curl -i -X POST "http://172.23.219.61:7667/v1/transfers/<transfer-uuid>/executions" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: fake-admin-token" \
  -d '{
    "execution": {
      "shutdown_instances": true,
      "auto_deploy": true
    }
  }'
```

**Automated Cutover Actions:**
1. Gracefully shuts down the source VM in vCenter via `ShutdownGuest()`.
2. Syncs remaining disk deltas in seconds.
3. Launches temporary OS morphing minion:
   - Installs `qemu-guest-agent`.
   - Removes `open-vm-tools`.
   - Injects KVM VirtIO drivers into `initramfs`.
   - Reconfigures networking & GRUB bootloader.
4. Attaches disks to target VM on OLVM (named `<VM>_<DISK_ID>`) and powers it on.

---

## 3. Diagnostics & Troubleshooting

Inspect container logs directly on `sb-v2v`:

```bash
# Worker logs (Data transfer, HotAdd, and OS morphing)
podman logs -f coriolis-worker

# Conductor logs (Workflow orchestration)
podman logs -f coriolis-conductor

# API logs (REST requests and responses)
podman logs -f coriolis-api
```
