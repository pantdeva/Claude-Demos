# Phone notifications — SFA Notifier for Android

This guide sets up push notifications from the computer that runs Stock Finder and Analyzer to your Android phone. It covers:

1. installing Android Studio;
2. creating the Firebase project, with **Google sign-in** (Firebase Authentication) and a small device registry (Cloud Firestore);
3. giving the computer permission to send;
4. building the **SFA Notifier** app and installing it on the phone;
5. signing in and testing;
6. opening the dashboard from the phone, keeping alerts on time, updating the app, and troubleshooting.

Budget about an hour the first time, most of it downloads. You need:
- an Android phone with Android 8.0 or newer and Google Play services (any phone with the Play Store);
- a Google account (the one you will sign in with on the phone);
- the computer that runs the app, with about 15 GB free for Android Studio and the Android SDK.

## How it works

```
your computer (python -m sfa start)                       Google (free)                         your phone
───────────────────────────────────                       ─────────────                         ──────────
notify job, every 30 min:                                                                       SFA Notifier
  1. finds new events (leads, IPOs, valuations, ...)                                              signed in with Google
  2. reads the device registry  ───────────────────▶  Cloud Firestore  ◀──── registers its ─────  (Firebase Authentication)
  3. keeps only phones whose verified Google           users/{uid}/devices      FCM token
     account is in SFA_NOTIFY_EMAILS  ─── checks ──▶  Firebase Authentication
  4. sends to those phones  ──────────────────────▶  Firebase Cloud Messaging ──── push ──────▶  shows it, keeps history,
                                                                                                 opens the dashboard on tap
```

- **Only your account receives alerts.** The phone signs in with Google. The computer sends only to phones signed in with an account you list in `SFA_NOTIFY_EMAILS`, and checks with Firebase Authentication that the email is verified. Someone else installing your app build and signing in gets nothing.
- **Signing out stops it.** Signing out in the app removes the phone from the registry. Tokens of uninstalled apps are deleted automatically on the next send.
- **No secrets on the phone.** The app holds only its Firebase sign-in. The key that can send messages and read the registry stays on your computer.

### What you get

| You get | When |
|---|---|
| **Top leads**: a company enters the top 10 listed leads, or its score jumps by 0.20 or more | Within 30 minutes of the finder job (every 6 h) |
| **IPO pipeline**: a new IPO name, or a move to filed / priced / listed | Within 30 minutes of the IPO job (every 3 h) |
| **Valuations**: a verdict changes (e.g. Fairly valued → Undervalued), or fair value moves 15% or more | After the 08:00 analyzer job |
| **Daily digest**: top 5 leads, verdict counts, new IPO names, job health | 08:45 |
| **Service alerts**: a job failed, or prices haven't been refreshed for 36 h | At once, even in quiet hours |
| **Computer gone quiet**: no message from the computer for 12 h (raised by the phone itself) | Checked every 3 h |

- **Quiet hours:** between 22:00 and 07:00, messages wait until morning. Service alerts still come through.
- **Folding:** more than 8 updates in one pass are folded into a single "…and N more" message.
- **Changes:** edit `sfa/config/notify.yaml` to change any of this.

---

## 1. Install Android Studio (20–40 minutes, mostly downloading)

The project needs **Android Studio Ladybug (2024.2) or newer**, because it uses Android Gradle Plugin 8.7. The current stable release from https://developer.android.com/studio is fine. Android Studio brings its own Java (JDK 21), so you don't need to install Java separately.

### Windows 10 / 11

1. Download the **.exe** installer and run it. Keep *Android Virtual Device* ticked if you may want an emulator.
2. Start Android Studio. In the **Setup Wizard**, choose **Standard**, accept the licences, and let it download the SDK. By default it goes to `C:\Users\<you>\AppData\Local\Android\Sdk`.
3. For a phone connected by USB:
   - **Pixel phones:** open **Tools → SDK Manager → SDK Tools**, tick **Google USB Driver**, and click **Apply**.
   - **Samsung, Xiaomi, OnePlus and other brands:** install the maker's USB driver (search "<brand> USB driver"). Samsung's is *Samsung Android USB Driver*.

