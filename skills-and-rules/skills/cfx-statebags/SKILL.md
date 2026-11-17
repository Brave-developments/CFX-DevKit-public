---
name: cfx-statebags
description: Implement FiveM replicated state bag readers, writers and change handlers.
---
Document what state is authoritative, which side can update it, and the lifecycle/cleanup. Do not use client-supplied state as a privileged server proof. Prefer narrow key replication and event-driven listeners.
