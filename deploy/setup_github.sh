#!/bin/bash
# Van Suraksha — GitHub + HuggingFace Deployment Setup
# Run this from E:\FIRE in Git Bash
# Prerequisites: gh (GitHub CLI), git, huggingface-cli

set -e

REPO_NAME="van-suraksha-alert"
HF_SPACE="Akshayr11/van-suraksha"

echo "================================================"
echo "  Van Suraksha Deployment Setup"
echo "================================================"

# Step 1: Create GitHub repo
echo ""
echo "[1/4] Creating GitHub repository..."
gh repo create "$REPO_NAME" --public --description "India's first AI forest fire Early Warning System" || echo "Repo may already exist"

# Step 2: Push code
echo ""
echo "[2/4] Pushing code to GitHub..."
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$(gh api user --jq .login)/$REPO_NAME.git"
git push -u origin HEAD

# Step 3: Set FIRMS secret for GitHub Actions
echo ""
echo "[3/4] Setting FIRMS_MAP_KEY secret for GitHub Actions..."
gh secret set FIRMS_MAP_KEY --body "e9440d63e8365cde82400a3e991fdc5e" --repo "$(gh api user --jq .login)/$REPO_NAME"

echo ""
echo "[4/4] Done!"
echo ""
echo "================================================"
echo "  DEPLOYMENT STATUS"
echo "================================================"
echo ""
echo "  GitHub repo : https://github.com/$(gh api user --jq .login)/$REPO_NAME"
echo "  Daily cron  : GitHub Actions runs at 06:00 AM IST automatically"
echo ""
echo "  NEXT STEPS:"
echo "  1. Go to https://huggingface.co/new-space"
echo "  2. Name: van-suraksha"
echo "  3. SDK: Docker"
echo "  4. Hardware: CPU basic (free)"
echo "  5. Create Space"
echo "  6. Then run:"
echo "     git clone https://huggingface.co/spaces/$HF_SPACE hf-space"
echo "     cp -r deploy/hf_space/* hf-space/"
echo "     cp -r src scripts dashboard config.yaml hf-space/"
echo "     cp -r models/ignition data/aoi hf-space/"
echo "     mkdir -p hf-space/data_lake"
echo "     cp -r data_lake/fire_detections data_lake/fire_weather data_lake/alerts data_lake/land_cover hf-space/data_lake/"
echo "     cd hf-space && git add . && git commit -m 'Deploy Van Suraksha' && git push"
echo ""
echo "  Dashboard will be live at: https://huggingface.co/spaces/$HF_SPACE"
echo "================================================"