### macOS (Apple silicon or Intel)

1. Download the **.dmg** that matches your Mac. *Mac with Apple chip* is for M1 and newer.
2. Drag Android Studio into **Applications** and open it.
3. In the **Setup Wizard**, choose **Standard**. The SDK goes to `~/Library/Android/sdk`.
4. No USB driver is needed.

### Linux (Ubuntu / Debian and similar)

1. Install the libraries the emulator needs. This is only needed if you'll use the emulator.
   ```
   sudo apt install libc6:i386 libncurses5:i386 libstdc++6:i386 lib32z1 libbz2-1.0:i386
   ```
2. Unpack and start Android Studio. Either:
   - unpack the **.tar.gz** into `/opt` and start it:
     ```
     sudo tar -xzf android-studio-*-linux.tar.gz -C /opt
     /opt/android-studio/bin/studio.sh
     ```
   - or install it with snap: `sudo snap install android-studio --classic`.
3. In the **Setup Wizard**, choose **Standard**. The SDK goes to `~/Android/Sdk`. To add a launcher icon, use **Tools → Create Desktop Entry**.
4. Allow USB access to the phone:
   ```
   sudo apt install android-sdk-platform-tools-common     # udev rules for Android devices
   sudo usermod -aG plugdev $USER                         # then log out and back in
   ```

### Check the SDK (all systems)

Open **Tools → SDK Manager** (or **Settings → Languages & Frameworks → Android SDK**):

- **SDK Platforms:** tick **Android 15.0 ("VanillaIceCream") — API 35**.
- **SDK Tools:** tick **Android SDK Build-Tools**, **Android SDK Platform-Tools**, and, on Windows with a Pixel, **Google USB Driver**.

Click **Apply**. Gradle can also download missing parts itself during the first sync.

### Prepare the phone

1. **Developer options:** open Settings → About phone and tap **Build number** seven times. On Xiaomi it's *MIUI/HyperOS version*; on Samsung it's under *Software information*.
2. In **Settings → System → Developer options**, turn on **USB debugging**.
3. Optional, Android 11 or newer: turn on **Wireless debugging** to install over Wi-Fi without a cable (step 4).

---

## 2. Create the Firebase project (15 minutes)

All of this happens in the Firebase console, https://console.firebase.google.com, signed in with your Google account.

### 2.1 Project and Android app

1. Click **Create a project**. Name it, for example `sfa-notifier`. Google Analytics is not needed, so you can switch it off.
2. On the project page, click the **Android** icon (*Add app*):
   - **Android package name:** `com.sfa.stockfinder` (exactly this).
   - **App nickname:** optional.
   - **Debug signing certificate SHA-1:** you can leave this empty for now. Step 2.3 adds it, and Google sign-in **needs** it.
   - Click **Register app**.
3. Skip the console's "Download config file" and "Add Firebase SDK" pages for now (click **Next** → **Continue to console**). The project already contains the SDK setup, and you'll download the config file in step 2.4, after sign-in is set up.

### 2.2 Turn on Google sign-in (Firebase Authentication)

1. In the left menu, open **Build → Authentication → Get started**.
2. On the **Sign-in method** tab, click **Google**, then **Enable**.
3. Choose your email as the **Support email for project** and click **Save**.

This also creates the *Web client* (an OAuth client ID) that the app uses to request a Google sign-in token.

> If the console asks you to configure the **OAuth consent screen / branding**, give it an app name (e.g. *SFA Notifier*) and your email, and save. Only basic scopes (email and profile) are used, so no Google verification is needed.

### 2.3 Add the computer's SHA-1 fingerprint

Google sign-in only works for app builds signed with a certificate registered in Firebase. Every computer with Android Studio has its own **debug certificate** (`~/.android/debug.keystore`), and this project signs both debug and release builds with it.

