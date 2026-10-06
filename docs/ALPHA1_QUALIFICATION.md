# Alpha1 qualification — 2026-10-06

PR #36 remains the single draft for `2.7.0-alpha1`. Stable `main` was
renumbered to v6.5.0 separately; this preview retains its existing version.

## Verified

| Check | Evidence |
| --- | --- |
| Physical mobile flows | Tester confirmed filtered Ask, connection approval/opening, edited consolidation and Recently reviewed on Android build 7 and iPhone Expo Go on October 1. |
| Database backup and restore | Fresh custom-format dump restored with `pg_restore --exit-on-error` into `engram_qualification_20261006`, with matching counts: 4 projects, 16 memories, 0 documents, 3 Agent proposals and 2 relations before tests. |
| Restored-database application checks | All 36 backend tests passed at `e659572` against the restored database and an isolated Redis container. Includes RLS, project-bound API keys, an actual MCP HTTP tool call, OAuth consent/refresh isolation, scheduled Agent scans, stale approvals and idempotent review. |
| Object-store restoration | The beta bucket has zero objects/versions. Two versions of a canary object were copied between isolated S3 buckets and compared by SHA-256; both matched. The temporary buckets were removed. This exercises versioned object recovery, rather than restoring a populated live bucket. |
| Document ingestion and review | A Markdown canary was uploaded to an isolated S3 bucket and processed using real Ollama embeddings and extraction. One durable candidate was generated and explicitly accepted with document provenance retained. Documents/candidates were inaccessible from Personal. Used the restored database; the temporary bucket was removed. |
| Public beta recovery | VM `engram-beta-1` was shut off. Started it with the existing 2 GB allocation; database, Redis, S3 and API became healthy. `https://engram-beta.hindley.tech/health` returned `2.7.0-alpha1`. |
| Tunnel recovery | Enabled a dedicated `engram-beta-tunnel.service` on Blackwall using the existing protected token file and unchanged remote ingress/DNS. The existing production tunnel remains separate. |

Protected rollback material is on the beta VM under
`/home/jayden/.config/engram-beta/qualification-20261006-180810`:
database dump, validated archive listing, environment, Compose configuration and
the runtime patch. Application images were additionally tagged
`engram-beta-<service>:prequal-20261006` before rebuilding. Keep these until the
replacement deployment is verified. Live beta data was not replaced by the
restored database or used for the integration fixtures.

## Remaining gates

- **Gmail callback and sync:** Google OAuth is absent on the beta server.
  The user explicitly chose to leave Gmail unqualified and keep the PR draft.
- **Patched native app:** Expo `57.0.27` and expo-updates `57.0.25` pass
  compatibility checks; TypeScript and fresh iOS/Android exports pass.
  Native runtime is now `2.7.0-alpha1-native1`, Android build 8 / iOS build 6.
  The previously tested build 7 uses `2.7.0-beta4-native1`; its physical checks
  do not qualify the patched build. Retest build 8 after installation.
- **Standalone iOS speech:** Expo Go checks cover the keyboard-dictation path;
  standalone native microphone recognition remains untested.
- **Latest deployment and CI:** Record the completed image rebuild, public
  checks and final CI result in PR #36 before treating the latest server
  checkout as qualified.

Keep PR #36 draft while the remaining gates are open.
