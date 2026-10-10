# Temporary mobile security patches

`pnpm-workspace.yaml` and the frozen lockfile enforce these patches for every
transitive importer. Use pnpm 11.19.0; do not use npm or an unpatched installation.

- `braces@3.0.3`: GHSA-vfj7-8cjw-p6xm. Iterative preflight bounds AST depth to
  256 before compile, expand or stringify recurses. It covers string inputs,
  direct ASTs and parsing's internal stringify. Excessive nesting raises a
  controlled SyntaxError; ordinary patterns, escapes and ranges remain supported.
- `node-forge@1.4.0`: GHSA-86w9-cpqp-85rv. Backports the nested DigestAlgorithm
  element-count check from digitalbazaar/forge PR #1152. Valid SHA-256 signatures
  with or without the optional NULL parameter remain supported.

Neither package has a published fixed release as of 2026-10-09. Version-based
Dependabot alerts can therefore remain open despite the applied patches. Do not
dismiss them or change version metadata to conceal them. Replace each patch with
the upstream fixed release once available, retaining the regression tests.

Run `pnpm test:dependency-security` to check rejection cases, normal behavior,
Xcode ID generation, PostCSS maps and Expo certificate/CSR/manifest signing.
The mobile CI job runs this suite after a frozen installation.
It also generates the iOS native project to exercise Xcode's UUID consumer.
Patch files must keep LF line endings so their lockfile hashes are portable.
