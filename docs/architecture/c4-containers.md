# C4 Container Diagram

This Container diagram details the internal microservices structure of the CloudShift (Coriolis) platform, showing how different services interact asynchronously and how they orchestrate the migration flow.

```mermaid
C4Container
  title Container Diagram for CloudShift

  Person(admin, "Migration Administrator", "Enterprise IT Operator or Consultant managing migrations")

  System_Boundary(cloudshift_system, "CloudShift Platform") {
    Container(dashboard, "Web Dashboard", "Nginx, Vanilla JS", "Web user interface that exposes endpoint configurations, migration jobs, and logs.")
    Container(nginx_proxy, "API Gateway / Proxy", "Nginx", "Routes /v1/ requests transparently to the API container, serves Swagger UI documentation.")
    Container(api_service, "API Service (coriolis-api)", "Python, WSGI/Flask", "Exposes REST API endpoints for migration operations and endpoints management.")
    
    ContainerDb(database, "Metadata Database", "MariaDB", "Stores endpoint definitions, job states, task executions, and transfer tracking data.")
    ContainerQueue(message_broker, "Message Broker", "RabbitMQ (Oslo.Messaging)", "Handles asynchronous message passing and work queuing between API, Conductor, and Workers.")
    
    Container(conductor, "Conductor (coriolis-conductor)", "Python, TaskFlow", "Stateless orchestration service that coordinates multi-phase migration pipelines.")
    Container(worker, "Worker (coriolis-worker)", "Python", "Executes data transfer, disk replication, and OS morphing tasks.")
    Container(scheduler, "Scheduler (coriolis-scheduler)", "Python", "Runs scheduled transfer synchronization tasks.")
    Container(minion_manager, "Minion Manager (coriolis-minion)", "Python", "Manages the lifecycle of temporary worker minion VMs.")
    Container(deployer_manager, "Deployer Manager", "Python", "Manages deployment pipelines.")
    
    ContainerDb(logs_fs, "Migration Logs Directory", "Filesystem", "Stores per-migration structured log files (*.log) in JSON-Lines format with duration metrics.")
  }

  System_Ext(vmware, "VMware vSphere", "Source hypervisor management (vCenter/ESXi)")
  System_Ext(olvm, "Oracle OLVM", "Destination hypervisor management (oVirt Engine)")
  System_Ext(hyperv, "Microsoft Hyper-V", "Destination hypervisor")

  Container_Boundary(minion_source_boundary, "Source Minion VM (Temporary)") {
    Container(minion_src, "Source Minion", "Linux VM", "Reads VMDK disks from vSphere Datastore and pipes data to the target minion.")
  }

  Container_Boundary(minion_target_boundary, "Target Minion VM (Temporary)") {
    Container(minion_tgt, "Target Minion", "Linux VM, coriolis-writer", "Receives raw chunks on port 6677 and writes them to target disks on OLVM storage.")
  }

  Rel(admin, dashboard, "Uses", "HTTPS")
  Rel(admin, nginx_proxy, "Performs API requests / views Swagger docs", "HTTPS")
  Rel(dashboard, nginx_proxy, "Calls API", "JSON/HTTPS")
  Rel(nginx_proxy, api_service, "Proxies calls to /v1/", "HTTP/7667")
  
  Rel(api_service, database, "Reads/writes metadata", "SQL/SQLAlchemy")
  Rel(api_service, message_broker, "Publishes jobs & transfers", "AMQP")
  
  Rel(conductor, message_broker, "Subscribes to orchestration queues", "AMQP")
  Rel(conductor, database, "Updates job records", "SQL/SQLAlchemy")
  
  Rel(worker, message_broker, "Subscribes to task queues", "AMQP")
  Rel(worker, database, "Updates task records", "SQL/SQLAlchemy")
  Rel(worker, minion_src, "Manages & communicates with", "SSH/22")
  Rel(worker, minion_tgt, "Manages & communicates with", "SSH/22")
  
  Rel(worker, vmware, "Queries metadata & deploys minion", "SOAP/pyvmomi")
  Rel(worker, olvm, "Provisions networks, VM, & deploys minion", "REST API/ovirt-engine-sdk-python")
  Rel(worker, hyperv, "Deploys VM & morphs OS", "WinRM/PowerShell")
  
  Rel(minion_src, minion_tgt, "Replicates disk chunks", "TCP/6677")
  
  Rel(worker, logs_fs, "Writes migration logs & tracks durations to", "File (olvm.migration_log_dir)")
```

## Description of Containers

- **Web Dashboard**: An Nginx-hosted Single Page Application (SPA) providing visual status monitoring, target environment mapping, and endpoint administration.
- **API Gateway (Nginx)**: The entrypoint for all frontend API traffic. Performs reverse proxying and serves Swagger JSON schemas.
- **API Service (`coriolis-api`)**: A Flask/Paste-based REST service that validates requests, handles authorization, and communicates with the relational database and the queue broker.
- **Metadata Database (MariaDB)**: A relational database tracking active migrations, schedules, execution configurations, and worker assignments.
- **Message Broker (RabbitMQ)**: Facilitates inter-container RPC communications and queues migration workloads for concurrency.
- **Conductor (`coriolis-conductor`)**: Uses Python's TaskFlow library to run the state machines for replica creations, updates, and deployments.
- **Worker (`coriolis-worker`)**: Performs the heavy-lifting tasks (such as copying disks and applying operating system morphing).
- **Migration Logs Directory**: Path configured via `olvm.migration_log_dir` (defaults to `/var/log/coriolis/migrations/`) where execution times, stages, and status codes are logged into JSON-Lines documents per migration.
- **Temporary Minions**: Dedicated lightweight VMs spawned on the hypervisors to read/write disk sectors. Piped together securely on Port 6677.
