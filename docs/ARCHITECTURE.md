# MealMind Architecture

## System Overview
MealMind is a full-stack food intelligence agent that integrates with Swiggy's services (Food Delivery, Instamart, Dineout) to provide intelligent ordering assistance and analytics.

## Tech Stack

### Backend
- **Framework**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL (Neon Cloud - Singapore region)
- **ORM**: SQLAlchemy with async support
- **Authentication**: OAuth 2.0 with Swiggy
- **Scheduling**: APScheduler for token refresh

### Frontend
- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite 5.4.21
- **Styling**: Tailwind CSS
- **UI Components**: shadcn/ui
- **State Management**: React Context API
- **Routing**: React Router v6

### DevOps
- **CI/CD**: GitHub Actions
- **Containerization**: Docker
- **Testing**: Vitest (frontend), Pytest (backend)
- **Code Quality**: ESLint, Prettier, Black

## Database Schema

### Users Table
- `id`: Primary key
- `swiggy_user_id`: Unique Swiggy identifier
- `access_token`: Encrypted OAuth token
- `refresh_token`: Encrypted OAuth refresh token
- `token_expires_at`: Token expiration timestamp
- `created_at`: User creation timestamp

### Orders Table
- `id`: Primary key
- `user_id`: Foreign key to users
- `swiggy_order_id`: Unique Swiggy order identifier
- `order_time`: Order timestamp
- `order_total`: Total order amount
- `delivery_address`: Delivery location
- `restaurant_name`: Restaurant name
- `is_swiggy_one`: Boolean flag for Swiggy One orders
- `order_status`: Current order status
- `order_data`: JSONB field with full order details
- `created_at`: Record creation timestamp

## API Endpoints

### Authentication
- `POST /api/auth/url` - Get OAuth authorization URL
- `GET /api/auth/callback` - OAuth callback handler
- `GET /api/auth/status` - Check authentication status

### Orders
- `GET /api/orders/sync` - Sync orders from Swiggy
- `GET /api/orders/list` - List all orders
- `GET /api/orders/stats` - Get order statistics

### Swiggy Integration
- `POST /api/swiggy/search` - Search restaurants
- `GET /api/swiggy/restaurant/{id}` - Get restaurant details
- `POST /api/swiggy/instamart/search` - Search Instamart products
- `GET /api/swiggy/dineout/offers` - Get Dineout offers

## Security Features

1. **Token Encryption**: All OAuth tokens encrypted at rest using Fernet
2. **Environment Variables**: Sensitive config in .env files
3. **CORS**: Configured for frontend origin only
4. **SQL Injection Protection**: SQLAlchemy ORM parameterized queries
5. **Token Refresh**: Automatic token refresh before expiration

## Deployment Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Client    │◄────────┤    Nginx     ├────────►│   Backend   │
│  (React)    │  HTTPS  │  (Reverse    │   HTTP  │  (FastAPI)  │
│             │         │   Proxy)     │         │             │
└─────────────┘         └──────────────┘         └──────┬──────┘
                                                         │
                                                         ▼
                                                  ┌─────────────┐
                                                  │  PostgreSQL │
                                                  │    (Neon)   │
                                                  └─────────────┘
```

## Key Design Decisions

1. **PostgreSQL over SQLite**: Better for production, supports concurrent access
2. **Neon Cloud**: Serverless PostgreSQL with auto-scaling
3. **Token Storage**: Encrypted in database rather than session storage
4. **Auto-sync**: Orders sync automatically after OAuth completion
5. **Squash-merge**: Clean linear git history for better maintenance
