# GitHub Setup

This workspace is now suitable for a GitHub repository, with generated recordings and run databases ignored by `.gitignore`.

## Local Commit

```bash
git init
git add .gitignore README.md requirements.txt mnet_slam ios docs
git commit -m "Initial mNET SLAM MVP and iOS app scaffold"
```

## Push To GitHub

With GitHub CLI:

```bash
gh repo create claudeSLAM_mvp --private --source . --remote origin --push
```

Without GitHub CLI:

```bash
git remote add origin https://github.com/YOUR_USER/claudeSLAM_mvp.git
git branch -M main
git push -u origin main
```

Do not commit `data/`, `runs/`, or real customer recordings unless a deliberate data release process is created.
