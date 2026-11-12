# Kroger grocery integration

This update adds a real Kroger Public API adapter and an explicit product-review
flow to the existing PlateJoy app. Google Calendar, its colors, existing plans,
inventory and OpenAI settings are preserved. There are no new Python dependencies
beyond the earlier Beta integration requirements.

## What it does

1. Connect a shopper's Kroger account using OAuth (the app never sees their password).
2. Find nearby Kroger-family stores by US ZIP and choose Pickup or Delivery.
3. Start a review of the current plan's unchecked grocery ingredients. Existing
   pantry stock and confirmed purchases are excluded.
4. Search Kroger products for each ingredient at that store and fulfillment type.
5. Choose actual products and **retail package counts**. Recipe cups/ounces are
   shown separately; no guessed conversion silently turns them into packages.
6. Review the consolidated products, package sizes, quantities, available prices
   and omitted ingredients, then explicitly add the selected products to the cart.
7. Open Kroger, confirm the same store/fulfillment, review the cart and check out there.

The chosen store filters product search. The public cart-add request does not
set your Kroger account's preferred store. Final stock, prices, fees, taxes,
substitutions and checkout are controlled by Kroger. Links to search each UPC
help you inspect product labels before confirming a selection. Search results
are not validated dietary substitutions.

The app does not place orders, handle payments, read your entire cart, delete
cart items or mark PlateJoy groceries purchased just because they were added.
The existing optional Instacart adapter remains available to accounts that already
have access, but Kroger is the new primary shopping option on the Grocery page.

## Developer account setup

First confirm that your account can register an application and obtain the Public
API subscriptions. This development environment has no Kroger credentials and
has not verified your account's eligibility or a live OAuth grant. Documentation
availability alone does not guarantee registration/access for a particular account.

1. Open https://developer.kroger.com/ and create/sign in to a developer account.
2. Register an application named **PlateJoy Local**. Select the public Products,
   Locations and Cart APIs as available in the portal. Do not select partner-only
   Carts/Checkout APIs. The app requests these OAuth scopes:

   ```text
   product.compact
   cart.basic:write
   ```

3. Register this exact redirect URI:

   ```text
   http://127.0.0.1:8000/integrations/kroger/callback
   ```

4. Copy the application's Client ID and Client Secret into your local ignored
   `.env`. Keep your existing settings, including the working session secret and
   Google encryption key. Add only:

   ```env
   KROGER_CLIENT_ID=your_kroger_application_client_id
   KROGER_CLIENT_SECRET=your_kroger_application_client_secret
   KROGER_REDIRECT_URI=http://127.0.0.1:8000/integrations/kroger/callback
   ```

Kroger tokens reuse your existing `GOOGLE_TOKEN_ENCRYPTION_KEY` for encryption;
Google OAuth credentials are not used to authenticate Kroger. For a standalone
Kroger setup you can instead set `KROGER_TOKEN_ENCRYPTION_KEY` to a private Fernet
key. Keep encryption keys stable. Nothing needs to be shared in chat or committed.

5. Stop the local server with Ctrl+C, then restart:

   ```bash
   .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
   ```

6. Open http://127.0.0.1:8000/integrations. Sign in with your existing **PlateJoy**
   login, choose **Connect Kroger**, and sign in on Kroger with your **shopper**
   account when prompted. The developer, shopper and local PlateJoy emails do not
   have to be identical.
7. Open **Grocery → Shop with Kroger**, choose a store and fulfillment type,
   start a review, search and choose products, then review and explicitly confirm.

OAuth uses a confidential server client, browser-bound state, a one-use callback
with a ten-minute expiry, and PKCE S256. Actual provider acceptance of the local
redirect URI, scopes and OAuth exchange still needs your registered app's live
check; no successful live login is claimed by the offline tests.

## Duplicate prevention and recovery

Kroger's public `/cart/add` operation is additive. A second request can add more
of the same products, even though its HTTP method is PUT.

- Cart submission is saved as pending in the database **before** the API request.
  Repeated or concurrent submissions of the same review cannot submit it again.
- A successful transfer has a saved receipt. Starting another new review is a
  deliberate new transfer that may add more quantities; inspect the receipt/cart.
- A timeout, redirect, 5xx or unexpected result can mean the cart changed without
  confirmation. The app blocks fresh transfers until you check your Kroger cart
  and explicitly acknowledge that you want to allow another review.
- If the process crashes while sending, wait at least one minute, inspect Kroger,
  then acknowledge. Disconnecting or reconnecting does not silently clear an
  unresolved transfer marker.
- Changing a product quantity invalidates the old confirmation. Changing the
  grocery list, store, connection or plan invalidates an old review.

A review expires after 30 minutes, offers up to five product matches per search,
and supports up to 100 ingredient rows, 50 distinct cart products and 1–99 packages
per product. These are application safeguards, not claims about Kroger's limits.
Unselected ingredients are visibly omitted from the transfer.

## Automated tests (no real provider requests)

```bash
.venv/Scripts/python.exe -m pytest tests/integration/test_kroger.py tests/test_kroger_boundaries.py -q
.venv/Scripts/python.exe -m pytest -q
```

The regular integration tests use the real HTTP routes, authentication, CSRF,
Alembic migrations, SQLite database and service code. Only external Kroger HTTP
responses are controlled, to test both success and otherwise hard-to-reproduce
errors without touching a cart. Tests cover OAuth state/replay/expiry, credential
encryption, token refresh/restart, store selection, UPC serialization, product
choice, package counts, explicit confirmation, stale reviews, duplicate and
concurrent requests, ambiguous write recovery and preserving inventory.

## Real read-only smoke test (optional)

After connecting a real account through the app, add these local test settings:

```env
LIVE_KROGER_USER_EMAIL=your_local_platejoy_login_email
LIVE_KROGER_ZIP=22903
```

Run:

```bash
.venv/Scripts/python.exe -m pytest live_integrations --run-integrations --integration-service kroger -q -s
```

It loads that account's encrypted credentials, refreshes if needed, searches
nearby stores and looks up rice. **It does not add anything to a cart, place an
order or call OpenAI.** It records real outcomes in the ignored
`test-results/live-integrations-report.json`. Missing credentials/access/no nearby
store produce a clear failure after opting in, not a fabricated pass.

The actual cart-write acceptance test is the explicit UI confirmation in the
manual checklist. It adds real products to your shopper cart and requires you
to remove unwanted test items manually on Kroger. The Public API adapter does not
have a cart-read or cart-delete capability to clean them up automatically.

## Official API references

- Developer portal: https://developer.kroger.com/
- Kroger's official Public API workspace and registration instructions:
  https://www.postman.com/kroger/the-kroger-co-s-public-workspace/overview
- Public API request documentation (OAuth, Locations, Products, Cart):
  https://www.postman.com/kroger/the-kroger-co-s-public-workspace/documentation/ki6utqb/kroger-public-apis
- Public Cart API: https://developer.kroger.com/api-products/api/cart-api-public

The implementation calls only `https://api.kroger.com/v1` endpoints. All external
errors are reduced to safe codes; tokens and raw provider bodies are not shown in
pages or reports. OAuth tokens are encrypted server-side and bound to the local
user/provider. Disconnect removes local Kroger credentials; revoke application
access through Kroger's account controls if you also want to withdraw the grant.
