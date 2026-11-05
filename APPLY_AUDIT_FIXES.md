# Apply the audit fixes to your existing Windows checkout

The update bundle contains the separate audit-fix commits on `KS_Work`, based on
the version you already pushed: `359263f4687565cad789071c969d28df5fcece2e`.

1. Stop the app with Ctrl+C.
2. Extract `KS_Audit_Fixes.bundle` from the download and place it directly in Downloads.
3. Open Git Bash in your existing checkout. Commit or stash any uncommitted edits before merging.

```bash
cd ~/OneDrive/Desktop/KS_LLM
git status
git switch KS_Work
git fetch "$HOME/Downloads/KS_Audit_Fixes.bundle" KS_Work
git merge --ff-only FETCH_HEAD && git push origin KS_Work
```

The merge advances your **local KS_Work branch**. The push then updates **KS_Work
on GitHub**. No new branch or merge commit is created. If the fast-forward is
refused, stop and inspect the error; do not force-push or reset your work.

Your `.env`, database and virtual environment are retained. These audit fixes
add no database migration or new Python dependency. Start the app again with:

```bash
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

You can verify the new code locally:

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m scripts.audit_correctness --repeats 3
```

See `AUDIT_FIXES.md` for the results and `CORRECTNESS_VALIDATION.md` for the
correctness-review workflow. Human time-savings and preference measurement are
deferred; no participant results have been invented.
