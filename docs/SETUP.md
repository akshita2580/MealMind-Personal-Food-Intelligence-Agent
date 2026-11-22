# MealMind Setup Guide

## Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- PostgreSQL (or Neon account)
- Swiggy OAuth credentials

## Backend Setup

### 1. Create Virtual Environment

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Unix
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the root directory:

```env
# Database
DATABASE_URL=postgresql+psycopg://user:password@host/database

# Encryption
ENCRYPTION_KEY=your-fernet-encryption-key

# Swiggy OAuth
SWIGGY_CLIENT_ID=your-client-id
SWIGGY_CLIENT_SECRET=your-client-secret
SWIGGY_REDIRECT_URI=http://localhost:8000/api/auth/callback

# Server
BACKEND_PORT=8000
FRONTEND_URL=http://localhost:5173
```

### 4. Initialize Database

```bash
python -m src.main
```

The database schema will be created automatically on first run.

### 5. Start Backend Server

```bash
python -m src.main
```

Backend will run on `http://localhost:8000`

## Frontend Setup

### 1. Navigate to Frontend Directory

```bash
cd frontend
```

### 2. Install Dependencies

```bash
npm install
```

### 3. Configure Environment

Create `frontend/.env`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

### 4. Start Development Server

```bash
npm run dev
```

Frontend will run on `http://localhost:5173`

## Testing

### Backend Tests

```bash
pytest
```

### Frontend Tests

```bash
cd frontend
npm run test
```

## Docker Setup

### Build and Run

```bash
docker build -t mealmind .
docker run -p 8000:8000 --env-file .env mealmind
```

### Docker Compose (Coming Soon)

```bash
docker-compose up
```

## Neon PostgreSQL Setup

1. Create account at https://neon.tech
2. Create a new project (choose Singapore region for best performance in Asia)
3. Copy the connection string
4. Update `DATABASE_URL` in `.env`

Connection string format:
```
postgresql+psycopg://user:password@host/database?sslmode=require
```

## Troubleshooting

### Database Connection Issues

- Verify DATABASE_URL is correct
- Check firewall allows PostgreSQL port (5432)
- Ensure Neon project is active (not suspended)

### OAuth Issues

- Verify redirect URI matches exactly in Swiggy Developer Console
- Check CLIENT_ID and CLIENT_SECRET are correct
- Ensure callback URL is accessible

### CORS Issues

- Frontend URL must match FRONTEND_URL in backend .env
- Check browser console for specific CORS errors

## Development Workflow

1. Create feature branch: `git checkout -b feature/your-feature`
2. Make changes and test locally
3. Commit with conventional commits: `feat:`, `fix:`, `docs:`
4. Push and create PR
5. Squash and merge to main after review

## Production Deployment

See `docs/DEPLOYMENT.md` for production deployment instructions.
