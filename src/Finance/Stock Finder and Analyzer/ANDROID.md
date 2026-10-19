# Phone notifications — SFA Notifier for Android

The computer running Stock Finder and Analyzer sends push notifications to your Android phone through Firebase Cloud Messaging (FCM). The app also opens the dashboard and keeps a history of every alert.

How a notification travels:

```
your computer (python -m sfa start)  ──every 30 min──▶  Firebase Cloud Messaging  ──push──▶  SFA Notifier on your phone
        detects events, sends to your private topic        (Google, free)                       shows it, keeps history,
                                                                                                 opens the dashboard on tap
```

| You get | When |
|---|---|
| **Top leads**: a company enters the top 10 listed leads, or its score jumps by 0.20 or more | Within 30 minutes of the finder job (every 6 h) |
| **IPO pipeline**: a new IPO name, or a move to filed / priced / listed | Within 30 minutes of the IPO job (every 3 h) |
| **Valuations**: a verdict changes (e.g. Fairly valued → Undervalued), or fair value moves 15% or more | After the 08:00 analyzer job |
| **Daily digest**: top 5 leads, verdict counts, new IPO names, job health | 08:45 |
| **Service alerts**: a job failed, or prices haven't been refreshed for 36 h | At once, even in quiet hours |
| **Computer gone quiet**: no message from the computer for 12 h (raised by the phone itself) | Checked every 3 h |

Between 22:00 and 07:00 (quiet hours), messages wait until morning; service alerts still come through. More than 8 updates in one pass are folded into a single "…and N more" message.

To change any of this, edit `sfa/config/notify.yaml`.

Budget about 30–45 minutes the first time. You need:
- an Android phone with Android 8.0 or newer;
- a Google account;
- the computer that runs the app, with Android Studio installed.

---

## 1. Create the Firebase project (5 minutes)

1. Go to https://console.firebase.google.com and click **Create a project** (or **Add project**).
2. Name it, for example `sfa-notifier`. Google Analytics is not needed: you can switch it off.
3. In the new project, click the **Android** icon ("Add app"):
   - **Android package name:** `com.sfa.stockfinder` (exactly this).
   - The nickname is optional, and you can skip the SHA-1.
   - Click **Register app**.
4. Download **google-services.json** and save it into the repository at:
   ```
   src/Finance/Stock Finder and Analyzer/android/app/google-services.json
   ```
   Skip the console's "Add Firebase SDK" steps, because the project already has them. This file is ignored by Git.
5. Open **Project settings → Cloud Messaging** and check that **Firebase Cloud Messaging API (V1)** shows as *Enabled*. If it doesn't, click the ⋮ menu next to it and enable it.

## 2. Give the computer permission to send (5 minutes)

1. In the Firebase console, open **Project settings → Service accounts → Generate new private key**, then **Generate key**. A JSON file downloads.
2. Move it somewhere safe **outside** the repository, for example:
   - `C:\Users\<you>\keys\sfa-firebase.json` on Windows;
   - `~/keys/sfa-firebase.json` on macOS or Linux.

   This key can send messages to your app, so don't share or commit it.
3. Add to `sfa.env` (next to the app; see INSTALL.md):
   ```
   SFA_FCM_SERVICE_ACCOUNT=C:\Users\<you>\keys\sfa-firebase.json
   ```
4. Install the Google sign-in package in the app's virtual environment:
   ```
   pip install -r requirements.txt        # now includes google-auth
   ```
5. Check it worked: `python -m sfa doctor` should show *Phone notifications: key file found, google-auth installed*.

## 3. Build and install the app (15–20 minutes the first time)

1. Install **Android Studio** from https://developer.android.com/studio and accept its default SDK download.
2. **File → Open** the folder `src/Finance/Stock Finder and Analyzer/android`.
3. Wait for **Gradle sync** to finish. The first time it downloads Gradle 8.9 and the Android libraries, which takes a few minutes. If Android Studio offers to upgrade the Android Gradle Plugin or libraries, accepting is safe.
4. On the phone, enable **Developer options**: Settings → About phone → tap *Build number* seven times. Then turn on **USB debugging** under Developer options.
5. Connect the phone by USB, accept the "Allow USB debugging" prompt, pick the phone in the device menu at the top of Android Studio, and press **Run ▶**.

**Without a cable:**
1. Choose **Build → Build App Bundle(s) / APK(s) → Build APK(s)**.
2. Copy `android/app/build/outputs/apk/debug/app-debug.apk` to the phone, for example via Google Drive.
3. Open the file and allow "install unknown apps" for the file manager when Android asks.

