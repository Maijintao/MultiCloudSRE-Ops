# Contributing

Thanks for improving AIOps OJ Platform.

## Development

Use Python 3.10 or newer.

```bash
python -m unittest discover -s tests -v
node scripts/build-static-app.js
```

The frontend source lives in `static/app/`. The checked-in `static/app.js`
bundle is generated from those files so the app can run without a separate
frontend build system.

## Case Materials

Only commit public demo cases. Private competition cases, hidden answers,
real cloud hosts, kubeconfigs, API keys, SSH keys, database files, screenshots,
and run state must stay out of the public repository.

Before opening a pull request, run the tests and check for accidental secrets:

```bash
python -m unittest discover -s tests -v
```
