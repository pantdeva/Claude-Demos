# Phone notifications and the dashboard on your phone

The dashboard is also a **web app**. You open it on your phone, add it to the home screen, and it receives **push notifications** from the computer that runs Stock Finder and Analyzer. This works on Android (Chrome, Edge, Firefox, Samsung Internet) and on iPhone/iPad (Safari, iOS 16.4 or newer). It needs no app store, no Firebase project and no Android Studio. The computer sends the notifications itself through the standard Web Push protocol.

Setup takes about 15 minutes. You need:
- the computer running the service (INSTALL.md);
- a free Tailscale account (you can sign in with Google, Microsoft or Apple);
- your phone.

## How it works

```
your computer                                   browser push service                  your phone
(python -m sfa start)                           (Google for Chrome, Apple for Safari)
  notify job, every 30 min ── encrypted push ──▶  forwards it  ─────────────────────▶  notification
  dashboard on 127.0.0.1:8000                                                              │ tap
        ▲                                                                                  ▼
        └──── Tailscale Serve: https://<computer>.<tailnet>.ts.net ◀── private network ──  web app
```

- **Why Tailscale.** Browsers allow notifications only on an HTTPS address. Tailscale gives your computer a private HTTPS address, with a real certificate, that only *your* devices can open, from home or anywhere. The dashboard stays bound to `127.0.0.1` and is never exposed to the internet.
- **Messages are end-to-end encrypted.** Each message is encrypted for that one browser (RFC 8291) and signed with your computer's own key (VAPID, RFC 8292). The key is created on first use in `db/push/` and never leaves the computer.
- **Who gets notifications.** Every browser where you tapped **Enable notifications** receives them. You can see and remove devices on the Alerts page.

### What you get

| Notification | When |
|---|---|
| **Top leads**: a company enters the top 10 listed leads, or its score jumps by 0.20 or more | within 30 minutes of the finder job (every 6 h) |
| **IPO pipeline**: a new IPO name, or a move to filed / priced / listed | within 30 minutes of the IPO job (every 3 h) |
| **Valuations**: a verdict changes, or fair value moves 15% or more | after the 08:00 analyzer job |
| **Daily digest**: top 5 leads, verdict counts, new IPO names, job health | 08:45 |
| **Service alerts**: a job failed, or prices haven't been refreshed for 36 h | at once, even in quiet hours |

- **Tapping a notification** opens the right page, such as the company.
- **Quiet hours:** messages wait between 22:00 and 07:00, except service alerts.
- **Folding:** more than 8 messages in one pass are folded into one "…and N more".
- **Changing it:** muting is per device, on the Alerts page. Everything else is in `sfa/config/notify.yaml`.

---

## 1. Tailscale on the computer (5 minutes)

1. Install Tailscale from https://tailscale.com/download and sign in. On Windows, it appears in the system tray.
2. Open the admin console at https://login.tailscale.com/admin/dns:
   - check that **MagicDNS** is on (it is by default);
   - under **HTTPS Certificates**, click **Enable HTTPS**.
3. Publish the dashboard on your private network. Open **PowerShell** (Windows) or **Terminal** (macOS/Linux) and run:
   ```
   tailscale serve --bg 8000
   ```
   It prints your address, for example `https://desktop-g002k9a.tail1234.ts.net/`.
   - The first time, it may print a link to allow Serve on your tailnet: open it and click **Enable**, then run the command again.
   - `--bg` keeps it running, also after a restart.
   - To check it later, run `tailscale serve status`. To stop it, run `tailscale serve --https=443 off`.
4. Open `sfa.env` (next to the app) and add the address without the trailing slash:
   ```
   SFA_DASHBOARD_URL=https://desktop-g002k9a.tail1234.ts.net
   ```
   Leave `SFA_HOST` unset: Tailscale Serve connects to the dashboard on this computer, so it does not need to listen on the network.
5. Restart the service. On Windows, double-click `deploy\windows\restart_service.bat`; on macOS/Linux, see INSTALL.md step 7.
6. Check: open the address in the computer's browser. You should see the dashboard with a valid lock icon.

