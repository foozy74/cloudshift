# C4 System Context Diagram

This diagram displays the high-level boundaries of the CloudShift migration platform, showing the primary users and external systems it interacts with.

```mermaid
C4Context
  title System Context Diagram - CloudShift Migration Engine

  Person(admin, "Administrator", "System administrator running VM migrations, managing mappings, and monitoring progress.")
  
  System(cloudshift, "CloudShift", "Enterprise Workload Migration as a Service. Manages replication, disk conversion, and OS morphing.")

  System_Ext(vsphere, "VMware vSphere", "Source hypervisor system. CloudShift exports virtual machine disks and metadata from it.")
  System_Ext(olvm, "Oracle OLVM / oVirt", "Destination hypervisor environment. CloudShift imports disks, configures storage mapping, and provisions target VMs.")
  System_Ext(hyperv, "Microsoft Hyper-V", "Destination hypervisor. CloudShift deploys migrated VMs directly using WinRM/PowerShell.")
  System_Ext(keystone, "OpenStack Keystone", "Optional external authentication provider. Houses Barbican secrets client.")

  Rel(admin, cloudshift, "Configures endpoints, schedules transfers, and runs migrations via Web-Dashboard / API")
  
  Rel(cloudshift, vsphere, "Reads VM metadata and replicates virtual disks", "HTTPS / vSphere Web API")
  Rel(cloudshift, olvm, "Provisions target VMs and attaches migrated disks", "HTTPS / oVirt SDK")
  Rel(cloudshift, hyperv, "Imports virtual disks and configures VM properties", "WinRM / PowerShell")
  Rel(cloudshift, keystone, "Authenticates sessions and retrieves secrets (Barbican)", "HTTPS / OpenStack API")
```

## Relationships Description

1. **Administrator to CloudShift**: Communicates with the Control Plane using standard HTTP request payloads to manage endpoints, scenario mappings, and view active transfer executions.
2. **CloudShift to VMware vSphere**: Performs read-only queries to extract virtual machine definitions (CPU, RAM, NICs) and streams disk snapshots during replication.
3. **CloudShift to Oracle OLVM**: Authenticates with oVirt Engine, creates disk entities on target storage domains, uploads virtual disk layers, and spawns temporary minion VMs to process block/file adjustments.
4. **CloudShift to Microsoft Hyper-V**: Establishes secure WinRM sessions to run PowerShell scripts on the host to create VHDX files, configure virtual switches, and register imported VMs.
