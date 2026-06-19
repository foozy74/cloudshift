# C4 System Context Diagram

This System Context diagram provides a high-level overview of the CloudShift (Coriolis) migration engine, its users, and the external virtualization environments it integrates with.

```mermaid
C4Context
  title System Context diagram for CloudShift

  Person(admin, "Migration Administrator", "Enterprise IT Operator or Consultant managing the VM migration process")
  
  System(cloudshift, "CloudShift (Coriolis)", "Stateless, Oslo-based migration orchestrator that replicates VM disks and adapts operating systems for target hypervisors.")

  System_Ext(vmware, "VMware vSphere", "Source virtualization platform hosting virtual machines, templates, storage, and networking configurations.")
  
  System_Ext(olvm, "Oracle OLVM / oVirt", "Target virtualization platform where migrated workloads are deployed as VMs.")
  
  System_Ext(hyperv, "Microsoft Hyper-V", "Target virtualization platform where migrated workloads are deployed via WinRM.")

  Rel(admin, cloudshift, "Configures endpoints, triggers, and monitors migration jobs", "Web Dashboard / REST API / CLI")
  
  Rel(cloudshift, vmware, "Exports VM configuration, metadata, and disk data", "vSphere Web Services SDK (SOAP)")
  Rel(cloudshift, olvm, "Imports VM configuration, provisions networks, and uploads VM disks", "oVirt REST API v4 / KVM SSH")
  Rel(cloudshift, hyperv, "Imports VM configuration and deploys VMs", "WinRM / PowerShell")
```

## Key Interactions

1. **Migration Administrator**: Interacts with CloudShift via the Web Dashboard, REST API, or CLI to define connection secrets (vCenter/OLVM/Hyper-V credentials), map networks/storage, start migration jobs, and monitor replication progress.
2. **VMware vSphere (Source)**: CloudShift connects to the vCenter API to query VM properties, extract network details (including VLAN-IDs), and read raw disk data from ESXi datastores.
3. **Oracle OLVM / oVirt (Destination)**: CloudShift connects to the oVirt Engine API to define virtual machines, provision logical networks and VNIC profiles, and write disk data to destination storage domains.
4. **Microsoft Hyper-V (Destination)**: CloudShift connects to Hyper-V hosts using secure WinRM connections to construct target VMs, attach converted disks, and configure hypervisor settings.
