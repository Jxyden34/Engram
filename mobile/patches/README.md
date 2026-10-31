# Temporary mobile security patches

`pnpm-workspace.yaml` and the frozen lockfile enforce these patches for every
transitive importer. Use pnpm 11.19.0; do not use npm or an unpatched installation.

- `braces@3.0.3`: GHSA-vfj7-8cjw-p6xm. Iterative preflight bounds AST depth to
  256 before compile, expand or stringify recurses. It covers string inputs,
  direct ASTs and parsing's internal stringify. Excessive nesting raises a
  controlled SyntaxError; ordinary patterns, escapes and ranges remain supported.
- `deepmerge@4.3.1`: GHSA-gcqx-w48m-w2h4. Excludes `__proto__` from both
  operands' own keys before copying into the returned object. Source, CommonJS
  and UMD implementations are patched; ordinary nested config, arrays and symbols
  retain their behavior.
- `zod@3.25.76`: GHSA-mrhx-c7xc-m3w5. Backports early upper-size rejection for
  the Zod 3 arrays and sets consumed by Expo CLI 57, in CommonJS, ESM and source.
  Oversized `.max()`, `.length()` and set `.size()` inputs fail before element
  parsing. This follows the constrained-collection fix in upstream Zod PR #6652.
  Unbounded containers are unchanged; Zod 3 maps have no built-in size constraint.
  The unused bundled Zod 4 exports are not patched. Expo CLI still requires Zod 3;
  forcing Zod 4 or an Expo SDK major upgrade would change its schema contracts.

`node-forge` now uses upstream **1.4.2** through an override. Its obsolete custom
patch was removed; RSA rejection/normal-signature and Expo signing checks remain.

As of 2026-10-29, the retained braces/deepmerge releases have no published fix,
and the Zod fix is published only in the incompatible 4.x line. Version-based
audit/Dependabot alerts can therefore remain open despite the applied backports. Do not
dismiss them or change version metadata to conceal them. Replace each patch with
the upstream fixed release once available, retaining the regression tests.

Run `pnpm test:dependency-security` to check rejection cases, normal behavior,
Xcode ID generation, PostCSS maps and Expo certificate/CSR/manifest signing.
The mobile CI job runs this suite after a frozen installation.
It also generates the iOS native project to exercise Xcode's UUID consumer.
Patch files must keep LF line endings so their lockfile hashes are portable.
