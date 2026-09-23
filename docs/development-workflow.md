# Team setup and workflow

The local repository already has a foundation commit and an origin remote:
`https://github.com/Ashutos0h/OncoTwin-BRCA`.
Remote contents, access and publication status have not been verified here.
Do not reinitialize Git or add another origin.

1. Review docs/contract-decisions.md before freezing the provisional interfaces.
2. Run README.md checks and review `git status --short` and `git diff`.
3. Review untracked files too: the current frontend/backend work includes new files
   that teammates will not receive until they are committed and pushed.
4. Stage only reviewed source, tests, configuration examples and documentation.
   Commit the reviewed baseline, then push the intended branch to the existing
   origin. Do not include .env, datasets, credentials, databases or model binaries.
5. Invite the four leads using the repository's access settings. Each uses an
   independent clone and the relevant docs/leads/ instruction file.

Each lead runs:

```powershell
git clone https://github.com/Ashutos0h/OncoTwin-BRCA.git
cd OncoTwin-BRCA
git switch -c codex/YOUR_MODULE
```

Replace YOUR_MODULE with frontend, backend, ml or data. Follow README.md for
installation, then copy the prompt from your lead file into your working session.
After a module commit, push with `git push -u origin codex/YOUR_MODULE`.
Open a focused pull request and merge after relevant checks and affected-lead review.
Do not run separate branch checkouts in the same working folder.

Before a PR, run contract validation and relevant Python tests; for frontend changes,
run frontend tests and build. Shared schema changes need explicit agreement,
versioning and migration decisions, fixtures and tests. Existing schemas remain the
implementation authority while broader feature semantics are being reviewed.

See team-handoff.md for current module status and the next deliverable per lead.
