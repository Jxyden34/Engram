# Alpha1 qualification — 2026-10-06

This records the October 6 qualification of PR #36 at `2.7.0-alpha1`.
On October 8 the user approved promotion to `main` as stable `v2.7.0`,
superseding the previous keep-draft instruction. The native mobile runtime
and preview update channel retain their existing identifiers.

## Verified

| Check | Evidence |
| --- | --- |
| Physical mobile flows | Tester confirmed filtered Ask, connection approval/opening, edited consolidation and Recently reviewed on Android build 7 and iPhone Expo Go on October 1. |
| Database backup and restore | Fresh custom-format dump restored with `pg_restore --exit-on-error` into `engram_qualification_20261006`, with matching counts: 4 projects, 16 memories, 0 documents, 3 Agent proposals and 2 relations before tests. |
| Restored-database application checks | All 36 backend tests passed at `e659572` against the restored database and an isolated Redis container. Includes RLS, project-bound API keys, an actual MCP HTTP tool call, OAuth consent/refresh isolation, scheduled Agent scans, stale approvals and idempotent review. |
| Scheduled worker execution | A due project schedule enqueued an actual RQ job on isolated Redis. A worker consumed it with project metadata, marked the scan completed and created the expected proposal. The run remained invisible from Personal. |
| Object-store restoration | The beta bucket has zero objects/versions. Two versions of a canary object were copied between isolated S3 buckets and compared by SHA-256; both matched. The temporary buckets were removed. This exercises versioned object recovery, rather than restoring a populated live bucket. |
| Document ingestion and review | A Markdown canary was uploaded to an isolated S3 bucket and processed using real Ollama embeddings and extraction. One durable candidate was generated and explicitly accepted with document provenance retained. Documents/candidates were inaccessible from Personal. Used the restored database; the temporary bucket was removed. |
| Public beta recovery | VM `engram-beta-1` was shut off. Started it with the existing 2 GB allocation; database, Redis, S3 and API became healthy. `https://engram-beta.hindley.tech/health` returned `2.7.0-alpha1`. |
| Tunnel recovery | Enabled a dedicated `engram-beta-tunnel.service` on Blackwall using the existing protected token file and unchanged remote ingress/DNS. The existing production tunnel remains separate. |
| Build memory | RAM remains 2 GB. The first web rebuild was killed with SIGKILL under memory pressure. Added a protected 2 GB disk swap file, `/var/lib/engram-beta-build.swap`, with an `/etc/fstab` entry before retrying; this does not increase guest RAM. |
| Rebuilt beta deployment | Rebuilt API, worker, connector scheduler and web from `e659572`, preserving the beta Compose binding and environment. Services started successfully; API, PostgreSQL, Redis and S3 health checks passed. Public health and OAuth discovery returned HTTP 200. |
| Public authentication and MCP | Temporary public-HTTPS canary passed mobile login/logout/revocation, project-bound API-key reads and an MCP `memory_get` call. Overriding the key's project was rejected with 403. Temporary user, key, session, memory and project were removed. |
| CI and CodeQL | All five CI jobs and all three CodeQL language analyses passed at `510781c`: [CI run](https://github.com/Jxyden34/Engram/actions/runs/37510503692), [CodeQL run](https://github.com/Jxyden34/Engram/actions/runs/37510503747). This documentation update does not change runtime code. |

Protected rollback material is on the beta VM under
`/home/jayden/.config/engram-beta/qualification-20261006-180810`:
database dump, validated archive listing, environment, Compose configuration and
the runtime patch. Application images were additionally tagged
`engram-beta-<service>:prequal-20261006` before rebuilding. Keep these until the
replacement deployment is verified. Live beta data was not replaced by the
restored database or used for the integration fixtures.

## Remaining gates

- **Gmail callback and sync:** Google OAuth is absent on the beta server.
  Gmail was explicitly left unqualified. Promotion approval does not provide
  evidence of a real Gmail callback or sync test.
- **Patched native app:** Expo `57.0.27` and expo-updates `57.0.25` pass
  compatibility checks; TypeScript and fresh iOS/Android exports pass.
  Native runtime is now `2.7.0-alpha1-native1`, Android build 8 / iOS build 6.
  The previously tested build 7 uses `2.7.0-beta4-native1`; its physical checks
  do not qualify the patched build. Retest build 8 after installation.
  [Build 8](https://expo.dev/accounts/jxyden34/projects/engram-mobile/builds/726a8e44-6334-4867-801b-7a8e12b50e2a)
  was queued from `e659572`; no new OTA update was published. Repeat the
  iPhone Expo Go checks on the patched source as well.
- **Standalone iOS speech:** Expo Go checks cover the keyboard-dictation path;
  standalone native microphone recognition remains untested.

The user approved server promotion with these qualification limits recorded.
Do not describe the patched mobile build, native iOS speech or Gmail callback
as tested until their checks have actually passed.
