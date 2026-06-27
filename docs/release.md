# Public Release

Use a fresh public repository for the sanitized open-source release. Do not push
the existing private Git history.

## Suggested Flow

From a clean copy of `aiops-platform`:

```bash
python -m unittest discover -s tests -v
node scripts/build-static-app.js
git init
git add .
git status
git commit -m "Initial open-source release"
git branch -M main
git remote add origin <public-github-url>
git push -u origin main
```

Before `git add`, confirm that these paths are absent or ignored:

- `.env`
- `state/`
- `.private-release-backup/`
- `*.sqlite3`
- `__pycache__/`
- private fault cases
- real cloud host addresses
- kubeconfigs, SSH keys, API keys, or other credentials

The included hygiene tests scan for common leaks, but they are not a substitute
for reviewing the staged diff before publishing.
