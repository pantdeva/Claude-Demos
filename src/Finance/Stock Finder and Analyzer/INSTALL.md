# Installation guide — Stock Finder and Analyzer

This guide sets the app up on your own computer (Windows, macOS or Linux) and covers every remaining prerequisite. When you finish:
- a background service keeps the data, news, models and valuations up to date;
- a dashboard is available at **http://localhost:8000**.

Budget about 30 minutes of hands-on time. The first full data build then runs unattended for several hours (step 6).

---

## 0. Checklist of remaining prerequisites

| # | What | Why | Where in this guide |
|---|---|---|---|
| 1 | Python 3.10 or newer (3.12 recommended) and Git | Runs the app; downloads it | Step 1 |
| 2 | About 3 GB of free disk space and 8 GB of RAM | Database (~0.5 GB), FinBERT weights (~0.4 GB), caches | Step 1 |
| 3 | **A new NewsAPI key** (the old one was shared in a chat and should be treated as exposed) | Deep dives on the best leads | Step 4 |
| 4 | Your name and email for SEC requests | The SEC IPO-filings feed requires a contact in automated requests | Step 4 |
| 5 | Network access to the data sources listed in step 5 | Prices, statements, rates, news, filings | Step 5 |
| 6 | First full data build, including the remaining 443 companies of the model leaderboard | Only 383 of 826 companies were modelled in the cloud session | Step 6 |
| 7 | Start-on-boot service | Keeps everything current | Step 7 |
| 8 | Computer left on, and not sleeping, at the job times | Jobs run on a local clock | Step 7 |
| 9 | Optional: phone notifications (Android Studio, SFA Notifier app, Firebase project with Google sign-in, service-account key, `SFA_NOTIFY_EMAILS`) | Push alerts for leads, IPOs, valuations, digest and failures | [ANDROID.md](ANDROID.md) |
| 10 | Optional: tag `V2.0.0` on GitHub | Couldn't be pushed from the cloud session (HTTP 403) | Step 10 |

---

## 1. Install Python and Git

**Windows**
1. Install Python 3.12 from https://www.python.org/downloads/windows/ and tick **"Add python.exe to PATH"** in the installer. Or, in a terminal: `winget install Python.Python.3.12`
2. Install Git from https://git-scm.com/download/win, or: `winget install Git.Git`
3. Open a **new** Command Prompt and check:
   ```
   python --version
   git --version
   ```

**macOS**
```bash
brew install python@3.12 git        # Homebrew: https://brew.sh
python3 --version
```

**Linux (Debian/Ubuntu)**
```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
python3 --version                    # must show 3.10 or newer
```

In the rest of this guide, `python` means `python3` on macOS and Linux.

---

## 2. Download the app

The app is on the `stock-finder` branch of `pantdeva/Claude-Demos`:

```bash
git clone https://github.com/pantdeva/Claude-Demos.git
cd Claude-Demos
git checkout stock-finder
cd "src/Finance/Stock Finder and Analyzer"
```

The folder name contains spaces, so always put it in quotes. Every command below runs from this folder.

If the repository is private, Git will ask you to sign in. Use your GitHub username and a personal access token from GitHub → Settings → Developer settings → Tokens.

---

## 3. Create a virtual environment and install packages

**Windows (Command Prompt)**
```
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements.txt
```
(In PowerShell, activate with `.venv\Scripts\Activate.ps1`. If PowerShell blocks the script, first run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.)

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt
```

The packages are requests, PyYAML, NumPy, SciPy, pandas and openpyxl. PyTorch is **not** needed, because FinBERT runs in plain NumPy.

Activate the environment (`.venv\Scripts\activate` or `source .venv/bin/activate`) every time you open a new terminal for the app. The start-on-boot scripts in step 7 find it on their own.

---

## 4. Settings: NewsAPI key and SEC contact

1. **Get a new NewsAPI key.** Sign in at https://newsapi.org, open **Account**, and generate a new API key.
2. Copy the example settings file:
   - Windows: `copy sfa.env.example sfa.env`
   - macOS/Linux: `cp sfa.env.example sfa.env`
3. Open `sfa.env` in a text editor and fill in:
   ```
   NEWSAPI_KEY=your_new_key
   SFA_SEC_USER_AGENT=Your Name you@example.com
   ```
4. Save the file.

`sfa.env` is ignored by Git, so your key never reaches the repository. The app reads it on every start, including when it runs as a service.

You can use environment variables instead if you prefer: `setx NEWSAPI_KEY "..."` on Windows, or `export NEWSAPI_KEY=...` in `~/.zshrc` or `~/.bashrc`. A variable that is already set in the environment wins over `sfa.env`.

Optional settings, also in `sfa.env`:

| Variable | Default | Use |
|---|---|---|
| `SFA_FINBERT_DIR` | `db/models/finbert` | Where the FinBERT weights live, if you already have them |
| `SFA_DB` | `db/sfa.sqlite` | A different database file |
| `SFA_HOST` | `127.0.0.1` | `0.0.0.0` lets the phone open the dashboard (home Wi-Fi or Tailscale only) |
| `SFA_FCM_SERVICE_ACCOUNT` | — | Firebase service-account key file for phone notifications ([ANDROID.md](ANDROID.md)) |
| `SFA_NOTIFY_EMAILS` | — | Google account(s) whose signed-in phones receive notifications, comma-separated |
| `SFA_DASHBOARD_URL` | `http://localhost:8000` | Dashboard address the phone opens |

