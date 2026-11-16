# Publish BVT Studio on GitHub

The standalone source repository is intended to be **`nigdanil/BVT-Studio`**, independent of `nigdanil/BVT`. The add-on is not published until you run these commands and GitHub confirms success.

## Prerequisites

- Git for Windows and Git Bash
- GitHub CLI (`gh`); install it from <https://cli.github.com/> if missing
- An authenticated GitHub account with repository creation rights

## 1. Extract source

Extract `BVT_Studio_Source_v0.2.zip` into a clean directory, e.g. `D:\BVT-Studio`. Start Git Bash in that directory.

```bash
python scripts/build_addon.py
python -m unittest discover -s tests -v
gh auth login
gh auth status
git init -b main
git add .
git commit -m "feat: BVT Studio 2.5D Dataset Builder v0.2.0"
```

## 2. Create public repository, publish code

```bash
gh repo create nigdanil/BVT-Studio --public \
  --description "Blender 2.5D dataset builder: glass artifacts and YOLO annotations" \
  --source=. --remote=origin --push
```

If the repository was already created on GitHub, instead of `gh repo create` use:

```bash
git remote add origin https://github.com/nigdanil/BVT-Studio.git
git push -u origin main
```

## 3. Publish beta ZIP as GitHub release

After a successful local test in Blender 5.2.3:

```bash
gh release create v0.2.0 dist/BVT_Studio_Blender_Addon_v0.2.zip \
  --repo nigdanil/BVT-Studio \
  --title "BVT Studio v0.2.0" \
  --notes "Glass_p_001…N organization, 2.5D glass shader, YOLO Plane annotations and export."
```

For an untested preview, use `--prerelease` with this command and mark documentation accordingly.

**Do not use force push**, and do not publish photographs or dataset assets without separate permissions.

## One-command publishing alternative (Git Bash)

`bash scripts/publish_github.sh` performs the same checks, initializes the Git repository if needed, creates/pushes `nigdanil/BVT-Studio` if absent, and publishes an **untested beta pre-release** ZIP. It requires `gh`, authentication and a local Git identity. It never overwrites an existing release or force-pushes. Review the script before running it.
