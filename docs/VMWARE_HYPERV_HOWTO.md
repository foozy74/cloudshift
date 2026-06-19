# VMware to Microsoft Hyper-V Migration Guide

This guide describes how to migrate virtual machines from **VMware vSphere** to **Microsoft Hyper-V** using CloudShift.

## Overview

The Hyper-V import provider uses WinRM/PowerShell commands to talk directly to target Hyper-V hosts. 

### Key Capabilities
- Full transfer, deployment, and OS morphing.
- Auto-installation of Hyper-V Integration Services (LIS/Windows Integration Components).
- Network switch mapping.
- Disk format conversion to VHD/VHDX.

> [!NOTE]
> Hyper-V disk snapshots during replication are deliberate no-ops. For migrations, fall back to `clone_disks=True` to perform clone-based transfers, matching the OLVM behavior.

---

## Prerequisites

1. **Target Hyper-V Host**:
   - Windows Server with Hyper-V role enabled.
   - WinRM configured and listening securely.
   - Credentials configured in CloudShift's secrets manager (Barbican or local settings).
2. **WinRM Transport**:
   - NTLM, Kerberos, CredSSP, or Basic authentication enabled based on network security requirements.

---

## Endpoint Configuration

Example connection info for Hyper-V:

```json
{
    "host": "hyperv-host.local",
    "username": "Administrator",
    "password": "Password123",
    "transport": "ntlm"
}
```

Ensure the port group network names on vSphere match target Hyper-V Virtual Switch names using target network mappings in the migration payload.
