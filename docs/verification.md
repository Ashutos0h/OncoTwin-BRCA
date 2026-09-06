# Foundation verification — 2026-09-06

Verified locally with Python 3.12.14, Node 24.11.0 and npm 11.6.1.

| Check | Result |
| --- | --- |
| Five schemas and matching fixtures, including date-time formats | Passed |
| Python tests: contracts, fixture lineage, API health, mock ML, Data validation | 19 passed |
| Mock inference CLI and sample event validator CLI | Passed |
| TypeScript check and Vite production build | Passed |
| npm dependency audit after updating Vite to 7.3.6 | Zero reported vulnerabilities |
| Docker Compose configuration using .env.example | Passed; Docker config access warnings |

One upstream Starlette/AnyIO deprecation warning appeared in the test suite.
The database was not started; no database integration is implemented. Browser
interaction was not tested. The frontend was verified by type checking/build only.
GitHub CI is supplied but has not run remotely. No Git repository, remote, commit,
team branches or publication was created. No full end-to-end event pipeline is
claimed. Contract adoption/reconciliation remains a team decision.

Dependencies were installed in the local .venv and frontend/node_modules, both
ignored. frontend/package-lock.json records the resolved Node dependencies.
