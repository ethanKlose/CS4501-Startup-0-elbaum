# Apply the KS_Work update to your existing Windows checkout

The download contains `KS_Work_updates.bundle` and a complete `KS_LLM` folder. To keep your current `.env`, virtual environment and database, import the bundle into your existing checkout rather than replacing the folder.

1. Extract the ZIP in Downloads and place `KS_Work_updates.bundle` directly in `C:\Users\Kunaal Sastry\Downloads`.
2. Stop the running app with Ctrl+C. In Git Bash, run:

```bash
cd ~/OneDrive/Desktop/KS_LLM
git status
git switch KS_Work
git fetch "$HOME/Downloads/KS_Work_updates.bundle" KS_Work
git merge --ff-only FETCH_HEAD
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Back up `platejoy.db` before migrating if it contains data you want to keep. Do not run `make reset` to upgrade. If you have uncommitted edits, commit or stash those before the merge. A fast-forward merge refuses to overwrite divergent commits; share that error instead of forcing it.

After reviewing and testing, push from your own terminal:

```bash
git push origin KS_Work
```

Nothing was pushed by this implementation. The bundle contains the new commits on the exact `origin/KS_Work` baseline fetched at the beginning of this work. A full fresh copy, with Git history, is also included for a clean installation.
