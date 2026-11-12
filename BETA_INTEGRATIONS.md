# Beta integrations: setup, behavior and verification

This update targets `KS_Work` at `a76de37` (the merge with 581 passing tests).
It includes the earlier, unapplied `KS_OpenAI_Live_Tests.patch` additions too.
Apply this combined patch once; do not apply the previous version first.

## What changed

- **Google Calendar:** Connect through OAuth, then explicitly sync the current
  plan's meals, outside meals and scheduled cooking/prep blocks to the connected
  Google account's primary calendar. Repeated sync updates existing events,
  removes obsolete PlateJoy events for that week and preserves other weeks and
  personal events. Stable IDs survive plan regeneration. Restoring skipped meals
  also restores their deleted Google events when Google retains their details.
- **Instacart:** The existing real Developer Platform adapter remains in use.
  Grocery now has **Review list first**, showing the exact unchecked-item payload,
  quantity caveats and a confirmation action. Pantry stock and confirmed purchases
  remain excluded. Existing send, caching and failure handling are retained.
- **Discoverability:** Connected apps is available in the account menu and from
  the plan/calendar and grocery pages, with honest configured/unconfigured status.
- **Calendar fix:** Skipped meals no longer leave orphan cooking blocks in either
  the calendar-file export or the new Google sync.
- **Tests:** Free deterministic HTTP/database integration tests, boundary tests,
  and separate opt-in tests that actually call OpenAI, Google and Instacart.

Google sync is explicit and one-way. Click **Sync current week** after changing
or regenerating a plan. It does not run on a schedule. Google-side edits do not
change the app and may be overwritten on resync. Disconnect removes encrypted
credentials and attempts Google revocation; existing calendar events remain.

## Install and run (Windows Git Bash)

```bash
cd "/c/Users/Kunaal Sastry/OneDrive/Desktop/KS_LLM"
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Use http://127.0.0.1:8000 consistently (not a mixture of localhost and 127.0.0.1).
Restart the server after editing `.env`. No database reset or new migration is
needed; encrypted credentials live in the existing per-user preference table.

## Google Calendar setup

An OpenAI key cannot authenticate Google Calendar. The user must consent to a
Google OAuth Web application client.

1. In your Google Cloud project, enable **Google Calendar API**.
2. Configure the OAuth consent screen / Google Auth Platform. For local testing,
   add the Google accounts you will connect as test users if the app is in Testing.
3. Create an OAuth client with application type **Web application**. Register this
   exact authorized redirect URI:
   `http://127.0.0.1:8000/integrations/google/callback`.
4. Generate a private session secret and a separate encryption key locally:

   ```bash
   .venv/Scripts/python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
   .venv/Scripts/python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

5. Put the first output in `SECRET_KEY`, the second in
   `GOOGLE_TOKEN_ENCRYPTION_KEY`, and add your Google credentials to ignored `.env`:

   ```env
   SECRET_KEY=paste_the_first_generated_value
   GOOGLE_CLIENT_ID=your_web_client_id
   GOOGLE_CLIENT_SECRET=your_web_client_secret
   GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/integrations/google/callback
   GOOGLE_TOKEN_ENCRYPTION_KEY=paste_the_second_generated_value
   TIMEZONE=America/New_York
   ```

6. Restart, sign in to PlateJoy, generate/open your current plan, choose **Sync to
   Google Calendar**, then **Connect Google Calendar** and grant consent.
7. Click **Sync current week**. Check the connected account's primary Google
   calendar for the meals and **Cook …** prep blocks. Sync again: the result should
   show unchanged events, not duplicate copies.

The app requests `calendar.events.owned` (events on calendars you own). The scope
permits more than this application needs on its primary calendar; app code limits
writes/deletions to events marked for this installation, local user and week. It
never imports personal events into meal planning. OAuth state is browser-bound,
one-use and expires after ten minutes; PKCE protects code exchange. Tokens are
Fernet-encrypted on the server, not placed in the signed browser session.

Keep the encryption key stable and private with your database backups. Losing or
changing it requires reconnecting accounts and can leave previous events behind;
new ownership tags intentionally do not claim old events. Changing `SECRET_KEY`
signs everyone out. Google test-mode grants may expire and require reconnecting.
Production HTTPS, consent-screen requirements and any Google verification remain
account/deployment setup work, not something the patch can complete for you.

Official references:
- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.google.com/workspace/calendar/api/auth
- https://developers.google.com/workspace/calendar/api/guides/create-events
- https://developers.google.com/workspace/calendar/api/v3/reference/events/list

## Instacart setup

Get your own Instacart Developer Platform development key and access. Put it in
`.env` (separate from OpenAI and Google credentials):

```env
INSTACART_API_KEY=your_instacart_development_key
INSTACART_ENV=development
```

Restart, generate a plan, open **Grocery → Review list first**, then send the list.
The adapter uses the real `POST /idp/v1/products/products_link` endpoint. It sends
unchecked ingredients and supported measurements, caches unchanged list links,
validates returned HTTPS Instacart URLs and never submits an order or payment.
Review matches, allergens, quantities, package sizes and current prices there.
An unsupported measurement stays in the item description rather than being
silently converted to a false quantity.

For production, obtain a production key and use `INSTACART_ENV=production`.
Key approval/access and actual shopping-page rendering require your account.

Official contract:
https://docs.instacart.com/developer_platform_api/api/products/create_shopping_list_page

## Free regression and integration tests

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m pytest tests/integration/test_google_calendar.py tests/integration/test_shopping_provider.py tests/test_beta_integrations.py -q
```

