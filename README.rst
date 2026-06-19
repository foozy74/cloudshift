CloudShift
==========

*VMware to OLVM/Hyper-V Workload Migration as a Service — by thesolution.at*

CloudShift is a migration engine designed to automate the transfer and deployment of virtual machines from VMware vSphere (Origin) into Oracle OLVM/oVirt and Microsoft Hyper-V (Destination) environments.

Features:
- Live incremental disk replication.
- Automated OS morphing (driver injection, network adaptation, and boot configuration).
- Direct Hyper-V deployment via WinRM/PowerShell.
- Automated Oracle OLVM logical network and VNIC profile provisioning based on VLAN-IDs.
- Safe VLAN conflict detection and migration abort validation.
- Per-migration structured JSON-Lines log files with duration metrics.
- Standardized containerized dashboard deployment.
- Offline and Standalone (NoAuth) execution capabilities.
