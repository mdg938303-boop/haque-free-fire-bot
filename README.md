# 💎 Free Fire Diamond Top-Up Bot (Telegram-only Admin Panel)

A single Telegram bot that serves **both** customers and the admin — there is no
separate website. Admin access is granted purely by Telegram numeric ID
(`TELEGRAM_ADMIN_IDS` in `.env`); message `/admin` to the bot from that account to get
the full admin menu (Providers, Packages, Orders, Deposits, Users, Finance, Broadcast,
Settings, Logs).

Built for **Render's free tier**: one process, one Web Service, no webhooks required.
Order status updates are fetched by **polling** each provider on an interval instead of
waiting for provider webhooks, so no public callback URL is needed.

## Stack
- **Backend:** Python 3.11+, aiogram 3 (Telegram bot), FastAPI (health check only)
- **Database:** PostgreSQL, SQLAlchemy 2.0 (async), Alembic migrations

## Architecture at a glance
```
app/
├── main.py                 # Single entrypoint for Render: FastAPI /health + starts the
│                              bot polling loop and the order-status poller as background
│                              asyncio tasks (uvicorn app.main:app is all you deploy)
├── config.py                # Settings loaded from .env
├── database.py               # Async SQLAlchemy engine/session
├── models/                    # All DB tables (no admin_users table anymore)
├── core/                       # encryption, exceptions, idempotency, logging
├── providers/
│   ├── base.py                 # Generic adapter interface every provider must implement
│   ├── epinby.py                # EpinBy.com adapter (built from their public API docs)
│   └── registry.py               # Maps ApiProvider.code -> Adapter class
├── services/
│   ├── wallet_service.py          # Row-locked, transactional balance changes
│   ├── order_service.py            # Full order safety sequence + retry
│   ├── order_polling_service.py     # Polls provider order status (replaces webhooks)
│   ├── deposit_service.py            # Approve/reject deposits
│   ├── referral_service.py            # Signup attribution + bonus payout
│   ├── provider_service.py             # Provider CRUD/test-connection helpers
│   └── settings_service.py              # Key-value app settings (general/referral/topup)
└── bot/
    ├── bot.py                      # Dispatcher wiring + background poll loop
    ├── keyboards.py                  # All reply/inline keyboards (user + admin)
    ├── states.py                      # FSM states (user + admin flows)
    └── handlers/
        ├── admin.py                    # 👑 The entire Admin Panel, Telegram-native
        ├── start.py, uid_check.py, purchase.py, wallet.py, deposit.py, orders.py

run_bot.py                    # Optional: run only the bot, no HTTP server (local dev)
scripts/seed_settings.py       # Seed default settings rows after first migration
alembic/                        # DB migrations
```

### Adding a new Top-Up API provider (no code changes to the order engine)
1. Write `app/providers/provider_x.py` implementing `BaseProviderAdapter`
   (`validate_player`, `create_order`, `get_order_status`, `get_balance`).
2. Register it: add `"provider_x": ProviderXAdapter` to `ADAPTER_REGISTRY` in
   `app/providers/registry.py`.
3. In the bot, message `/admin` → **🔌 Providers → ➕ Add Provider**, and pick your new
   code from the list, then fill in base URL / API key / endpoints / priority.
4. Map it to a Package: **📦 Packages → ➕ Add Package**.

`order_service.py` and the order poller never reference any provider by name — they only
call `get_adapter(provider)` and use the interface.

### EpinBy integration
Implemented against Epinby's public documentation (`https://www.epinby.com/docs`):
- Base URL: `https://www.epinby.com/api/v1`, auth header `X-API-KEY`
- `POST /validate-player`, `POST /order` (with `X-Idempotency-Key`), `GET /order/{id}`, `GET /getMe`

Webhooks are not used in this build (Telegram-admin + polling setup), so you do not need
to configure a callback URL with Epinby. `app/providers/epinby.py` also implements
`verify_webhook_signature` / `parse_webhook_event` for `X-GAMEX-Signature` webhooks in
case you want to switch to instant webhook-driven updates later on a host that supports a
public HTTP endpoint.

## Order safety sequence (`order_service.create_order`)
1. User authentication (Telegram)
2. Package active check
3. UID validation via the package's active provider
4. Player name confirmation (shown to user before payment)
5. Wallet balance check
6. Idempotency-key based order lock (DB unique constraint)
7. Wallet debit **before** calling the provider (row-locked, transactional)
8. Provider order creation
9. Provider response persisted (`order_logs`)
10. Status kept in sync by the background poller (`ORDER_POLL_INTERVAL_SECONDS`, default 45s)
11. `COMPLETED` → finalized
12. Permanent failure → automatic wallet refund (guarded so it only ever fires once)

## Installation

### 1. Prerequisites
- Python 3.11+
- PostgreSQL 14+ (Render offers a free Postgres instance too)
- A Telegram bot token from @BotFather
- Your own Telegram numeric user ID (message @userinfobot to get it)
- An EpinBy reseller account + API key

### 2. Local setup
```bash
git clone <this-repo>
cd freefire-topup-bot
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: DATABASE_URL(s), TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_IDS, FIELD_ENCRYPTION_KEY
```

