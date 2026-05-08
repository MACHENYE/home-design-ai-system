# Home Design AI Frontend

This frontend is a Vite + Vue 3 + Element Plus application.

## Structure

```text
src/
  main.js
  App.vue
  styles.css
  components/
    AppHeader.vue
    AuthPanel.vue
    ControlPanel.vue
    ImageDialogs.vue
    ResultPanel.vue
```

`App.vue` keeps global state and backend API orchestration. The components focus
on specific UI modules and communicate with the parent through props and events.

## Development

Run the backend first on `http://127.0.0.1:8000`, then start Vite:

```powershell
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

Vite proxies `/api`, `/healthz`, and `/uploads` to the backend.

## Production Build

```powershell
npm run build
```

The build output is written to `frontend/dist`. The FastAPI backend will serve
`frontend/dist` at `/app/` when the directory exists.