Use `tailscale serve`, never `tailscale funnel`: Funnel would put the dashboard on the public internet, and the dashboard has no login.

## 2. Tailscale on the phone (3 minutes)

1. Install **Tailscale** from the Play Store or App Store.
2. Sign in with the **same account** as on the computer, and allow the VPN connection.
3. Open your `https://….ts.net` address in the browser. The dashboard should load.

## 3. Install the web app and turn on notifications (2 minutes)

**Android (Chrome)**
1. With the dashboard open, tap **⋮ → Add to Home screen → Install** (or *Install app*).
2. Open **Stock Finder** from the home screen, go to **Alerts**, and tap **Enable notifications → Allow**.
3. A test notification arrives within a few seconds.

**iPhone / iPad (iOS 16.4 or newer)**
1. Open the dashboard in **Safari**, tap **Share → Add to Home Screen → Add**.
2. Open **Stock Finder** *from the home screen*, go to **Alerts**, and tap **Enable notifications → Allow**. Notifications on iOS work only in the installed web app.

**The computer itself (optional)**
Open http://localhost:8000/#alerts and tap **Enable notifications** to get desktop notifications too.

On the **Alerts** page you can:
- choose per device which types to receive;
- send a test notification;
- remove old devices;
- read the history of every notification.

## 4. Keep notifications on time

- **Android:** in Settings → Apps → Chrome (or the browser you installed it with) → Battery, choose **Unrestricted**. Some phones also need *Autostart* allowed for that browser (Xiaomi, Oppo, Vivo, OnePlus, Realme).
- **Tailscale only matters for opening the dashboard.** Notifications arrive even when Tailscale is off on the phone; tapping one opens the dashboard only when Tailscale is connected.
- **The computer has to be on and awake** at the job times (INSTALL.md step 7). The Alerts page shows when it last checked for news.

---

## Troubleshooting

`python -m sfa notify log` lists the last 30 messages with their status. `python -m sfa notify devices` lists the devices. The Alerts page shows the same.

| Symptom | Fix |
|---|---|
| Alerts says **"This address is not HTTPS"** | You opened `http://<IP>:8000`. Open the `https://….ts.net` address instead (step 1) |
| Alerts says **"Add to Home Screen first"** (iPhone) | Install from Safari and open it from the home screen (step 3) |
| **Blocked**: notifications are blocked for this site | Lock icon → Permissions → Notifications → Allow (Android); Settings → Notifications → Stock Finder (iPhone); then reload |
| `tailscale serve` says HTTPS is not enabled | Enable **HTTPS Certificates** in the admin console (step 1.2) |
| The `.ts.net` address doesn't load on the phone | Tailscale is not connected on the phone, or it is signed in to another account |
| Status `logged`: *no device has enabled notifications yet* | Do step 3 on at least one device |
| Status `failed`: *push service HTTP 401/403* | The VAPID key changed (`db/push` was deleted or copied from elsewhere): on each device tap **Turn off**, then **Enable notifications** again |
| Status `failed` with a connection error | The computer's network blocks the push services: `python -m sfa doctor` checks `fcm.googleapis.com`, `web.push.apple.com` and the Mozilla push service |
| A device disappeared from the list | Its browser reported the subscription as gone (app uninstalled, site data cleared): enable notifications on it again |
| `held` | Quiet hours (22:00–07:00): sent after 07:00 |

## Security, in short

- **No login, on purpose.** The dashboard listens only on `127.0.0.1`, and Tailscale Serve makes it reachable only from devices signed in to your tailnet.
- **Protection from other websites.** Requests that change something must carry a header that pages on other sites cannot add.
- **Unreadable push messages.** Messages are encrypted per device, so the push services (Google, Apple, Mozilla) only relay ciphertext.
- **The signing key stays put.** It lives in `db/push/`, which git ignores.
- **Nothing to sign up for besides Tailscale.** There are no accounts to create and no third-party project to set up.
