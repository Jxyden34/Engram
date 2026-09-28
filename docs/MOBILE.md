# Engram mobile beta (iOS and Android)

The `mobile/` app is part of `2.7.0-dev-beta.1`. It uses one Expo/React Native codebase for iOS and Android. The beta currently targets Expo SDK 57, which matched the Expo Go version reported by our physical iPhone test on 2026-09-28. It supports account sign-in, project switching, recent memories, new manual memories, project search, and review-only memory-agent findings. Agent consolidation drafts are previews; apply any change in the web app.

## First phone test with Expo Go

1. Install Expo Go from the App Store or Google Play on the test device. Create a free Expo account and sign in to Expo Go.
2. On the development computer, install Node.js 24 and pnpm 11.19.0. Run `cd mobile`, `pnpm install --frozen-lockfile`, and `pnpm exec expo login` with the **same Expo account** if prompted on the device.
3. Run `pnpm start` and scan the terminal QR code with the iPhone Camera or Android Expo Go. Keep the development server running while testing. The device and computer should be on the same Wi-Fi; use Expo's tunnel mode if the LAN connection fails. If Expo Go reports an SDK mismatch, check the installed Expo Go version against `mobile/package.json` before changing dependencies.
4. The sign-in screen can be checked immediately. To test authentication and data, start an isolated Engram 2.7 beta server with migrations 009, 010, and 011 applied and a test account. Enter its publicly trusted HTTPS origin in the app, for example `https://preprod.engram.example.com`. The production host was on 2.4.0 on 2026-09-28 and did not have the mobile login endpoint.

For a local simulator, `pnpm ios` requires macOS and an iOS simulator; `pnpm android` requires an Android emulator or connected device.

## Installable preview builds

The `preview` profile in `mobile/eas.json` is set up for an Android APK and an internally distributed iOS app. This route produces an Engram app icon on the home screen and does not need the development server. From `mobile/`, install EAS CLI and sign in to the `jxyden34` Expo account. The app is linked to the `engram-mobile` Expo project:

```sh
npm install -g eas-cli
eas login
eas build --platform android --profile preview
eas build --platform ios --profile preview
```

Open the completed build link on the Android device, download the APK, and allow the browser or Files app to install it when Android prompts. The iOS build requires an Apple Developer Program account and registered test devices for ad hoc provisioning. Keep these builds with testers; they are not App Store or Play Store submissions.

## Session behavior

`POST /api/v1/mobile/login` accepts the same user credentials as browser login and returns a mobile bearer token. The app stores the token in Expo SecureStore, never saves the password, and sends `X-Engram-Project` with API requests. The default token lifetime is 30 days (`MOBILE_SESSION_TTL_DAYS`); sign-out revokes it immediately. Keep the server behind HTTPS. Mobile bearer tokens do not grant MCP access.

## Checks

Run `pnpm check` and `pnpm export` in `mobile/`. CI builds both JavaScript bundles and runs the backend integration test for mobile login, project access, and token revocation. The JavaScript export does not validate native signing or device behavior.
