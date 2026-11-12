# How to run PlateJoy locally

Use Python 3.12 (the version used for local verification). Python 3.11 is also the version configured for Docker and CI. Node.js is only needed for the optional browser test.

Run commands from the repository folder containing `app`, `requirements-dev.txt`, and this file. No API key is required for demo mode.

## Windows - Git Bash

Open Git Bash in your extracted `KS_LLM` folder. For your current location:

```bash
cd ~/OneDrive/Desktop/KS_LLM
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
cp -n .env.example .env
.venv/Scripts/python.exe -m scripts.seed
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

You do not need `make` or virtual environment activation. `cp -n` preserves an existing `.env` file.

## Windows - Command Prompt

```bat
cd /d "C:\Users\Kunaal Sastry\OneDrive\Desktop\KS_LLM"
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if not exist .env copy .env.example .env
.venv\Scripts\python.exe -m scripts.seed
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

These commands are for Command Prompt, not PowerShell.

## macOS or Linux

With Python 3.11 or 3.12 installed as `python3`:

```bash
cd ~/Desktop/KS_LLM
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cp -n .env.example .env
.venv/bin/python -m scripts.seed
.venv/bin/python -m uvicorn app.main:app --reload
```

If `make` is installed, `make setup` followed by `make run` is an alternative on macOS/Linux.

## Open the app

Keep the terminal running and open **http://127.0.0.1:8000** in your browser.

Register an account or use:

- Email: `demo@platejoy.dev`
- Password: `demo-password`

Complete your preferences to generate a plan. Without an API key, the app displays Demo mode and uses the built-in recipe planner.

Press **Ctrl+C** in the server terminal to stop it.

## Start it again later

After the initial setup, you only need the server command from your repository folder.

Windows Git Bash:

```bash
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Windows Command Prompt:

```bat
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

macOS/Linux:

```bash
.venv/bin/python -m uvicorn app.main:app --reload
```

## Optional live AI

1. Open the `.env` file created during setup.
2. Set `ANTHROPIC_API_KEY` to your own key.
3. Set `ANTHROPIC_MODEL` to a model available to your API account.
4. Restart the server.

Live calls may incur API charges. Keep `.env` private and do not commit it. Live Anthropic calls were not part of the local verification.

## Run the Python tests

Stop the server first if you want to use the same terminal.

Windows Git Bash:

```bash
.venv/Scripts/python.exe -m pytest -q
```

Windows Command Prompt:

```bat
.venv\Scripts\python.exe -m pytest -q
```

macOS/Linux:

```bash
.venv/bin/python -m pytest -q
```

## Run the integration tests

With the virtual environment active, run:

```bash
python -m pytest tests/integration -m integration -q --strict-markers --junitxml=test-results/integration.xml
```

On Windows Git Bash you can also use `.venv/Scripts/python.exe` instead of
`python`. These 70 cases use temporary databases and controlled provider I/O;
no paid API key or actual email delivery is required. See
`INTEGRATION_TESTING.md` for the workflow matrix and recorded results.

## Optional browser test

Install Node.js 20 or newer, then run these commands from the repository folder:

```bash
npm ci
npx playwright install chromium
npm run test:e2e
```

The browser test uses a disposable database and starts its own server on port 8123. It does not use a paid API key. On Linux, browser dependencies may require `npx playwright install --with-deps chromium`.

On Windows Git Bash, select the virtual environment before running the browser test:

```bash
export PYTHON="$PWD/.venv/Scripts/python.exe"
npm run test:e2e
```

In Command Prompt, select it this way:

```bat
set "PYTHON=%CD%\.venv\Scripts\python.exe"
npm run test:e2e
```

## Troubleshooting

### `make` is not recognized

Use the direct commands above. Git Bash does not necessarily include `make`, and the provided Makefile uses macOS/Linux virtual environment paths.

### `py` or Python 3.12 is not found

On Windows, `py -0p` lists Python versions installed through the launcher. If Python 3.11 is installed, replace `py -3.12` with `py -3.11`. Otherwise install Python 3.12 and reopen your terminal. If the launcher is unavailable but `python --version` reports Python 3.11 or 3.12, use `python -m venv .venv` for the first setup command.

### `.venv/Scripts/python.exe` does not exist

The virtual environment creation command must finish successfully first. Make sure your terminal is in the repository folder. A virtual environment created on macOS/Linux cannot be reused on Windows; recreate it locally.

### `No module named app` or `scripts`

Run from the folder containing `app/` and `scripts/`. Use the `-m scripts.seed` command shown above.

### Port 8000 is already in use

Stop the other running server, or append `--port 8001` to the Uvicorn command and open http://127.0.0.1:8001 instead.

### Existing database reports missing columns

Do not delete your database unless you intend to lose its accounts and saved plans. These fixes need no schema reset for a database compatible with the starting alpha version. A database from an older schema needs separate attention; back it up before making changes.


## Import the story-completion commits on Windows Git Bash

Extract the downloaded package to your Desktop so `KS_All_Stories.bundle` is directly on the Desktop. Keep your existing repository, virtual environment and database.

```bash
cd "$HOME/OneDrive/Desktop/KS_LLM" &&
git switch KS_Work &&
git fetch "$HOME/OneDrive/Desktop/KS_All_Stories.bundle" KS_Work &&
git merge --ff-only FETCH_HEAD &&
git push origin KS_Work
```

Then update development tools with `python -m pip install -r requirements-dev.txt` from the active environment. If Git reports uncommitted changes or that fast-forward is impossible, stop and resolve that message; these instructions do not discard local work or force-push.

Run automated tests with `python -m pytest -q`. Measure Python application coverage with `python -m coverage run --source=app -m pytest -q` followed by `python -m coverage report`. Browser checks are `npm run test:e2e` and `npm run test:e2e:audit` after `npm ci` and `npx playwright install chromium`. Manual procedures and blank execution logs are in `MANUAL_TESTS.md`.
