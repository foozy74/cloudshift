# C4 Dynamic Flow: Automated Network and VNIC Profile Provisioning

This Dynamic diagram illustrates the flow of automated logical network and VNIC profile creation in Oracle OLVM during a migration import task.

```mermaid
C4Dynamic
  title Dynamic Flow - Automated Network and VNIC Profile Provisioning on OLVM

  System_Ext(vmware, "VMware vSphere", "Source hypervisor")
  Container(worker, "Worker (coriolis-worker)", "Python", "Executes import/export tasks")
  System_Ext(olvm, "Oracle OLVM / oVirt", "Target hypervisor engine")
  ContainerDb(logs_fs, "Migration Logs", "Filesystem", "per-migration log file")

  Rel(worker, vmware, "1. Read replica instance info & extract NIC VLAN IDs", "pyvmomi / SOAP")
  Rel(worker, worker, "2. Check target_environment mapping for NIC network name", "In-Memory")
  
  Rel(worker, olvm, "3. Query existing logical networks by name in Datacenter", "REST API")
  
  Rel(worker, olvm, "4a. [If Network Exists with Different VLAN] Abort migration with InvalidInput error", "REST API")
  Rel(worker, logs_fs, "4b. [If Aborted] Log migration failure event", "JSON-Lines File")
  
  Rel(worker, olvm, "5a. [If Network does not exist] Create logical network with VLAN ID", "REST API")
  Rel(worker, olvm, "5b. Attach new network to Datacenter & Cluster", "REST API")
  Rel(worker, olvm, "5c. Create VNIC Profile for the network", "REST API")
  
  Rel(worker, logs_fs, "6. Log 'network_provisioned' event", "JSON-Lines File")
  Rel(worker, olvm, "7. Create VM and bind NIC to resolved/created VNIC profile", "REST API")
  Rel(worker, logs_fs, "8. Log VM creation, disk transfer, and final duration", "JSON-Lines File")
```

## Detail Flow Description

1. **VLAN Extraction**: During the VMware export phase, the `coriolis-worker` calls the vCenter SOAP API via `pyvmomi` to extract the network name and VLAN-ID for each virtual network interface card (NIC) attached to the source VM.
2. **Explicit Override Check**: Before performing auto-provisioning, the worker checks if the source network is explicitly mapped in the migration's `network_map` destination payload. If it is mapped, the auto-provisioning logic is bypassed.
3. **OLVM Network Lookup**: The worker queries the oVirt REST API to check if a logical network matching the source network name already exists in the destination Datacenter.
4. **VLAN Conflict Detection**: 
   - If the network exists but its VLAN-ID differs from the source VM network, the migration is **aborted immediately** with an `InvalidInput` exception. 
   - The failure event is logged to the per-migration log file inside `/var/log/coriolis/migrations/` and the task terminates to prevent network mismatches.
5. **Auto-Provisioning**:
   - If the network does not exist, the worker creates a logical network in OLVM with the matching VLAN-ID.
   - The logical network is attached to the target Datacenter and Cluster.
   - A VNIC profile is created under that logical network, inheriting the network's name.
6. **Logging and VM binding**:
   - A `network_provisioned` event is logged.
   - The worker creates the target VM and binds the NIC to the newly provisioned or existing VNIC profile.
   - Migration continues and records execution durations for VM creation, disk transfer, and final migration status.
