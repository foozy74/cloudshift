# C4 Deployment Diagram

This diagram displays the typical production deployment of the CloudShift Control Plane and its network topology relative to the source and target hypervisors.

```mermaid
C4Deployment
  title Deployment Diagram - CloudShift Control Plane Production Setup

  Deployment_Node(admin_desktop, "Administrator Workstation", "Windows/macOS") {
    Container(browser, "Web Browser", "Chrome/Firefox/Safari", "Accesses the management interface.")
  }

  Deployment_Node(control_plane_host, "Control Plane VM", "RHEL 9 / Rocky Linux 9", "Dedicated server hosting the dockerized migration engine.") {
    Deployment_Node(docker_engine, "Docker Engine", "Docker Compose Stack") {
      Container(dashboard, "cloudshift-dashboard", "nginx:alpine", "Serves static web files and acts as API proxy.", "8080")
      Container(api, "cloudshift-api", "Python 3.11-slim", "REST API gateway.", "7667")
      
      ContainerDb(db, "cloudshift-db", "mariadb:10-jammy", "Database instance.", "13306")
      ContainerQueue(rabbitmq, "cloudshift-rabbitmq", "rabbitmq:3-management", "Message broker.", "5672/15672")

      Container(conductor, "cloudshift-conductor", "Python 3.11-slim", "Workflow orchestrator.")
      Container(worker, "cloudshift-worker", "Python 3.11-slim", "Data transfer & task execution engine.")
      Container(minion_mgr, "cloudshift-minion-manager", "Python 3.11-slim", "Minion VM lifecyle control.")
      Container(deployer_mgr, "cloudshift-deployer-manager", "Python 3.11-slim", "Deployment pipeline control.")
      Container(scheduler, "cloudshift-scheduler", "Python 3.11-slim", "Task router.")
      Container(cron, "cloudshift-transfer-cron", "Python 3.11-slim", "Schedule agent.")
    }
  }

  Deployment_Node(source_datacenter, "Source Datacenter", "VMware Infrastructure") {
    Deployment_Node(vcenter_node, "vCenter Server Appliance", "Photon OS VM") {
      System(vcenter, "vSphere vCenter API", "Manages source ESXi nodes and VM inventory.")
    }
    Deployment_Node(esxi_node, "ESXi Hypervisors", "Baremetal Hosts") {
      System(esxi, "ESXi Storage", "Holds VM virtual disk snapshots.")
    }
  }

  Deployment_Node(dest_datacenter_olvm, "Destination Datacenter (KVM)", "Oracle Linux VM (OLVM) / oVirt") {
    Deployment_Node(olvm_engine, "OLVM Engine Manager", "Oracle Linux VM") {
      System(ovirt, "oVirt Engine API", "Manages destination clusters and storage domains.")
    }
    Deployment_Node(kvm_nodes, "OLVM Hypervisor Hosts", "Baremetal KVM") {
      System(kvm_hypervisor, "KVM Storage & VM pool", "Runs target VMs and temporary minion helper VMs.")
    }
  }

  Deployment_Node(dest_datacenter_hyperv, "Destination Datacenter (Hyper-V)", "Microsoft Infrastructure") {
    Deployment_Node(hyperv_host, "Hyper-V Host", "Windows Server 2022") {
      System(hyperv, "Hyper-V Hypervisor", "Runs target VMs directly.")
    }
  }

  Rel(browser, dashboard, "Accesses dashboard UI", "HTTPS / Port 8080")
  Rel(dashboard, api, "Sends backend calls", "HTTP / Port 8080 -> 7667")

  Rel(worker, vcenter, "Queries VM metadata", "HTTPS / Port 443")
  Rel(worker, esxi, "Downloads disk snapshots", "HTTPS / Port 443")
  
  Rel(worker, ovirt, "Creates empty disks & VMs", "HTTPS / Port 443")
  Rel(worker, kvm_hypervisor, "Mounts disks on helper Minion VMs for writing", "SSH / Port 22")
  Rel(worker, hyperv, "Builds target VM & morphs OS configuration", "WinRM / Port 5986")
```

## Network Considerations

1. **Firewall Allowances**:
   - The Control Plane VM must have outbound HTTPS (Port 443) access to both the VMware vCenter/ESXi hosts and the Oracle OLVM Engine.
   - Outbound SSH (Port 22) must be open from the Control Plane VM to the OLVM Hypervisor hosts (or the dynamic minion VM IPs) to mount and stream disk layers during replication.
   - Outbound WinRM (Port 5985/5986) must be allowed from the Control Plane VM to the target Microsoft Hyper-V hosts.
2. **Internal Proxying**:
   - The Nginx-based `cloudshift-dashboard` exposes port 8080 to the client web browser.
   - All REST requests to `/v1/` are dynamically proxied internally via the Docker network bridge to the `cloudshift-api` container on port 7667.
3. **Keystone & Barbican**:
   - For Keystone integration (if not in `noauth` mode), the API container requires outbound HTTPS access to the Keystone endpoint.
