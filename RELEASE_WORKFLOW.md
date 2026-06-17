# Release Workflow

This file describes the practical release workflow for this repository.

## Version scheme

This project uses Git tags in the form:

- `vMAJOR.MINOR.PATCH`

Examples:

- `v0.1.0`
- `v0.1.1`
- `v0.2.0`
- `v1.0.0`

Meaning:

- `PATCH`
  Bug fixes without intentional behavior changes.
- `MINOR`
  New features without intentional breaking changes.
- `MAJOR`
  Intentional breaking changes.

## Typical release decisions

- Bug fix only:
  - `v0.1.0` -> `v0.1.1`
- New feature:
  - `v0.1.0` -> `v0.2.0`
- Breaking change:
  - `v0.9.0` -> `v1.0.0`

## Standard workflow

1. Check the local status:

```powershell
git status
```

2. Review the changes that belong to the release.

3. Commit the intended state:

```powershell
git add .
git commit -m "Short release-related description"
```

4. Push the branch:

```powershell
git push origin main
```

5. Create an annotated tag:

```powershell
git tag -a v0.1.1 -m "Short release note"
```

6. Push the tag:

```powershell
git push origin v0.1.1
```

7. Open GitHub and create a Release based on the pushed tag.

## Recommended order

- First commit the final release state.
- Then push the branch.
- Then create and push the tag.
- Then publish the GitHub Release in the web UI.

This order keeps the repository history easy to understand and makes the tagged state visible on GitHub immediately.

## Optional checks before tagging

Useful checks before a release:

- run relevant tests
- verify README or user documentation if behavior changed
- confirm that no local-only files are included
- confirm that `git status` is clean before creating the tag

## Useful commands

Show the latest commit:

```powershell
git log -1 --oneline
```

List all tags:

```powershell
git tag
```

Show details for one tag:

```powershell
git show v0.1.0
```

Check whether the branch is clean:

```powershell
git status --short
```

## GitHub Release notes

The Git tag marks the exact repository state.

The GitHub Release is the presentation layer on top of the tag and should usually contain:

- release title
- short summary
- major included features or fixes
- important notes or limitations

## Minimal checklist

- changes reviewed
- commit created
- branch pushed
- tag created
- tag pushed
- GitHub Release published
