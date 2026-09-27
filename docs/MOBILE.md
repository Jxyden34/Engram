# Engram mobile beta (iOS and Android)

The `mobile/` app is part of `2.7.0-dev-beta.1`. It uses one Expo/React Native codebase for iOS and Android. It supports account sign-in, project switching, recent memories, new manual memories, project search, and review-only memory-agent findings. Agent consolidation drafts are previews; apply any change in the web app.

## First phone test with Expo Go

1. Start an isolated Engram 2.7 beta server with database migrations 009, 010, and 011 applied. Use a publicly trusted HTTPS origin that your phone can reach. The current production host is on 2.4.0 and does not have the mobile login endpoint.
2. Install Node.js 24 and pnpm 11.19.0.
3. Run `cd mobile`, `pnpm install --frozen-lockfile`, then `pnpm start`.
4. Open the project in Expo Go on an iOS or Android device and sign in with a test Engram user account. Enter the preprod server origin only, for example `https://preprod.engram.example.com`. On a physical iPhone, sign in to Expo Go and Expo CLI with the same Expo account.

For a local simulator, `pnpm ios` requires macOS and an iOS simulator; `pnpm android` requires an Android emulator or connected device.

## Installable preview builds

The `preview` profile in `mobile/eas.json` is set up for an Android APK and an internally distributed iOS app. From `mobile/`, install EAS CLI and sign in to an Expo account, then link this app to an Expo project when prompted:

```sh
pnpm dlx eas-cli login
pnpm dlx eas-cli build --platform android --profile preview
pnpm dlx eas-cli build --platform ios --profile preview
```

Open the completed build links on the devices to install them. The iOS build requires an Apple Developer Program account and registered test devices for ad hoc provisioning. Keep these builds with testers; they are not App Store or Play Store submissions. No preview binary has been built or installed yet.

## Session behavior

`POST /api/v1/mobile/login` accepts the same user credentials as browser login and returns a mobile bearer token. The app stores the token in Expo SecureStore, never saves the password, and sends `X-Engram-Project` with API requests. The default token lifetime is 30 days (`MOBILE_SESSION_TTL_DAYS`); sign-out revokes it immediately. Keep the server behind HTTPS. Mobile bearer tokens do not grant MCP access.

## Checks

Run `pnpm check` and `pnpm export` in `mobile/`. CI builds both JavaScript bundles and runs the backend integration test for mobile login, project access, and token revocation. The JavaScript export does not validate native signing or device behavior.
