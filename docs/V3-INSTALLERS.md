# v3.0 native installation packages

This work moves host installation out of commercial preview PR #85 and into the
v3.0 distribution track. It does not publish v3.0, change the stable release number
or include the draft's commercial/business features. Stable remains v2.8.0.

## Packages

| Platform | Package | Launch |
| --- | --- | --- |
| Windows x64 | ZIP containing a compiled EXE and its runtime | Extract; open EngramInstaller.exe |
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
curl -fsSL https://raw.githubusercontent.com/Jxyden34/Engram/v3.0.0/install.sh | sudo bash
```

This URL is reserved for the future tag; use pipeline artifacts to evaluate the
development installer. No currently published v3 stable release is implied.

## Build pipeline

`.github/workflows/installers.yml` runs on installer PR changes, manual dispatch
and v3 tags:

1. Native Linux x64/ARM64 jobs build the application images, create checksum-verified
   payloads and exercise a fresh Docker installation without local source builds.
2. Windows, Linux and macOS runners compile the wizard with PyInstaller 6.22.3,
   execute its native self-test, and create packages/checksums. Native compilation
   follows [PyInstaller's build model](https://pyinstaller.org/en/stable/usage.html);
   platform runners use [GitHub's documented labels](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
3. Packages remain downloadable Actions artifacts for development. A v3 tag matching
   VERSION attaches all packages to a draft GitHub release; it does not silently
   publish stable. Payload intermediates expire after one day, packages after seven.

Previews are unsigned: Windows/macOS trust prompts may require an explicit Run/Open
action. Authenticode, Apple Developer signing/notarization and real Docker Desktop
device qualification remain required before claiming frictionless trusted installation.
CI compiles and self-tests on those operating systems; Linux CI also exercises the
container stack. Neither native self-tests nor readiness substitute for device tests.

The pipeline contains no signing keys, licence issuer private keys or owner dashboard.
All packages retain the repository licence and recorded source commit. Runtime version
stays unchanged until a separate release/version instruction is given.