Get its SHA-1 in one of these ways:

- **From the command line.** Open the project in Android Studio first (step 4.1), then use the **Terminal** tab at the bottom:
  - Windows: `.\gradlew.bat signingReport`
  - macOS or Linux: `./gradlew signingReport`

  Look for `Variant: debug` and copy the line `SHA1: AB:CD:…`.
- **From the Gradle panel.** Open the **Gradle** panel on the right and choose **app → Tasks → android → signingReport**. If the task list is empty, enable *Settings → Experimental → Configure all Gradle tasks during Gradle Sync* and sync again.
- **Without the project, with keytool.** On Windows, use `%USERPROFILE%\.android\debug.keystore` as the path.
  ```
  keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android -keypass android
  ```
  The keystore only exists after Android Studio has built or run any app once.

Then, in the Firebase console:

1. Open **⚙ Project settings → General → Your apps → com.sfa.stockfinder**.
2. Click **Add fingerprint**, paste the SHA-1, and click **Save**.
3. Optionally, add the **SHA-256** from the same report too.

If you build the app on more than one computer, add each computer's SHA-1.

### 2.4 Download google-services.json

On the same **Project settings → Your apps** card, click **google-services.json** to download it. Save it in the repository as:

```
src/Finance/Stock Finder and Analyzer/android/app/google-services.json
```

Download it **after** steps 2.2 and 2.3. The file then contains the sign-in client entries (`oauth_client`). Without them, the build fails with *Unresolved reference: default_web_client_id*.

The file is ignored by Git. It identifies your Firebase project but holds no secret that can send messages.

### 2.5 Create the device registry (Cloud Firestore)

1. Open **Build → Firestore Database → Create database**.
2. Choose the **Standard** edition if asked.
3. Pick a **location** close to you, for example `asia-south1 (Mumbai)`. The location can't be changed later.
4. Choose **Start in production mode** and click **Create**.
5. Open the **Rules** tab. Replace everything with the contents of `android/firestore.rules` from this repository and click **Publish**.

   These rules let a signed-in phone write only its own `users/{uid}/devices` entries and close everything else. The computer is not affected by the rules: it reads with its service-account key.

Usage stays far inside the free (Spark) plan: a few document reads every 30 minutes.

### 2.6 Check Cloud Messaging

Open **Project settings → Cloud Messaging** and check that **Firebase Cloud Messaging API (V1)** shows as *Enabled*. If it doesn't, click the ⋮ menu next to it and enable it.

---

## 3. Give the computer permission to send (5 minutes)

1. **Download the key.** In the Firebase console, open **Project settings → Service accounts**, click **Generate new private key**, then **Generate key**. A JSON file downloads.
2. **Store it outside the repository**, for example:
   - Windows: `C:\Users\<you>\keys\sfa-firebase.json`
   - macOS or Linux: `~/keys/sfa-firebase.json`

   On macOS or Linux, also run `chmod 600 ~/keys/sfa-firebase.json`.

   This key can send messages to your app and read the device registry, so never share or commit it. If it leaks, delete it under *Service accounts → Manage service account permissions → Keys* and generate a new one.
3. **Add three lines to `sfa.env`** (next to the app; see INSTALL.md):
   ```
   SFA_FCM_SERVICE_ACCOUNT=C:\Users\<you>\keys\sfa-firebase.json
   SFA_NOTIFY_EMAILS=you@gmail.com
   ```
   - **`SFA_NOTIFY_EMAILS`** lists the Google account(s) whose phones may receive notifications. Separate several with commas. Use the account you will sign in with in the app.
   - The dashboard address for the phone (**`SFA_DASHBOARD_URL`**) is set in step 6.
4. **Install the Google client library** in the app's virtual environment, if you haven't already:
   ```
   pip install -r requirements.txt        # includes google-auth
   ```
5. **Restart the service** (INSTALL.md step 7), then run `python -m sfa doctor`. It should show:
   - *Phone notifications: key file found, google-auth installed*;
   - `SFA_NOTIFY_EMAILS set`;
   - *Signed-in phones: 0* for now, since the phone isn't signed in yet.