---

## 5. Check the computer is ready

```
python -m sfa doctor
```

The doctor checks:
- Python and packages;
- your settings;
- which data sources this computer can reach;
- the FinBERT weights;
- free disk space;
- what is in the database.

Every `FAIL` line must be fixed before going on. `WARN` lines reduce coverage but the app still runs.

The app talks to these sites over HTTPS. If you are on a work network or use a firewall, allow them:

| Purpose | Hosts |
|---|---|
| Prices, statements, listings, Yahoo news (**essential**) | `query1.finance.yahoo.com` |
| Interest rates and bond yields (**essential**) | `fred.stlouisfed.org` |
| FinBERT weights (first run only, ~440 MB) | `huggingface.co`, `*.hf.co` |
| NewsAPI deep dives | `newsapi.org` |
| News feeds | `feeds.bloomberg.com`, `www.ft.com`, `feeds.content.dowjones.io` (WSJ, MarketWatch), `news.google.com` (Reuters and IPO searches), `finance.yahoo.com`, `feeds.finance.yahoo.com`, `www.economist.com`, `economictimes.indiatimes.com`, `www.livemint.com`, `www.moneycontrol.com`, `pulse.zerodha.com`, `in.investing.com` |
| IPO filings | `www.sec.gov`, `www.sebi.gov.in` |
| Country risk premiums | `pages.stern.nyu.edu` (Damodaran) |
| Phone notifications (optional) | `fcm.googleapis.com`, `oauth2.googleapis.com` |

Two notes on the sources:
- **Unconfirmed feed addresses.** The news-feed addresses couldn't be tested from the cloud session. After the first news run, `python -m sfa feeds` (or the dashboard's **Service** page) shows which feeds work. A feed that fails three times in a row is read through a Google News search of its site instead, and it is retried once a day.
- **Damodaran's file.** It is downloaded the first time a valuation runs. Until it loads, valuations use a configured equity risk premium and say so in the report.

---

## 6. First full data build

Run these in order. Each step saves its progress, so you can stop with Ctrl+C and run the same command again later.

| Step | Command | Time (typical laptop) | What it does |
|---|---|---|---|
| a | `python -m sfa all` | 1–2 h | Universe (858 seed tickers → ~826 companies, ~2,200 listings), prices since 2005, fundamentals, Stage 0 classification |
| b | `python -m sfa models --jobs 4` | 2–6 h | Walk-forward forecasts for every company, model leaderboard, MPT vs 1/N, growth predictions. Set `--jobs` to your CPU cores minus one. |
| c | `python -m sfa finder` | 20–60 min the first time | News from all feeds and Yahoo, FinBERT scoring (downloads ~440 MB of weights once), rules A–D, IPO pipeline, leads, investment routes |
| d | `python -m sfa analyze` | 5–10 min | Module 13 integrated model and valuation for the top 25 leads |

Results appear in `exports/`:
- `summary.md`, `leaderboard.md` and `leads.md`;
- `analysis/<SYMBOL>.md` and `analysis/<SYMBOL>.xlsx`.

The same results are on the dashboard.

To see the dashboard straight away, without the background service:
```
python -m sfa web
```
Then open **http://localhost:8000**.

Prefer to let the service do the first build? Skip to step 7. The service runs the same jobs in the same order, but it works through them one at a time, so news and leads wait until the model run (b) has finished.

---

## 7. Run it as a service (starts with your computer)

`python -m sfa start` runs the scheduler and the dashboard together. The scripts below register it to start when you log in, restart it if it stops, and write a log to `logs/sfa.log`.

**Windows (Task Scheduler)**
```powershell
cd "deploy\windows"
powershell -ExecutionPolicy Bypass -File .\install_task.ps1
```
To remove it: `powershell -ExecutionPolicy Bypass -File .\uninstall_task.ps1`

**macOS (launchd)**
```bash
bash deploy/macos/install_launchd.sh
```
To remove it: `bash deploy/macos/uninstall_launchd.sh`

**Linux (systemd user service)**
```bash
bash deploy/linux/install_systemd.sh
sudo loginctl enable-linger $USER     # optional: keep it running when you are logged out
```
To remove it: `bash deploy/linux/uninstall_systemd.sh`

