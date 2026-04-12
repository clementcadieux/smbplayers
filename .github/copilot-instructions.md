# Copilot Agent Instructions

These instructions apply whenever a Copilot coding agent works on this repository.

## Branch & Issue Workflow

1. **One branch per issue.** When assigned to fix an issue, create a branch whose name starts with the issue number, e.g. `42-fix-power-rating` or `issue/42-fix-power-rating`. The `auto-pr.yml` workflow parses this number to auto-link the pull request to the issue.
2. **Check `PLAN.md` first.** When a GitHub issue is opened, `update-plan-on-issue.yml` appends an AI-generated implementation plan to `PLAN.md` under `## Issue #<number>`. Read that section before writing any code — it is the canonical list of steps to follow for the issue.
3. **Never push directly to `main` or `master`.** All changes must go through a pull request. The `auto-pr.yml` workflow creates the PR automatically on the first push to a non-default branch.
4. **Close keyword in PR body.** When creating or editing a PR description, include `Closes #<issue-number>` so that `close-issue-on-merge.yml` automatically closes the issue when the PR is merged.
5. **Regular small commits.** Always commit and push regularly, don't just build 1 huge commit with all the changes.
6. **Always pull main at the beginning.** Always pull from origin main to guarantee latest changes as the work's base.

## Repository Layout

```
smb4_mlb_ratings/       # Python rating engine package
  engine.py             # core rating logic
  models.py             # Pydantic input/output models
  cli.py                # CLI entry point
  ingest/
    savant.py           # Baseball Savant CSV ingestion
    baseball_reference.py  # Baseball Reference CSV ingestion
smb4_player_reference.json  # SMB4 reference schema and trait catalog
tests/                  # test suite
PLAN.md                 # auto-updated issue resolution plan
```

## Coding Standards

- **Language:** Python 3. Follow existing style (no type annotations are required if the surrounding code omits them; add them if the surrounding code uses them).
- **Models:** Use the `PlayerInput` / `PlayerOutput` models in `models.py` for all data crossing the engine boundary. Do not add new top-level JSON keys without updating those models.
- **Reference data:** All SMB4 thresholds, trait definitions, and position data live in `smb4_player_reference.json`. Read from that file rather than hard-coding values.
- **Tests:** Add or update tests in the `tests/` directory for every behaviour change. Run `python -m pytest tests/` to verify before opening a PR.
- **Dependencies:** Use only libraries already present in the project. Do not add new dependencies without explicit user approval.

## Running the Tool Locally

```powershell
# Rate a prepared JSON file
python -m smb4_mlb_ratings.cli rate players.json output.json

# Ingest from a source manifest, then rate
python -m smb4_mlb_ratings.cli ingest-rate manifest.json output.json

# Run tests
python -m pytest tests/
```

## Pull Request Checklist

Before marking a PR ready for review, confirm:

- [ ] The branch name contains the issue number (e.g. `42-description`).
- [ ] `PLAN.md` steps for the issue are all addressed.
- [ ] `Closes #<issue-number>` appears in the PR body.
- [ ] Tests pass (`python -m pytest tests/`).
- [ ] No new hard-coded thresholds — reference data belongs in `smb4_player_reference.json`.
