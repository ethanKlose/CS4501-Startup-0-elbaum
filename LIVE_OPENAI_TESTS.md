# Real, opt-in OpenAI tests

These tests make actual OpenAI requests and inspect actual model output. They
do not supply predetermined provider responses. The existing integration suite
still uses controlled providers so normal regression runs remain free.

## Setup

Keep your real key in the repository's local, ignored `.env`:

```env
OPENAI_API_KEY=your_actual_key
OPENAI_MODEL=gpt-4o-mini
ANTHROPIC_API_KEY=
```

From your existing Windows Git Bash checkout:

```bash
cd "/c/Users/Kunaal Sastry/OneDrive/Desktop/KS_LLM"
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

The default `python -m pytest -q` follows `testpaths = tests`; it does not collect
the separate `live_tests/` directory. Even explicitly running that directory
skips paid cases unless you supply `--run-live`.

## First: tiny real API check

```bash
.venv/Scripts/python.exe -m pytest live_tests --run-live --live-case smoke --live-max-calls 1 --live-budget-usd 0.01 -q -s
```

This permits one real paid request, caps its output at 32 tokens and disables
SDK retries through the application's real OpenAI adapter. It checks credentials,
provider JSON parsing and actual token-usage metadata. It is not a meal-planning
quality test.

## Then: actual application workflow

```bash
.venv/Scripts/python.exe -m pytest live_tests --run-live --live-case week --live-max-calls 2 --live-budget-usd 0.05 -q -s
```

This creates a temporary account and migrated SQLite database, submits a survey,
calls OpenAI through the actual application generation endpoint, and validates
the resulting week. It checks 21 distinct meal slots, the $200 estimated checkout
budget, encoded diet/schedule checks, persisted data, recipe and grocery pages,
ICS export, pinning, cooking status, ratings and check-in. Viewing and checking
off the saved plan must not add paid calls. TestClient exercises HTTP and
middleware but does not execute browser JavaScript.

Your personal database, account and saved plans are not used. Blank free text
avoids spending a separate request on preference extraction. The application may
try its normal repair/retry behavior, but the test transport blocks requests
that would exceed the shared paid-call budget.

## Optional: vegetarian generation

```bash
.venv/Scripts/python.exe -m pytest live_tests --run-live --live-case restricted --live-max-calls 2 --live-budget-usd 0.05 -q -s
```

This uses real model output and checks the selected vegetarian requirement in
both the validator and the saved ingredients. Live model failures remain failures;
the test never silently substitutes the offline planner.

`--live-case all --live-max-calls 3` selects all three cases, sharing three paid
attempts across the invocation. If an earlier case consumes the remaining calls,
later scenarios are explicitly skipped rather than reported as passed. Start
with individual scenarios. Running tests in parallel with pytest-xdist is blocked.

## Limits and recorded evidence

* Maximum 1-3 paid attempts per invocation, including failed requests/timeouts.
* At most 2,000 output tokens per request (32 for the tiny smoke check).
* Default conservative estimated run budget: $0.05; configurable up to $0.10.
* Only the standard OpenAI chat-completions endpoint and the specifically priced
  GPT-4o mini alias/snapshot are allowed. Streaming, tools, multiple completions
  and additional billed modalities are rejected.
* Input reservation uses request UTF-8 bytes plus a large framing allowance;
  output reservation assumes the entire allowed output is consumed. Reservations
  are not refunded after a timeout or HTTP failure.
* Estimated usage cost uses the actual returned prompt/completion counts and
  published base rates ($0.15/$0.60 per million input/output tokens), before cache
  discounts. These are estimates, not an invoice or account-wide spending cap.
  Check current pricing before changing models or reusing the suite in future.

The report at `test-results/live-openai-report.json` records the run time, model,
paid attempt count, HTTP statuses, returned token counts, estimated cost and each
case's actual pytest outcome. It excludes API keys, request headers, raw prompts
and provider error text. This directory is already ignored by Git.

An authentication error, provider outage, budget stop, invalid output or rejected
plan is not recorded as a successful live test. No live request was performed by
the authoring environment; run these locally with your own key to collect genuine
results. The free `tests/test_live_cost_guard.py` checks validate the safeguards
using controlled responses and are not live-model evidence.

Published pricing: https://developers.openai.com/api/docs/models/gpt-4o-mini
Usage fields: https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