**Schedule** (from `sfa/config/jobs.yaml`; times are your computer's local time):

| Job | When | Does |
|---|---|---|
| prices | daily 06:30 | Daily prices for every home listing and index |
| classify | daily 07:00 | Stage 0 classification and exports |
| analyzer | daily 08:00 | Module 13 valuation of the top leads and new listings |
| news | hourly | RSS + Yahoo news, FinBERT scoring, linking |
| ipo_pipeline | every 3 h | IPO events, resolution of new listings |
| finder | every 6 h | Rules A–D, leads, NewsAPI deep dives, exports |
| fundamentals, universe, leaderboard | weekly | Statements, new listings, new forecast dates |
| notify | every 30 min | Push notifications to the Android app (see [ANDROID.md](ANDROID.md)); without a Firebase key they are only logged |

In India (IST), 06:30 picks up the previous US close. Indian prices for the day arrive the next morning. Change the times in `jobs.yaml` if you prefer.

**Keep the computer awake at those times:**
- Windows: Settings → System → Power → Sleep = Never (when plugged in).
- macOS: System Settings → Battery/Energy → "Prevent automatic sleeping…".
- Linux: your desktop's power settings.

A job missed while the computer was off runs at the next check after it comes back on.

---

## 8. Use the dashboard

Open **http://localhost:8000**:

| Page | Shows |
|---|---|
| Overview | Counts, top leads, chosen models, valuation verdicts, last job runs |
| Leads | Listed / new listings / IPO pipeline with rules A–D, model signal, verdict and best Indian-resident route; sortable |
| Company | Stage 0 categories, price chart, growth forecasts, news evidence, routes, valuation (with the Module 13 report and Excel model) and the company's model record. **Analyze now** re-runs the valuation. |
| Models | Leaderboard by market class, cell, sector group, exchange; MPT vs 1/N |
| Markets | Market class × sector map, classification counts, exchange-expansion suggestions, IPO events |
| Service | Settings detected, job schedule and runs, feed health |

The dashboard listens only on this computer. To open it from a phone, set `SFA_HOST=0.0.0.0` in `sfa.env` and restart. Then browse to `http://<your-computer's-IP>:8000` on the same Wi-Fi, or use the computer's Tailscale name from anywhere. It has no login, so do this only on a network you trust.

For **push notifications on your phone** (leads, IPOs, valuation changes, daily digest, failures), follow [ANDROID.md](ANDROID.md). It covers installing Android Studio, the Firebase project (Google sign-in, Firestore device registry, Cloud Messaging), building and installing the SFA Notifier app, and signing in.

---

## 9. Check it works

```
python tests/test_stage0.py && python tests/test_models.py && python tests/test_finder.py && python tests/test_analyzer.py && python tests/test_web.py && python tests/test_notify.py
python -m sfa doctor
python -m sfa jobs
```

All tests should print `ok`. `jobs` lists each job and its last run.

---

## 10. Updating and housekeeping

**Update to the latest version:**
```
git pull
pip install -r requirements.txt
```
Then restart the service:
- Windows: Task Scheduler → "Stock Finder and Analyzer" → End, then Run.
- macOS: `launchctl kickstart -k gui/$(id -u)/com.sfa.stockfinder`
- Linux: `systemctl --user restart sfa`

**Backups:** copy `db/sfa.sqlite` while the service is stopped. Everything else can be rebuilt.

**Add exchanges or companies:**
- Add the exchange to `sfa/config/exchanges.yaml`.
- Add tickers to `sfa/config/universe_seeds.yaml`.
- Run `python -m sfa all`.
- The **Markets** page suggests exchanges when news shows growing industries there.

**Review dated rules:** `sfa/config/routes.yaml` (LRS, TCS, IFSC Receipts, market access) and `sfa/config/market_classification.yaml` (MSCI/FTSE/S&P reviews) carry the date they were last checked. Review them after rule changes and annual index reviews.

**Optional: create the `V2.0.0` tag on GitHub.** Go to Releases → Draft a new release → tag `V2.0.0` on the `ML` branch.

---

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| `python` not found (Windows) | Reinstall Python with "Add to PATH", or use `py -3.12` instead of `python` |
| Yahoo errors / HTTP 429 | Too many requests. The app slows down and retries; rerun the same command later, since progress is saved. |
| FRED requests fail | Check `fred.stlouisfed.org` is allowed. FRED refuses browser-like User-Agents; the app already sends the plain one. |
| Feeds show `failing` on the Service page | The address may have changed or the site may block your network. The app falls back to a Google News search of that site. You can update the URL in `sfa/config/news_sources.yaml`. |
| `NEWSAPI_KEY not set` in the finder output | Check `sfa.env` (no spaces around `=`), then restart the service. Free plan: 100 requests a day; the app stops at 90. |
| `database is locked` | Two heavy commands are running at once (for example `models` while the service runs). Let one finish, or stop the service first. |
| Dashboard doesn't open | Check the service log `logs/sfa.log`. Port 8000 may be in use: `python -m sfa web --port 8010`. |
| FinBERT download fails | Allow `huggingface.co` and `*.hf.co`, or copy `config.json`, `vocab.txt` and `model.safetensors` from https://huggingface.co/ProsusAI/finbert into `db/models/finbert` |
| Valuation flags "risk-free rate is an approximation" | China/Taiwan have no FRED series. Set a current 10-year yield in `sfa/config/analyzer.yaml` → `risk_free.approximate`. |

---

Data from Yahoo Finance, FRED, MSCI/FTSE classifications and news sites carries licence limits. It is fine for personal research on your own computer, but not for redistribution. Everything the app produces is research output, not investment advice.
