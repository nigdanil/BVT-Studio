#!/usr/bin/env bash
# Run explicitly in Git Bash after reviewing the source and testing in Blender.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="${BVT_STUDIO_REPO:-nigdanil/BVT-Studio}"
VERSION="v0.2.0"
ARCHIVE="dist/BVT_Studio_Blender_Addon_v0.2.zip"

command -v gh >/dev/null || { echo 'GitHub CLI (gh) missing: https://cli.github.com/'; exit 2; }
command -v git >/dev/null || { echo 'Git missing'; exit 2; }
gh auth status >/dev/null || { echo 'Run: gh auth login'; exit 2; }

python scripts/build_addon.py
python -m unittest discover -s tests -v

if git rev-parse --show-toplevel >/dev/null 2>&1; then
  GIT_ROOT="$(git rev-parse --show-toplevel)"
  if [[ "$(cd "$GIT_ROOT" && pwd -P)" != "$(pwd -P)" ]]; then
    echo "Refusing to publish from inside an existing Git repository: $GIT_ROOT"
    echo "Extract BVT Studio into its own folder (e.g. D:/BVT-Studio)."
    exit 3
  fi
else
  git init -b main
fi

git add README.md LICENSE CHANGELOG.md .gitignore bvt_studio scripts tests docs .github
if ! git diff --cached --quiet; then
  git commit -m 'feat: BVT Studio 2.5D Dataset Builder v0.2.0'
fi

if gh repo view "$REPO" >/dev/null 2>&1; then
  echo "Repository already exists: $REPO"
  if git remote get-url origin >/dev/null 2>&1; then
    CURRENT_REMOTE="$(git remote get-url origin)"
    case "$CURRENT_REMOTE" in
      *"github.com/${REPO}"|*"github.com/${REPO}.git") ;;
      *) echo "Refusing to push to unexpected origin: $CURRENT_REMOTE"; exit 4 ;;
    esac
  else
    git remote add origin "https://github.com/${REPO}.git"
  fi
  git push -u origin "$(git branch --show-current)"
else
  gh repo create "$REPO" --public \
    --description 'Blender 2.5D dataset builder: glass artifacts and YOLO annotations' \
    --source=. --remote=origin --push
fi

if gh release view "$VERSION" --repo "$REPO" >/dev/null 2>&1; then
  echo "Release ${VERSION} already exists. Not overwriting it."
else
  gh release create "$VERSION" "$ARCHIVE" --repo "$REPO" --prerelease \
    --title 'BVT Studio v0.2.0 (beta)' \
    --notes 'Independent Blender addon: auto-named Glass_p_001...N in BVT_Glass, glass material, YOLO annotation and clean dataset export. Beta: local Blender validation pending.'
fi
printf '\nPUBLISHED: https://github.com/%s\n' "$REPO"
