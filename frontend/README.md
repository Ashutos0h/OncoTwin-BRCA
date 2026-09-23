# Frontend dashboard

The React dashboard connects to the FastAPI backend and implements the complete
synthetic workflow: create/select a twin, append a contract-shaped clinical event,
inspect reconstructed state and missingness, create a feature snapshot, generate an
explicitly marked mock prediction, and inspect event and audit histories.

Run the backend first, then start the frontend from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
npm.cmd --prefix frontend run dev
```

Open `http://127.0.0.1:5173`. Configure another API with
`VITE_API_BASE_URL`. `VITE_API_KEY` is available for a local authenticated demo,
but Vite embeds it in browser code; never use a production writer key there.

The interface includes backend connection, loading, empty, validation/error,
missing-data, and success states. A risk trajectory is rendered only after two or
more historical predictions exist. All predictions remain labelled mock and
research-only.

Validation commands:

```powershell
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend audit
.\.venv\Scripts\python.exe scripts\validate_contracts.py
```
