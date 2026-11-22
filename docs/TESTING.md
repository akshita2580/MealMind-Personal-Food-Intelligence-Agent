# MealMind Testing Guide

## Overview

MealMind uses comprehensive testing strategies for both backend and frontend:

- **Backend**: Pytest with pytest-asyncio for async testing
- **Frontend**: Vitest with Testing Library for React components

## Running Tests

### Backend Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_api.py

# Run with coverage report
pytest --cov=src --cov-report=html

# Run specific test
pytest tests/test_api.py::test_auth_status
```

### Frontend Tests

```bash
cd frontend

# Run all tests (watch mode)
npm run test

# Run all tests once
npm run test -- --run

# Run with UI
npm run test:ui

# Run with coverage
npm run test:coverage

# Run specific test file
npm run test -- api.test.ts
```

## Test Structure

### Backend Tests

Located in `tests/` directory:
- `test_api.py` - API endpoint tests
- `test_repository.py` - Database operations
- `test_security.py` - Encryption and auth logic
- `test_scheduler.py` - Background job tests

### Frontend Tests

Located in `frontend/src/**/__tests__/` directories:
- `services/__tests__/api.test.ts` - API service tests
- `components/__tests__/*.test.tsx` - Component tests
- `pages/__tests__/*.test.tsx` - Page component tests

## Writing Tests

### Backend Test Example

```python
import pytest
from src.api import app
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_auth_status():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/auth/status")
        assert response.status_code == 200
        assert "authenticated" in response.json()
```

### Frontend Test Example

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Dashboard } from '../Dashboard';

describe('Dashboard', () => {
  it('should render welcome message', () => {
    render(<Dashboard />);
    expect(screen.getByText(/welcome/i)).toBeInTheDocument();
  });
});
```

## Test Coverage Goals

- **Backend**: Minimum 80% coverage for core modules
- **Frontend**: Minimum 70% coverage for components and services

## CI/CD Integration

Tests run automatically on:
- Every push to any branch
- Pull requests
- Before deployment

## Mocking

### Backend Mocks

Use pytest fixtures for database mocking:
```python
@pytest.fixture
def mock_db():
    # Mock database session
    pass
```

### Frontend Mocks

Use Vitest mocks:
```typescript
vi.mock('../services/api', () => ({
  getOrders: vi.fn(),
}));
```

## Debugging Tests

### Backend
```bash
# Run with print statements visible
pytest -s

# Run with debugger
pytest --pdb
```

### Frontend
```bash
# Run with debug output
npm run test -- --reporter=verbose

# Run single test in watch mode
npm run test -- --grep="specific test name"
```

## Common Issues

### Backend

**Issue**: Tests fail with database errors
**Solution**: Ensure test database is clean or use transactions

**Issue**: Async tests timeout
**Solution**: Increase timeout in pytest.ini or use `@pytest.mark.asyncio(timeout=30)`

### Frontend

**Issue**: Component tests fail to find elements
**Solution**: Use `screen.debug()` to see rendered output

**Issue**: Mock not working
**Solution**: Ensure mock is defined before import of tested module

## Best Practices

1. **Arrange-Act-Assert**: Structure tests clearly
2. **Isolation**: Each test should be independent
3. **Descriptive Names**: Test names should describe what they test
4. **One Assertion**: Prefer one logical assertion per test
5. **Clean Up**: Reset mocks and state after each test

## Performance

- Backend tests should complete in < 30 seconds
- Frontend tests should complete in < 1 minute
- Use `--run` flag in CI to avoid watch mode

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Vitest Documentation](https://vitest.dev/)
- [Testing Library](https://testing-library.com/docs/react-testing-library/intro/)
