# Engram mobile beta (iOS and Android)

The `mobile/` app is part of `2.7.0-dev-beta.1`. It uses one Expo/React Native codebase for iOS and Android. It supports account sign-in, project switching, recent memories, new manual memories, project search, and review-only memory-agent findings. Agent consolidation drafts are previews; apply any change in the web app.

## Run during development

1. Start an Engram 2.7 beta server with database migrations 009, 010, and 011 applied. Use a publicly trusted HTTPS origin that your phone can reach.
2. Install Node.js 24 and pnpm 11.19.0.
3. Run `cd mobile`, `pnpm install --frozen-lockfile`, then `pnpm start`.
4. Open the project in Expo Go on an iOS or Android device and sign in with an Engram user account. Enter the server origin only, for example `https://engram.example.com`.

For a local simulator, `pnpm ios` requires macOS and an iOS simulator; `pnpm android` requires an Android emulator or connected device. The app currently has no published App Store, Play Store, or installable beta binary. Native binary builds and physical-device testing remain release gates.

## Session behavior

`POST /api/v1/mobile/login` accepts the same user credentials as browser login and returns a mobile bearer token. The app stores the token in Expo SecureStore, never saves the password, and sends `X-Engram-Project` with API requests. The default token lifetime is 30 days (`MOBILE_SESSION_TTL_DAYS`); sign-out revokes it immediately. Keep the server behind HTTPS. Mobile bearer tokens do not grant MCP access.

## Checks

Run `pnpm check` and `pnpm export` in `mobile/`. CI builds both JavaScript bundles and runs the backend integration test for mobile login, project access, and token revocation. The JavaScript export does not validate native signing or device behavior.
