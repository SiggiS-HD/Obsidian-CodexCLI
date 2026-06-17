# Releases and Tags

This repository uses a simple Semantic Versioning style for Git tags:

- `vMAJOR.MINOR.PATCH`
- Example: `v0.1.0`

## Meaning

- `MAJOR`
  Use this when you introduce intentional breaking changes.
- `MINOR`
  Use this when you add new features without intentionally breaking existing workflows.
- `PATCH`
  Use this when you fix bugs without changing the intended public behavior.

## Starting point

The first public repository state can be tagged as:

- `v0.1.0`

As long as the project is still evolving and interfaces may still change, `0.x.y` is appropriate.

## Recommended usage for this project

- New feature: increase `MINOR`
  Example: `v0.1.0` -> `v0.2.0`
- Bug fix only: increase `PATCH`
  Example: `v0.2.0` -> `v0.2.1`
- Breaking change: increase `MAJOR`
  Example: `v0.9.0` -> `v1.0.0`

## Tag workflow

Create an annotated tag locally:

```powershell
git tag -a v0.1.0 -m "First public release"
```

Push a single tag:

```powershell
git push origin v0.1.0
```

Push all local tags:

```powershell
git push origin --tags
```

List tags:

```powershell
git tag
```

## Git Tag vs GitHub Release

- A Git tag marks one exact commit in the repository history.
- A GitHub Release is the GitHub presentation layer on top of a tag, usually with a title and release notes.

Recommended workflow:

1. Commit the intended changes.
2. Create the version tag.
3. Push the tag to GitHub.
4. Optionally create a GitHub Release based on that tag.