---

## 4. Build the app and install it on the phone

### 4.1 Open and build

1. In Android Studio, choose **File → Open**, select the folder `src/Finance/Stock Finder and Analyzer/android`, and trust the project.
2. Wait for **Gradle sync** to finish (bottom status bar). The first time, it downloads Gradle 8.9 and the libraries, which takes 5–10 minutes.
   - If Android Studio offers to upgrade the Android Gradle Plugin or libraries, you can decline (the project is pinned to tested versions) or accept; both work.
   - If sync complains about the JDK, set **Settings → Build, Execution, Deployment → Build Tools → Gradle → Gradle JDK** to the bundled **jbr-21**.
3. If you skipped it, do step 2.3 now: get the SHA-1, add it in Firebase, and download `google-services.json` again.
4. Choose **Build → Make Project**. It should finish with *BUILD SUCCESSFUL*.

### 4.2 Install on the phone

Use whichever way suits you.

**A. By USB cable (simplest)**
1. Connect the phone. Accept **Allow USB debugging?** on the phone, and tick *Always allow from this computer*.
2. Pick the phone in the device menu at the top of Android Studio.
3. Press **Run ▶**. The app installs and opens.

**B. Over Wi-Fi (Android 11 or newer, phone and computer on the same network)**
1. In Android Studio, open the device menu → **Pair Devices Using Wi-Fi**.
2. On the phone, go to **Developer options → Wireless debugging → Pair device with QR code** and scan the code.
3. Pick the phone and press **Run ▶**.

**C. As an APK file (no Android Studio connection to the phone)**
1. Build the APK in one of these ways:
   - choose **Build → Build App Bundle(s) / APK(s) → Build APK(s)**;
   - or run `./gradlew assembleRelease` (on Windows: `.\gradlew.bat assembleRelease`) in the Terminal tab.
2. Find the file:
   - debug build: `android/app/build/outputs/apk/debug/app-debug.apk`;
   - release build: `android/app/build/outputs/apk/release/app-release.apk`.

   The release build is smaller and faster. It is signed with the same debug certificate, so Google sign-in works with the same SHA-1.
3. Copy it to the phone, for example via Google Drive, a USB file transfer, or an email to yourself.
4. Open it on the phone.
   - Allow **Install unknown apps** for the app you opened it with when Android asks.
   - If **Play Protect** warns about an unknown developer, choose *More details → Install anyway*. The app is your own build.

**D. Emulator (for trying it without a phone)**
1. Open **Device Manager → Create Virtual Device**.
2. Pick a phone and a system image **with Google Play** (the Play Store icon in the list). Google sign-in needs Play services.
3. Sign in to a Google account in the emulator's Settings, then **Run ▶**.

When the app first opens, allow **notifications** (Android 13 and newer ask).

### 4.3 Updating the app later

After pulling a new version of the repository:

1. Raise `versionCode` in `android/app/build.gradle.kts` if the update didn't already.
2. Install again with any method above. It installs over the old one and keeps your sign-in and alert history.

Android only accepts an update signed with the **same certificate**, so keep `~/.android/debug.keystore` (Windows: `%USERPROFILE%\.android\debug.keystore`) backed up. If it is lost or you switch computers:

1. Uninstall the app from the phone.
2. Add the new computer's SHA-1 in Firebase (step 2.3) and download `google-services.json` again.
3. Install, and sign in again.

---

## 5. Sign in and test (2 minutes)

1. Open SFA Notifier → **Settings** → **Sign in with Google**, and pick the account you put in `SFA_NOTIFY_EMAILS`. The Alerts tab banner changes to *Signed in · waiting for the computer's first message*.
2. On the computer, run:
   ```
   python -m sfa notify pair
   ```
   It lists the allowed accounts and the **signed-in phones** it can see, for example `you@gmail.com  samsung SM-S921B  2026-…`. The dashboard's **Service** page shows the same.
