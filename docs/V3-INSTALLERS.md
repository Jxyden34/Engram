# v3.0 native installation packages

Engram v3.0.2 moves host installation out of commercial preview PR #85 and into the
main distribution. The draft's commercial/business features are excluded. Desktop
signing, Store acceptance and device qualification retain the limits described below.

## Packages

| Platform | Package | Launch |
| --- | --- | --- |
| Windows x64 | ZIP containing a compiled EXE and its runtime | Extract; open EngramInstaller.exe |
| Windows Store x64 | Unsigned MSIX and identity metadata | Prepare for Partner Center submission; Microsoft signs after acceptance |
| Linux x64 / ARM64 | tar.gz containing a compiled installer | Extract; open EngramInstaller, or run it from a terminal |
| macOS Intel / Apple Silicon | Separate DMG files with an installer app | Open the DMG, then Engram Installer.app |

The wizard opens a terminal for configuration and progress. Docker Desktop must be
installed and running in Linux-container mode on Windows/macOS. Linux uses Docker
Engine and Compose 2.24.4+. Compiled Linux installers target glibc 2.35+, including
Ubuntu 22.04+ and Debian 12+. A Linux desktop needs a terminal emulator; headless
hosts use the terminal entry point. Plan for 4 CPU cores, 8 GB RAM (16 GB preferred)
and disk space for images, data, backups and optional models.

Bundles include prebuilt Engram API, worker/scheduler, web, backup and DR images.
They include runtime Compose/database/gateway files and an image SHA256. Users do
not need Python or local application compilation. Third-party service images and
optional AI models still download during setup; this is not an offline installer.

Default setup binds to localhost and opens the login page after creating an admin.
An explicit proxy/domain or automatic HTTPS mode supports server deployments.
Independent secrets are generated in a private installation folder. Windows uses
an explicit user/SYSTEM ACL. Remote Docker contexts, existing folders/configuration,
existing installer-labelled Docker resources and image checksum failures are refused.
Failures retain installation data for diagnosis; the installer never removes volumes.

## Linux one-line entry point

After a v3 release is published, the instance can serve `/install.sh`, or use the
script from that release tag. It selects a published v3 package, checks its SHA256,
then asks before installing Ubuntu/Debian prerequisites and opening the wizard.
It never installs code from the commercial draft branch. Existing container runtime
packages are preserved; conflicting installations require manual Docker configuration.
Until a v3 release exists, the script exits before changing system packages.

The eventual release command is:

```sh
curl -fsSL https://raw.githubusercontent.com/Jxyden34/Engram/v3.0.2/install.sh | sudo bash
```

The URL requires the published v3.0.2 tag and release assets. Before publication,
use pipeline artifacts to evaluate the development installer.

## Build pipeline

`.github/workflows/installers.yml` runs on installer PR changes, manual dispatch
and v3 tags:

1. Native Linux x64/ARM64 jobs build the application images, create checksum-verified
   payloads and exercise a fresh Docker installation without local source builds.
2. Windows, Linux and macOS runners compile the wizard with PyInstaller 6.22.3,
   execute its native self-test, and create packages/checksums. Native compilation
   follows [PyInstaller's build model](https://pyinstaller.org/en/stable/usage.html);
   platform runners use [GitHub's documented labels](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
3. Windows also uses the Windows SDK to pack/unpack an unsigned MSIX and execute
   the unpacked installer's self-test. Linux archives receive signed Sigstore build
   provenance, which the pipeline verifies against its workflow, source ref and commit.
4. Packages remain downloadable Actions artifacts for development. A v3 tag matching
   VERSION attaches all packages to a draft GitHub release; it does not silently
   publish stable. Payload intermediates expire after one day, packages after seven.

Direct-download Windows ZIPs and macOS DMGs remain unsigned. The MSIX is an unsigned
Store submission candidate, not a trusted sideload package. Linux archives have signed
build provenance; the executable itself does not acquire an OS-trusted signature.
Apple Developer signing/notarization, Windows Store acceptance or direct-download
Authenticode, and real Docker Desktop device qualification remain required before
claiming frictionless trusted installation.
CI compiles and self-tests on those operating systems; Linux CI also exercises the
container stack. Neither native self-tests nor readiness substitute for device tests.

The pipeline contains no signing keys, licence issuer private keys or owner dashboard.
All packages retain the repository licence and recorded source commit. The server,
MCP, web package and DR monitor report version 3.0.2; native mobile retains its
separate preview channel.

## Free Windows Store signing route

Without an account, the build uses a clearly marked preview package identity and
MSIX version `3.0.2.0`, corresponding to server version 3.0.2.
The accompanying `*-store-identity.json` records whether real Store values were used.
An unsigned preview MSIX cannot be installed as a publicly trusted Store application.

When ready, register a free individual developer account at
[Microsoft Store developer registration](https://storedeveloper.microsoft.com),
reserve the application name, then copy the exact identity fields from Partner Center
into these GitHub repository Actions **variables** (not secrets):

| Variable | Partner Center value |
| --- | --- |
| `MS_STORE_IDENTITY_NAME` | Package/Identity/Name |
| `MS_STORE_PUBLISHER` | Package/Identity/Publisher |
| `MS_STORE_PUBLISHER_DISPLAY_NAME` | Package/Properties/PublisherDisplayName |
| `MS_STORE_VERSION` | Optional four-part package version; final part must be `.0` |

Set all three identity values together and rerun the installer workflow. The build
validates them and emits `*-store-submission.msix`. Upload that package and complete
the Store listing, Docker prerequisite disclosure and `runFullTrust` justification.
[Microsoft signs MSIX packages after certification](https://learn.microsoft.com/en-us/windows/apps/publish/get-started);
it does not sign the separate ZIP/EXE. Certification has not been performed, and
SDK package validation does not establish Store acceptance.

The Store application launches the setup wizard; Docker Desktop with Linux containers
must already be installed and running. Its default data directory is `%USERPROFILE%\Engram`,
outside MSIX's redirected AppData directories so Docker can mount the physical files.
Choose a folder outside AppData if changing that default. Uninstalling the Store wizard
does not stop/remove the Docker server or delete its data. Use Docker Compose in the
installation folder to manage the server; retain the directory and volumes for backups.

## Free Linux provenance verification

The `installer-package-linux-provenance` Actions artifact contains a `.sigstore.json`
bundle for each Linux archive and `VERIFY-LINUX.txt` with the expected source ref and
digest. Tagged v3 draft releases receive these files alongside the archives/checksums.
This uses [GitHub artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
with public Sigstore signing; no signing-key secret or paid signing account is needed.
Fork PRs can build packages but cannot run the privileged signing job.

Download the archive and matching bundle. Use a current GitHub CLI, replacing the
filename, ref and full commit with the release/PR you intended to install:

```sh
gh attestation verify ARCHIVE.tar.gz \
  --bundle ARCHIVE.tar.gz.sigstore.json \
  --repo Jxyden34/Engram \
  --signer-workflow Jxyden34/Engram/.github/workflows/installers.yml \
  --source-ref refs/tags/v3.0.2 --source-digest FULL_COMMIT_SHA \
  --deny-self-hosted-runners
```

For development artifacts, use the ref/digest recorded in `VERIFY-LINUX.txt` and
confirm them against the Actions run. Verification checks the archive content and
the signing workflow's identity. It does not audit the application or configure a
Linux package-manager trust store. The one-line bootstrap still checks SHA256;
perform this provenance check before manually launching a downloaded Linux package.
