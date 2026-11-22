# Create Pull Request Script
$title = "🚀 Complete Web Migration: Telegram → React + PostgreSQL + CI/CD"
$body = @"
## 📋 Summary
Complete migration of MealMind from Telegram bot to modern React web application with PostgreSQL backend and comprehensive CI/CD pipeline.

## 🎯 Key Changes

### ✅ Frontend Migration (Telegram → React)
- Built complete React + TypeScript + Vite frontend
- 9 pages: Dashboard, Food Delivery, Instamart, Dineout, Orders, Insights, Analytics, Login, OAuth Callback
- Swiggy OAuth authentication flow
- **Swiggy-themed orange design** (#FC8019) with custom animations
- Responsive UI with shadcn/ui + Tailwind CSS

### ✅ Database Migration (SQLite → PostgreSQL)
- Migrated to **Neon PostgreSQL** (Singapore: ap-southeast-1)
- Successfully migrated 2 users and 6 orders
- Connection pooling with psycopg driver
- Production-ready setup

### ✅ UX Improvements
- **Removed all browser prompts** - auto-select variants/addons
- **Auto-sync orders after login** - removed separate sync tab
- Toast notifications instead of alert() dialogs
- Seamless Swiggy-like experience

### ✅ CI/CD Pipeline
- GitHub Actions with 7 jobs:
  - Backend tests (PostgreSQL service container)
  - Frontend build & type checking
  - Security scanning (Trivy)
  - Integration tests
  - Docker image build
  - Code quality (SonarCloud ready)
  - Deployment hooks

## 🧪 Test Results
``````
Total: 27 tests
✅ Passed: 23 (85.2%)
❌ Failed: 0 (0%)
⚠️ Warnings: 4 (expected 401s)

Backend: ✅ Port 8000
Frontend: ✅ Port 5173
PostgreSQL: ✅ 2 users, 6 orders
``````

## 📦 Changes Summary
- **Modified**: 25 files (UI/UX, PostgreSQL integration)
- **Added**: 20 files (CI/CD, Docker, UI components, tests)
- **Deleted**: 8 files (Telegram bot legacy code)

## 🔧 Technical Stack
- Frontend: React 18, TypeScript, Vite, Tailwind, shadcn/ui
- Backend: Python 3.12, FastAPI, SQLAlchemy
- Database: PostgreSQL 15 (Neon Cloud)
- CI/CD: GitHub Actions, Docker, Trivy
- Testing: Pytest, pytest-asyncio, HTTPX

## ✨ Before & After
**Before**: Telegram bot, window.prompt() dialogs, SQLite, manual sync tab
**After**: React web app, auto-selection, PostgreSQL, auto-sync on login

## 🚀 Ready to Deploy
- ✅ CI/CD configured
- ✅ Docker containerization
- ✅ Environment templates
- ✅ Security scanning
- ✅ Health checks

**Test locally**:
``````bash
# Backend
pip install -r requirements.txt
python -m src.main

# Frontend
cd frontend && npm install && npm run dev
``````

**Access**: http://localhost:5173
"@

gh pr create --title $title --body $body --base main