Generate the field-encryption key (encrypts provider API keys at rest):
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# paste into FIELD_ENCRYPTION_KEY in .env
```

### 3. Database + migrations
```bash
alembic revision --autogenerate -m "init schema"
alembic upgrade head
python scripts/seed_settings.py
```

### 4. Run it locally
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
This single command starts the health endpoint, the bot, and the order poller together.
(Or, if you don't want any HTTP server at all for local testing: `python run_bot.py`.)

Open Telegram, message your bot `/start` (as a normal user) or `/admin` (from a
`TELEGRAM_ADMIN_IDS` account) to see the Admin Panel menu.

### 5. First-time Admin Panel setup (inside Telegram)
1. `/admin` → **🔌 Providers → ➕ Add Provider** — add EpinBy (base URL, API key).
2. **📦 Packages → ➕ Add Package** — create diamond packages, map each to its Provider Product ID.
3. **⚙️ Settings → 💳 Payment Methods → ➕ Add** — add bKash/Nagad/Rocket receiving numbers.
4. **⚙️ Settings** — set Bot Username (for referral links), Support Username, referral bonus.

## Deploying to Render (free tier) — no terminal / no Shell needed

Render's free plan doesn't include the Shell tab, and this repo doesn't require it: the
app creates its own database tables and default settings automatically the first time it
starts (see `init_db()` in `app/database.py`, called from `app/main.py`'s startup). You
never need to run `alembic upgrade head` by hand.

### 1. Get the code onto GitHub (from a phone)
Easiest phone-friendly option — **GitHub's website, no git commands**:
1. Open github.com in your phone's browser, log in (or sign up).
2. Create a new repository (name it e.g. `freefire-topup-bot`), keep it **Private**.
3. On the empty repo page, tap **"uploading an existing file"**.
4. From your file manager, select every file/folder from the extracted zip and upload
   them (GitHub's mobile upload keeps folder structure if your browser supports folder
   picking; if not, upload folder-by-folder — `app/`, `alembic/`, then the root files).
5. Commit.

(If you'd rather use real git from your phone: install **Termux** (Android) and run
`git clone`, `git add`, `git commit`, `git push` from there — but the web upload above
needs nothing extra installed.)

### 2. Create the free Postgres database
1. On render.com (mobile browser is fine) → **New → PostgreSQL**
2. Name it, pick **Free** plan → Create Database
3. Once it's ready, open it and copy the **Internal Database URL** — you'll need it next.

### 3. Create the Web Service
1. **New → Web Service** → connect the GitHub repo you just created
2. **Build Command:** `pip install -r requirements.txt`
3. **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. **Plan:** Free

### 4. Set Environment Variables
In the Web Service's **Environment** tab, add:

| Key | Value |
|---|---|
| `APP_SECRET_KEY` | any long random string you type |
| `DATABASE_URL` | the Internal Database URL, but change `postgresql://` at the start to `postgresql+asyncpg://` |
| `DATABASE_URL_SYNC` | the same URL again, but change `postgresql://` to `postgresql+psycopg2://` |
| `TELEGRAM_BOT_TOKEN` | from @BotFather |
| `TELEGRAM_ADMIN_IDS` | your Telegram numeric ID (message @userinfobot to get it) |
| `FIELD_ENCRYPTION_KEY` | see below |

**Generating `FIELD_ENCRYPTION_KEY` without a computer:** open any free online Python
runner on your phone (e.g. search "online python compiler", or use Programming Hub /
Pydroid 3 if you have an Android app for it) and run:
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```
Copy the output string into `FIELD_ENCRYPTION_KEY`.

### 5. Deploy
Save the environment variables → Render redeploys automatically. Watch the **Logs** tab
(in the browser) for `Creating database tables if they don't exist yet...` followed by
`Application startup complete` — that means tables were created and the bot is live.

### 6. Test from Telegram
1. Message `/start` to your bot — the customer menu should appear.
2. Message `/admin` from your `TELEGRAM_ADMIN_IDS` account — the Admin Panel menu should appear.
3. `/admin` → **🔌 Providers → ➕ Add Provider** → add EpinBy.
4. **📦 Packages → ➕ Add Package** → create your diamond packages.
5. **⚙️ Settings → 💳 Payment Methods → ➕ Add** → add bKash/Nagad/Rocket numbers.

### 7. Keep it awake
Free Web Services sleep after ~15 minutes idle. Set up a free monitor on
[UptimeRobot](https://uptimerobot.com) (their site works fine on mobile) to ping
```
https://your-app-name.onrender.com/health
```
every 5 minutes, so the bot stays responsive.


## Environment Variables
See `.env.example` for the full list.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` / `DATABASE_URL_SYNC` | Postgres connection (async for the app, sync for Alembic) |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_ADMIN_IDS` | Comma-separated Telegram numeric IDs — **this is the entire admin auth system** |
| `PORT` | Render sets this automatically; leave as default locally |
| `FIELD_ENCRYPTION_KEY` | Fernet key — encrypts provider API keys in the DB |
| `ORDER_POLL_INTERVAL_SECONDS` | How often the poller checks open order statuses (default 45s) |

**Never commit `.env`.** Rotate `FIELD_ENCRYPTION_KEY` and provider API keys immediately
if they are ever exposed.

## Security checklist already implemented
- Provider API keys encrypted at rest (Fernet / `core/security.py`)
- Admin access is allow-listed by Telegram ID only — no separate credentials to leak
- Order idempotency key (unique DB constraint) — prevents duplicate orders/double-charging
- Wallet mutations always row-locked (`SELECT ... FOR UPDATE`) and logged to `wallet_transactions`
- All admin actions written to `admin_logs` (who, what, old value, new value, when)
- User-facing error messages never leak provider/internal error detail (see `core/exceptions.py`)

## What you still need to do
- Run `alembic revision --autogenerate` once against your real Postgres instance and
  review the generated migration before applying it in production.
- Confirm your Epinby account's exact product IDs for each diamond package (`/admin` →
  Packages → Provider Product ID) — these are account-specific and not guessable.
- If polling proves too slow for your volume, lower `ORDER_POLL_INTERVAL_SECONDS`, or move
  to a host that supports a public HTTPS endpoint and re-enable webhooks using the
  `verify_webhook_signature` / `parse_webhook_event` methods already implemented in
  `app/providers/epinby.py`.