These execute real routes, sessions, CSRF, migrations, SQLite persistence and
adapter serialization. External HTTP responses are controlled to reproduce
failures reliably without charging accounts. They do not prove live provider
credentials, Google consent or real Instacart availability. They remain meaningful
regression tests; the live tests below complement them.

Covered flows include consent state/PKCE, expiry/replay, cancellation, encrypted
credentials, refresh after restart, duplicate prevention, regenerated weeks,
partial remote writes followed by retry, skipped/restored meals, ownership,
stale forms, CSRF, pagination, authentication/permission/quota failures, DST
conversion, Instacart preview fidelity, cache expiry and quantity/size boundaries.

## Real, opt-in Google and Instacart tests

These are outside default pytest discovery and require an explicit flag. They
make no LLM requests and consume no OpenAI tokens. Normal tests do not run them.
Start with Google only after connecting an account in the app. In ignored `.env`,
identify your **local PlateJoy login email**, not necessarily your Google email:

```env
LIVE_GOOGLE_USER_EMAIL=your_local_platejoy_login_email
```

```bash
.venv/Scripts/python.exe -m pytest live_integrations --run-integrations --integration-service google -q -s
.venv/Scripts/python.exe -m pytest live_integrations --run-integrations --integration-service instacart -q -s
```

Google uses that local account's saved consent, refreshes credentials if needed,
creates **one future temporary event**, resyncs without duplication, changes its
description and removes it in `finally`. Its random ownership namespace cannot
match any real plan. Roughly seven Calendar requests, plus a token refresh if
needed. If cleanup is blocked, the test fails and asks you to remove the future
**PlateJoy integration test — temporary** event manually. It does not alter your
meal plan, groceries or personal events.

Instacart creates one real shopping-list link for rice. It never creates a cart
or order. The report records outcomes and request effects, not credentials or
raw provider bodies: `test-results/live-integrations-report.json` (ignored).
If credentials are missing after opting in, the test fails clearly instead of
pretending the integration passed. Neither live test was executed in this patch's
development environment because connected account credentials were unavailable.

## Real OpenAI tests and your $5 balance

The earlier cost-guarded tests are included unchanged. See `LIVE_OPENAI_TESTS.md`.
The smallest real key check is:

```bash
.venv/Scripts/python.exe -m pytest live_tests --run-live --live-case smoke --live-max-calls 1 --live-budget-usd 0.01 -q -s
```

That permits one paid request with a 32-token output cap. Full-week generation
uses a separate opt-in command documented there. The dollar limit is a conservative
local estimate, not an account billing cap. No paid OpenAI request was made here.

## Roadmap completion status

| Roadmap statement | Evidence in code | Remaining acceptance work |
| --- | --- | --- |
| Meals and prep blocks add to Calendar | OAuth connection, direct sync, deterministic event mapping and integration tests | Configure your Google project, grant real consent and run the live/manual checks |
| Grocery lists transfer to Instacart | Existing real API adapter plus new payload preview and regression tests | Obtain Instacart access, run the live link test and review the shopping page |
| Resolve all critical Alpha bugs | Existing audited fixes retained; one skipped-prep export bug fixed here; full suite rerun | Team must triage any remaining live/user-reported critical bugs; passing tests cannot prove none exist |
| Implement prioritized feedback | Connected-app discoverability, quantity review and sync feedback added; existing rating/check-in feedback retained | Team must confirm its actual prioritized backlog. This patch does not assume every requested customization is complete |

Do not mark Beta fully accepted from offline test totals alone. Time-savings and
user-preference studies remain deferred as previously requested. No human test
results, user quotes or feedback were invented.
