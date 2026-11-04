# KS_LLM

This is a complete clone of the PlateJoy `alpha-mvp` branch with the requested fixes committed on `KS_Work`.

For Windows setup, use [HOW_TO_RUN_LOCALLY.md](HOW_TO_RUN_LOCALLY.md). For applying this update to an existing checkout, use [APPLY_UPDATES.md](APPLY_UPDATES.md).

## Open on your Mac

1. Move `KS_LLM.zip` to your Desktop and extract it. The archive contains one folder named `KS_LLM`.
2. Open Terminal and run:

```bash
cd ~/Desktop/KS_LLM
make setup
make run
```

Requires Python 3.11 or newer. Open http://127.0.0.1:8000 in your browser. You can register an account, or use the demo login `demo@platejoy.dev` / `demo-password`.

The app works offline with the built-in recipe planner. To use live AI, add your own Anthropic key to the `.env` file created by setup and select a model available to your account. Restart the server afterward. Never commit `.env`.

## Review the separate commits

The `.git` directory is included even if Finder hides it. Do not initialize another Git repository inside this folder.

```bash
git status
git branch --show-current
git log --oneline origin/alpha-mvp..HEAD
```

`FIXES.md` maps the commits to the changes and records validation. Nothing has been pushed to GitHub. The remote remains https://github.com/ethanKlose/CS4501-Startup-0-elbaum.git.

## Run the checks

```bash
make test
```

For the browser flow, install Node.js 20 or newer and run:

```bash
npm ci
npx playwright install chromium
make test-e2e
```

The browser test starts and stops a separate local server with a disposable database. It uses no paid AI calls. On Linux, browser setup may require `npx playwright install --with-deps chromium`.

## Data behavior

Plans start next Monday. The Plan next week button advances the calendar; Regenerate week replaces the displayed future week. Confirmed groceries and cooked ingredients update the pantry once at check-in or successful plan replacement. Check-in closes cooking and shopping edits for that plan.

No database or private API key is included. Existing databases compatible with the starting alpha version do not need a reset for these fixes. `make reset` deletes local data, so use it only intentionally.