3. Send a test, either way:
   - on the computer: `python -m sfa notify test`;
   - or on the dashboard: **Service → Send test notification**.

   It should reach the phone within a few seconds.
4. Check `python -m sfa notify log` if it didn't arrive (troubleshooting below).

To stop notifications on a phone, use **Settings → Sign out**: the phone removes itself from the registry. To stop them for an account, remove it from `SFA_NOTIFY_EMAILS` and restart the service.

To review every signed-in user, open the Firebase console → **Authentication → Users**. You can disable or delete accounts there, and the computer skips disabled ones.

---

## 6. Open the dashboard from the phone

The notifications arrive anywhere, through Google. **Opening the dashboard** needs the phone to reach your computer. That happens when you tap a notification or use the app's Dashboard tab.

**At home (same Wi-Fi):**
1. In `sfa.env` set:
   ```
   SFA_HOST=0.0.0.0
   SFA_DASHBOARD_URL=http://<computer's-LAN-IP>:8000
   ```
   To find the IP, use `ipconfig` on Windows, System Settings → Network on macOS, or `ip addr` on Linux.
2. Restart the service.
3. Allow Python through the computer's firewall when it asks, on private networks only.

**Anywhere (recommended): Tailscale.** It's a free private network and needs no router changes.
1. Install Tailscale on the computer (https://tailscale.com/download) and on the phone (Play Store), and sign in with the same account on both.
2. Note the computer's Tailscale name from the Tailscale admin page, for example `my-pc.tail1234.ts.net`.
3. In `sfa.env` set:
   ```
   SFA_HOST=0.0.0.0
   SFA_DASHBOARD_URL=http://my-pc.tail1234.ts.net:8000
   ```
4. Restart the service.

To put the address into the app, do one of these:
- type it in the app's **Settings → Dashboard address** and tap **Save address**;
- or open the **set-up link** on the phone. `python -m sfa notify pair` prints it as `sfa://pair?url=…`, and the dashboard's Service page shows it. You can email it to yourself and tap it on the phone.

The phone also picks the address up from the computer's heartbeat if it is still empty.

The dashboard has **no login**. Never forward port 8000 on your router or expose it to the internet; use Tailscale or your home Wi-Fi only. Google sign-in protects the notifications, not the dashboard.

---

## 7. Keep notifications on time

- **Battery:** in the app, open **Settings → Battery optimisation settings** and set SFA Notifier to *Unrestricted* / *Not optimised*.
  - Xiaomi, Oppo, Vivo, OnePlus and Realme phones also need **Autostart** allowed for the app in the phone's security app.
- **Sound and vibration:** set these per type in Android Settings → Apps → SFA Notifier → Notifications. The types are Top leads, IPO pipeline, Valuations, Daily digest and Service alerts.
- **Muting:** to stop a type altogether, use the switches in the app's Settings. Muted alerts are still kept in the Alerts list.
- **The computer:** must be on and awake at the job times (INSTALL.md step 7). If it is quiet for 12 hours, the phone tells you.

---

## 8. Troubleshooting

`python -m sfa notify log` shows the last 30 messages, their status and any error. The dashboard's Service page has the same table.

### Signing in (on the phone)

| Message | Meaning and fix |
|---|---|
| *Google sign-in is not set up for this build (code 10)* / `DEVELOPER_ERROR` | The SHA-1 of the computer that built the app isn't in Firebase, or `google-services.json` is older than the fingerprint. Do step 2.3, download the file again (2.4), rebuild and reinstall |
| *No Google account on this phone* / `NoCredentialException` | Add a Google account in Android Settings → Accounts. On an emulator, use a *Google Play* image (4.2 D) |
| *Sign-in cancelled* | The account picker was closed: try again |
| Sign-in works, but *Could not register: PERMISSION_DENIED* | The Firestore rules weren't published (2.5 step 5), or the database doesn't exist yet |
| *Could not register: … unavailable / offline* | No internet on the phone. The app retries at the next start and once a day |

### Building

| Message | Fix |
|---|---|
| *File google-services.json is missing* | Step 2.4: put the file in `android/app/` |
| *No matching client found for package name 'com.sfa.stockfinder'* | The Firebase Android app must use exactly that package name (2.1) |
| *Unresolved reference: default_web_client_id* | `google-services.json` was downloaded before Google sign-in was enabled: do 2.2, then download it again |
| Gradle sync fails on the JDK | Set Gradle JDK to the bundled jbr-21 (4.1) |
| *INSTALL_FAILED_UPDATE_INCOMPATIBLE* | The installed app was signed by another computer: uninstall it first (4.3) |

### Sending (on the computer)

| Status / symptom | Meaning and fix |
|---|---|
| `logged`: *SFA_FCM_SERVICE_ACCOUNT is not set …* | Set the key path in `sfa.env`, run `pip install google-auth`, then restart the service |
| `logged`: *set SFA_NOTIFY_EMAILS …* | Add your Google account to `SFA_NOTIFY_EMAILS` and restart |
| `logged`: *no signed-in phone yet …* | Sign in to the app with an account that is **exactly** in `SFA_NOTIFY_EMAILS`, then use **Re-register** in the app's Settings |
| `failed`: *Firestore HTTP 403 … API has not been used / is disabled* | Create the Firestore database (2.5). If it exists, enable *Cloud Firestore API* in the Google Cloud console for the project |
| `failed`: *Identity Toolkit HTTP 403* | Enable Authentication (2.2), or the *Identity Toolkit API* in the Google Cloud console |
| `failed`: *FCM HTTP 403 / 404* | The key belongs to a different Firebase project, or the FCM API (V1) is disabled (2.6) |
| `failed` with a connection error | The network blocks `fcm.googleapis.com`, `firestore.googleapis.com`, `identitytoolkit.googleapis.com` or `oauth2.googleapis.com`: allow them (`python -m sfa doctor` checks all four) |
| `sent`, but nothing on the phone | Notifications allowed for the app? Battery unrestricted (step 7)? Open the app once after installing. Check that the phone appears under *Signed-in phones* (`notify pair`) |
| `held` | Quiet hours (22:00–07:00): it is sent after 07:00 |
| Dashboard tab can't reach the computer | Check `SFA_HOST`, `SFA_DASHBOARD_URL`, the firewall and Tailscale (step 6) |
| *Computer has gone quiet* alert | The computer is off, asleep or offline, or the service stopped: see `logs/sfa.log` |

---

## Security model, in short

- **On the phone:**
  - **Google sign-in:** Firebase Authentication, through Android's Credential Manager.
  - **Registry access:** Firestore rules let the phone write only `users/<its uid>/devices/…`.
- **On the computer:**
  - **The key:** the service-account key in `SFA_FCM_SERVICE_ACCOUNT`, kept outside the repository, is the only thing that can send or read the registry.
  - **Who receives:** it sends only to devices of users whose **verified** email, as Firebase Authentication reports it (not as the app claims), is in `SFA_NOTIFY_EMAILS`. Disabled users are skipped.
- **In Git:** nothing secret is committed. `google-services.json`, `sfa.env` and the key are ignored.
- **The dashboard:** it has no login, so reach it only through Tailscale or your home network.

Firebase Authentication, Firestore at this size and Cloud Messaging are free. The app collects nothing beyond your Google account's email (to match it against `SFA_NOTIFY_EMAILS`), the phone model, and the messaging token.

<details>
<summary>Optional: the older shared-code mode (no sign-in)</summary>

Setting `audience: topic` in `sfa/config/notify.yaml` makes the computer send to a shared FCM topic instead of signed-in devices. `python -m sfa notify pair` then prints a code (`sfa-…`) and a link `sfa://pair?topic=…`. Opening that link on the phone subscribes the app to the topic, with no sign-in needed. Anyone with your app build and the code could receive the alerts, so the default sign-in mode is recommended.

</details>
