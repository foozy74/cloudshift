# C4 Container Diagram

This diagram displays the internal container architecture of CloudShift, showing how the decoupled services communicate via RabbitMQ and read/write metadata in MariaDB.

```mermaid
C4Container
  title Container Diagram - CloudShift Control Plane

  Person(admin, "Administrator", "Interacts with the web dashboard to manage migrations.")

  System_Boundary(cloudshift_platform, "CloudShift Platform") {
    Container(dashboard, "Web Dashboard", "Nginx & Vanilla JS", "Serves the admin web portal and proxies `/v1/` requests to the API.", "8080")
    Container(api, "API Service", "Python (Paste/Cheroot)", "Exposes the REST API, handles endpoint registration, and queues tasks.", "7667")
    
    ContainerDb(db, "Metadata Database", "MariaDB 10", "Stores endpoint details, migration metadata, execution logs, and scheduling records.", "13306")
    ContainerQueue(rabbitmq, "Message Broker", "RabbitMQ 3", "Enables asynchronous communication between API, Conductor, Scheduler, and Worker services.", "5672")

    Container(conductor, "Conductor", "Python (TaskFlow)", "Coordinates the high-level workflow pipelines (Migration, Replication, OS-Morphing).")
    Container(scheduler, "Scheduler", "Python", "Routes worker tasks to appropriate execution nodes based on load and region specs.")
    Container(worker, "Worker", "Python", "Runs actual data transfer, disk snapshotting, and morphing scripts.")
    Container(minion_manager, "Minion Manager", "Python", "Manages lifecycle and allocations of helper data-minion VMs.")
    Container(deployer_manager, "Deployer Manager", "Python", "Controls deployment orchestration and OS morphing triggers.")
    Container(transfer_cron, "Transfer Cron", "Python", "Triggers recurring, scheduled replication jobs.")
  }

  System_Ext(vsphere, "VMware vSphere", "Source hypervisor API.")
  System_Ext(olvm, "Oracle OLVM", "Destination hypervisor API.")
  System_Ext(hyperv, "Microsoft Hyper-V", "Destination WinRM/PowerShell.")

  Rel(admin, dashboard, "Manages migrations", "HTTPS")
  Rel(dashboard, api, "Proxies REST calls", "HTTP /v1/")
  Rel(api, db, "Reads/writes metadata", "SQL")
  Rel(api, rabbitmq, "Queues jobs & publishes events", "AMQP")
  
  Rel(conductor, rabbitmq, "Subscribes to workflows & posts task updates", "AMQP")
  Rel(scheduler, rabbitmq, "Subscribes to routing events", "AMQP")
  Rel(worker, rabbitmq, "Subscribes to transfer & morphing queues", "AMQP")
  Rel(minion_manager, rabbitmq, "Subscribes to minion pool controls", "AMQP")
  Rel(deployer_manager, rabbitmq, "Subscribes to deployment events", "AMQP")
  Rel(transfer_cron, rabbitmq, "Publishes schedule triggers", "AMQP")

  Rel(conductor, db, "Tracks workflow state", "SQL")
  Rel(worker, db, "Updates execution logs & progress status", "SQL")

  Rel(worker, vsphere, "Extracts disks & queries templates", "HTTPS / SOAP")
  Rel(worker, olvm, "Uploads raw/cow disks & attaches to target", "HTTPS / SDK")
  Rel(worker, hyperv, "Injects drivers & boots target VM", "WinRM / PowerShell")
```

## Internal Communication Flows

1. **REST API Request**: The user triggers a migration on the Dashboard. Nginx routes it to `cloudshift-api`, which writes the migration record to MariaDB and publishes a start event to RabbitMQ.
2. **Workflow Orchestration**: `cloudshift-conductor` picks up the start event, initiates a `TaskFlow` engine pipeline, and posts subtasks (e.g. Export, Transfer, Morph) back onto RabbitMQ.
3. **Task Execution**:
   - `cloudshift-scheduler` routes the subtask to a specific worker.
   - `cloudshift-worker` starts execution, calling the VMware API to pull disk contents and sending data to the destination (OLVM or Hyper-V).
   - If importing to OLVM, `cloudshift-minion-manager` handles creation of the helper data-minion VM to attach and write the incoming disks.
   - Once transfer finishes, `cloudshift-deployer-manager` triggers OS-morphing (e.g. installing VirtIO drivers on Windows or updating initramfs on RedHat).
