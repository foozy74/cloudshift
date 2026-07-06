# C4 Container Diagram

This Container diagram details the internal microservices structure of the CloudShift (Coriolis) platform, showing how different services interact asynchronously and how they orchestrate the migration flow.

```mermaid
flowchart TD
  admin["Migration Administrator"]
  
  subgraph cloudshift_system["CloudShift Platform"]
    dashboard["Web Dashboard<br>(Nginx, Vanilla JS)"]
    nginx_proxy["API Gateway / Proxy<br>(Nginx)"]
    api_service["API Service<br>(coriolis-api)"]
    database[("Metadata Database<br>(MariaDB)")]
    message_broker[["Message Broker<br>(RabbitMQ)"]]
    conductor["Conductor<br>(coriolis-conductor)"]
    worker["Worker<br>(coriolis-worker)"]
    scheduler["Scheduler<br>(coriolis-scheduler)"]
    minion_manager["Minion Manager<br>(coriolis-minion)"]
    deployer_manager["Deployer Manager"]
    logs_fs[("Migration Logs Directory<br>(Filesystem)")]
  end

  vmware["VMware vSphere"]
  olvm["Oracle OLVM"]
  hyperv["Microsoft Hyper-V"]
  proxmox["Proxmox VE"]

  subgraph minion_source_boundary["Source Minion VM (Temporary)"]
    minion_src["Source Minion"]
  end

  subgraph minion_target_boundary["Target Minion VM (Temporary)"]
    minion_tgt["Target Minion"]
  end

  admin -->|"HTTPS"| dashboard
  admin -->|"HTTPS"| nginx_proxy
  dashboard -->|"JSON/HTTPS"| nginx_proxy
  nginx_proxy -->|"HTTP/7667"| api_service

  api_service -->|"SQL/SQLAlchemy"| database
  api_service -->|"AMQP"| message_broker

  conductor -->|"AMQP"| message_broker
  conductor -->|"SQL"| database

  worker -->|"AMQP"| message_broker
  worker -->|"SQL"| database
  worker -->|"SSH/22"| minion_src
  worker -->|"SSH/22"| minion_tgt

  worker -->|"SOAP/pyvmomi"| vmware
  worker -->|"REST/ovirt-sdk"| olvm
  worker -->|"WinRM/PS"| hyperv
  worker -->|"REST/proxmoxer"| proxmox

  minion_src -->|"TCP/6677"| minion_tgt
  worker -->|"File"| logs_fs
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
