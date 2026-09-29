# Engram mobile beta (iOS and Android)

The `mobile/` app is part of `2.7.0-beta2`. It uses one Expo/React Native codebase for iOS and Android. The beta currently targets Expo SDK 57, which matched the Expo Go version reported by our physical iPhone test on 2026-09-28. It supports account sign-in, project switching, recent memories, quick capture, project search, and review-only memory-agent findings. Agent consolidation drafts are previews; apply any change in the web app.

## Quick capture and offline drafts

Capture opens first after sign-in. Enter a thought and tap **Save capture**. The app saves it in device secure storage before attempting to send it. If the server cannot be reached, the draft stays under the account and project where it was written. You can edit, send, or delete saved drafts in Capture. Retrying a saved draft is manual; the app does not silently retry or create memories in another project. If a send times out, check Memories before retrying because the server may have accepted it. Switching projects or signing out saves an unfinished capture first. Short captures only: the app rejects a draft that is too large for secure storage and leaves its text on screen to shorten.

Drafts are local to that installation. Expo Go and the standalone Android APK do not share drafts; uninstalling the Android app may remove them. Send important drafts before uninstalling or switching apps. The iPhone home-screen web app remains online-only and does not use the native app's draft storage.

## Agent review on mobile

Open a finding to read its evidence and source memories. For possible duplicates, generate a consolidation draft; the app flags a stale draft when a source has changed. If the draft is safe and current, **Use as new capture** puts it in the Capture composer for human editing and an explicit save. Saving creates a new memory and leaves both source memories in place. **Dismiss finding** requires confirmation and only clears the pending suggestion. The Agent screen also shows recent scan results.

## iPhone home-screen app without Apple Developer membership

Open the Engram web server in Safari over HTTPS. Tap Share, choose **Add to Home Screen**, and open the new Engram icon. This installs the web interface as a standalone home-screen app without Expo Go or an Apple Developer membership. It uses the server you opened in Safari and needs a connection to that server; offline memory access is not provided. This is a web app, not an App Store or TestFlight build, and its screens differ from the Expo mobile app.

## First phone test with Expo Go

1. Install Expo Go from the App Store or Google Play on the test device. Create a free Expo account and sign in to Expo Go.
2. On the development computer, install Node.js 24 and pnpm 11.19.0. Run `cd mobile`, `pnpm install --frozen-lockfile`, and `pnpm exec expo login` with the **same Expo account** if prompted on the device.
3. Run `pnpm start` and scan the terminal QR code with the iPhone Camera or Android Expo Go. Keep the development server running while testing. The device and computer should be on the same Wi-Fi; use Expo's tunnel mode if the LAN connection fails. If Expo Go reports an SDK mismatch, check the installed Expo Go version against `mobile/package.json` before changing dependencies.
4. The sign-in screen can be checked immediately. To test authentication and data, start an isolated Engram 2.7 beta server with migrations 009, 010, and 011 applied and a test account. Enter its publicly trusted HTTPS origin in the app, for example `https://preprod.engram.example.com`. The production host was on 2.4.0 on 2026-09-28 and did not have the mobile login endpoint.

For a local simulator, `pnpm ios` requires macOS and an iOS simulator; `pnpm android` requires an Android emulator or connected device.

## Android development build for rapid testing

The `development` EAS profile includes `expo-dev-client`. Build and install it once on the USB-connected tablet, then run `pnpm start -- --dev-client` from `mobile/`. Open Engram on the tablet and connect to the development server. JavaScript and layout edits appear after a refresh without rebuilding the APK. Rebuild when native packages, Expo SDK, or app configuration change. This development build uses the same Android package ID as the standalone preview, so installing either one replaces the other; keep Metro running while using the development build.

```sh
eas build --platform android --profile development
pnpm start -- --dev-client
```

## Installable preview builds

The `preview` profile in `mobile/eas.json` is set up for an Android APK and an internally distributed iOS app. This route produces an Engram app icon on the home screen and does not need the development server. From `mobile/`, install EAS CLI and sign in to the `jxyden34` Expo account. The app is linked to the `engram-mobile` Expo project:

```sh
npm install -g eas-cli
eas login
eas build --platform android --profile preview
eas build --platform ios --profile preview
```

Open the completed build link on the Android device, download the APK, and allow the browser or Files app to install it when Android prompts. The iOS build requires an Apple Developer Program account and registered test devices for ad hoc provisioning. Keep these builds with testers; they are not App Store or Play Store submissions.

## Preview updates

Preview builds made after EAS Update was configured contain `expo-updates`, the project update URL, and the `preview` channel. The native runtime is `2.7.0-beta2-native1`; increment this value whenever native dependencies, Expo SDK, or native configuration change. JavaScript and asset changes can be published to compatible preview builds without reinstalling an APK. After local checks and device testing, publish deliberately from the intended Git commit:

```sh
eas update --channel preview --platform android --environment preview --message "Describe the tested change"
```

Force close and reopen the preview app twice to download and apply an update. A native dependency, Expo SDK, or app configuration change may require a new runtime and APK. Older APKs, including the first beta2 builds, were created before EAS Update was configured and cannot receive these updates. Development builds use Metro for live edits; the `development` channel stays separate from `preview`.

## Session behavior

`POST /api/v1/mobile/login` accepts the same user credentials as browser login and returns a mobile bearer token. The app stores the token in Expo SecureStore, never saves the password, and sends `X-Engram-Project` with API requests. The default token lifetime is 30 days (`MOBILE_SESSION_TTL_DAYS`); sign-out revokes it immediately. Keep the server behind HTTPS. Mobile bearer tokens do not grant MCP access.

## Checks

Run `pnpm check` and `pnpm export` in `mobile/`. CI builds both JavaScript bundles and runs the backend integration test for mobile login, project access, and token revocation. The JavaScript export does not validate native signing or device behavior.