When the app first opens, allow **notifications** (Android 13 and newer ask).

## 4. Pair the phone with the computer (2 minutes)

1. On the computer:
   ```
   python -m sfa notify pair
   ```
   This prints a **pairing code** (`sfa-` followed by 16 characters), the dashboard address it will send, and a **pairing link** (`sfa://pair?...`). The dashboard's **Service** page shows the same.
2. Pair the phone in either of these ways:
   - In the app, open **Settings**, type the pairing code and the dashboard address, and tap **Save and subscribe**.
   - Or send the pairing link to yourself (an email or chat to yourself) and tap it on the phone. The app opens and fills both fields.
3. Test it:
   - On the computer: `python -m sfa notify test`
   - Or on the dashboard: **Service → Send test notification**.

   The notification should reach the phone within a few seconds.

The pairing code is the FCM topic your computer sends to. Treat it like a password: anyone with your app build and the code could read your notifications.

## 5. Open the dashboard from the phone

The notifications themselves arrive anywhere, through Google. **Opening the dashboard** (tapping a notification, or the app's Dashboard tab) needs the phone to reach your computer.

**At home (same Wi-Fi):**
1. In `sfa.env` set:
   ```
   SFA_HOST=0.0.0.0
   SFA_DASHBOARD_URL=http://<computer's-LAN-IP>:8000
   ```
   Find the IP with `ipconfig` (Windows) or `ip addr` / System Settings → Network (macOS).
2. Restart the service.
3. Allow Python through the computer's firewall when it asks, on private networks only.

**Anywhere (recommended): Tailscale**, a free private network, with no router changes:
1. Install Tailscale on the computer (https://tailscale.com/download) and on the phone (Play Store). Sign in with the same account on both.
2. Note the computer's Tailscale name, shown in the Tailscale admin page, for example `my-pc.tail1234.ts.net`.
3. In `sfa.env` set:
   ```
   SFA_HOST=0.0.0.0
   SFA_DASHBOARD_URL=http://my-pc.tail1234.ts.net:8000
   ```
4. Restart the service and run `python -m sfa notify pair` again. Then update the address in the app (or reopen the new pairing link).

The dashboard has **no login**. Never forward port 8000 on your router or expose it to the internet. Tailscale or your home Wi-Fi only.

## 6. Keep notifications on time

- **Battery:** in the app, **Settings → Battery optimisation settings**, set SFA Notifier to *Unrestricted* / *Not optimised*.
  - Xiaomi, Oppo, Vivo, OnePlus and Realme phones also need **Autostart** allowed for the app in the phone's security app.
- **Sound and vibration:** set these per type in Android Settings → Apps → SFA Notifier → Notifications. The types are Top leads, IPO pipeline, Valuations, Daily digest and Service alerts.
- **Muting:** to stop a type altogether, use the switches in the app's Settings. Muted alerts are still kept in the Alerts list.
- **The computer:** must be on and awake at the job times (INSTALL.md step 7). If it is quiet for 12 hours, the phone tells you.

## 7. Troubleshooting

`python -m sfa notify log` shows the last 30 messages and their status:

| Status / symptom | Meaning and fix |
|---|---|
| `logged` | The computer has no Firebase key: check `SFA_FCM_SERVICE_ACCOUNT` in `sfa.env` and `pip install google-auth`, then restart the service |
| `failed` with HTTP 403 / 404 | The key belongs to a different Firebase project, or the FCM API (V1) is disabled (step 1.5) |
| `failed` with a connection error | `fcm.googleapis.com` / `oauth2.googleapis.com` are blocked on this network: allow them |
| `sent`, but nothing on the phone | Is the phone paired with the **same code** (app → Alerts banner)? Notifications allowed? Battery set to unrestricted? Open the app once after installing. |
| `held` | Quiet hours (22:00–07:00): it will be sent after 07:00 |
| Build fails: "File google-services.json is missing" | Step 1.4: put the file in `android/app/` |
| Build fails: "No matching client found for package name" | The Firebase Android app must use the package `com.sfa.stockfinder` |
| Dashboard tab says it can't reach the computer | Check `SFA_HOST`, `SFA_DASHBOARD_URL`, the firewall and Tailscale (step 5) |
| "Computer has gone quiet" alert | The computer is off, asleep or offline, or the service stopped: see `logs/sfa.log` |

---

Firebase Cloud Messaging is free with no message limits that matter here. The app collects nothing about you beyond what Firebase needs to deliver messages.
