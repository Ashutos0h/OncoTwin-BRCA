# Team setup and workflow

1. Project owner reviews docs/contract-decisions.md and adopts or reconciles the
   provisional schemas before freezing integration interfaces.
2. Follow README.md to run checks locally.
3. Create a private GitHub repository and publish the reviewed base (commands below).
4. Invite all four leads. Each clones separately and creates a feature branch.
5. Give each lead their docs/leads/ file; start with the synthetic milestone.
6. Open focused PRs, review contract impact and merge into main after checks pass.

Publishing is manual: no remote, commit or push was created by the scaffold.
From root, after reviewing `git status`:

```powershell
git init -b main
git add .
git commit -m "Initialize OncoTwin-BRCA shared foundation"
git remote add origin YOUR_REPOSITORY_URL
git push -u origin main
```

Each lead runs (replace placeholders):

```powershell
git clone YOUR_REPOSITORY_URL
cd OncoTwin-BRCA
git switch -c feature/YOUR_MODULE
```

Use frontend, backend, ml or data for YOUR_MODULE. Push with
`git push -u origin feature/YOUR_MODULE` after the first module commit.
Never commit .env, patient records, raw datasets, local databases or model binaries.

Before a PR: run contract validation, relevant pytest modules, and frontend build
when frontend changes. Include what changed, checks and any unimplemented pieces.
