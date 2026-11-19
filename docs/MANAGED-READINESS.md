# Managed service readiness

Engram has a personal self-hosting license. A managed or commercial offering
requires separate written permission and operating terms. The existing
[license guide](LICENSING.md) lists the current permissions.

| Area | Responsibility for a managed deployment |
| --- | --- |
| Provisioning | The operator records the deployment, data region, owner, administrator, storage, and restore destination. The customer approves data sources and controls connector authorization. |
| Upgrades | The operator stages a specific revision and verifies an upgrade from the customer's deployed version. The change record includes the backup, compatibility checks, and rollback procedure. |
| Backups | The operator configures encrypted database and object backups, a separate copy, and retention. Keep the recovery key and access procedure in a separate protected store. |
| Recovery | Restore into an isolated environment, verify PostgreSQL, source objects, and application access, then record the elapsed time and data recovery point. The operator coordinates the cutover with the customer. |
| Access | Document who can administer the deployment, read customer data during recovery, and revoke credentials. Record any support access to customer data. |
| Support | Agree on the support channel, hours, incident escalation, and data handling with each pilot customer before onboarding. |

Use the [deployment guide](DEPLOYMENT.md), [upgrade checklist](UPGRADING.md),
and [disaster recovery runbook](DISASTER-RECOVERY.md) to exercise those controls
on a disposable pilot before accepting customer data.

Before a paid launch, demonstrate repeatable recovery, verify project roles and
credential isolation, validate quotas and retention, and agree on uptime,
recovery objectives, support, and exit terms. Establish willingness to pay
through pilot interviews. These are launch gates rather than service commitments.
