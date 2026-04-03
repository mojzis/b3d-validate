#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]] || [[ ! "$1" =~ ^(patch|minor|major)$ ]]; then
    echo "Usage: $0 <patch|minor|major>"
    exit 1
fi

# Ensure working tree is clean
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Error: working tree is not clean. Commit or stash changes first."
    exit 1
fi

# Bump version
uv version --bump "$1" --no-sync

# Capture new version
VERSION=$(uv version --short)

echo "Releasing v${VERSION}..."

# Commit and tag
git add pyproject.toml uv.lock
git commit -m "release v${VERSION}"
git tag "v${VERSION}"

# Push
git push && git push --tags

echo "Done. v${VERSION} pushed — GitHub Actions will publish to PyPI."
