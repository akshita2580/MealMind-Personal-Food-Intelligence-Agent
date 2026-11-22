# MealMind PR Creation Script
Write-Host "🚀 Creating Pull Request for MealMind Project Cleanup" -ForegroundColor Cyan
Write-Host ""

# PR Details
$title = "refactor: Clean up project structure and add comprehensive testing framework"
$prUrl = "https://github.com/akshita2580/MealMind-Personal-Food-Intelligence-Agent/compare/main...feature/cleanup-project-structure"

Write-Host "📝 PR Title:" -ForegroundColor Green
Write-Host $title
Write-Host ""

Write-Host "🔗 Opening PR creation page in browser..." -ForegroundColor Yellow
Start-Process $prUrl

Write-Host ""
Write-Host "✅ Steps to complete:" -ForegroundColor Cyan
Write-Host "1. Browser should open to PR creation page"
Write-Host "2. Title is pre-filled (or copy from above)"
Write-Host "3. Description is pre-filled from .github/pull_request_template.md"
Write-Host "4. Review the changes in the 'Files changed' tab"
Write-Host "5. Click 'Create Pull Request' button"
Write-Host "6. Wait for CI checks to pass"
Write-Host "7. Click 'Squash and merge' button"
Write-Host "8. Confirm the merge"
Write-Host ""
Write-Host "🎉 That's it! PR will be merged to main with clean history." -ForegroundColor Green
