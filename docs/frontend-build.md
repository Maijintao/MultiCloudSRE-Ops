# Frontend Build

The browser UI is dependency-free JavaScript.

- Source modules live under `static/app/`.
- `static/index.html` loads the generated `static/app.js` bundle.
- `static/styles.css` contains shared styling.

Rebuild after editing frontend source:

```bash
node scripts/build-static-app.js
```

CI runs the build and fails if the generated bundle differs from the committed
file.
