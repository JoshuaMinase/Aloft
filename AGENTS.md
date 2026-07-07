# Aloft Backend - Development Guide

This file provides project-specific commands, conventions, and guidance for development work on the Aloft backend.

## Project Structure

```
aloft/
├── backend/
│   ├── app/              # Main application code
│   │   ├── clients/      # External API clients (Groq, ElevenLabs, etc.)
│   │   ├── core/         # Core configuration, database, Redis
│   │   ├── middleware/   # Custom middleware (security, logging)
│   │   ├── models/       # Pydantic models
│   │   ├── routers/      # FastAPI route handlers
│   │   ├── services/     # Business logic layer
│   │   └── utils/        # Utility functions
│   ├── tests/            # Pytest test suite
│   ├── scripts/          # Utility scripts
│   │   └── manual-tests/ # Manual testing scripts
│   ├── music_assets/     # Audio files for background music
│   ├── requirements.txt  # Production dependencies
│   ├── requirements-dev.txt # Development dependencies
│   ├── pyproject.toml    # Project configuration (ruff, pytest)
│   ├── Dockerfile        # Container build configuration
│   ├── docker-compose.yml # Local development stack
│   └── gunicorn.conf.py  # Production server config
└── README.md             # Project overview
```

## Development Commands

### Environment Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Copy environment template
cp .env.example .env
# Edit .env with your configuration
```

### Running the Application

```bash
# Development server with auto-reload
uvicorn app.main:app --reload

# Production server (with gunicorn)
gunicorn app.main:app --config gunicorn.conf.py

# Docker Compose (includes MongoDB and Redis)
docker-compose up --build
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html --cov-report=term

# Run specific test file
pytest tests/test_auth.py

# Run specific test function
pytest tests/test_auth.py::test_tampered_token_raises_auth_error

# Run with verbose output
pytest -v

# Run tests in parallel (requires pytest-xdist)
pytest -n auto
```

### Performance Testing

```bash
# Run Locust load tests
cd backend
locust -f tests/performance/locustfile.py

# Run headless load test
locust -f tests/performance/locustfile.py \
  --headless \
  --users 50 \
  --spawn-rate 10 \
  --run-time 60s \
  --host http://localhost:8000

# Run with HTML report
locust -f tests/performance/locustfile.py \
  --headless \
  --users 50 \
  --spawn-rate 10 \
  --run-time 60s \
  --host http://localhost:8000 \
  --html performance-report.html
```

### Code Quality

```bash
# Run ruff linter
ruff check .

# Auto-fix linting issues
ruff check . --fix

# Format code with ruff
ruff format .

# Check formatting without making changes
ruff format --check .
```

### Docker Commands

```bash
# Build Docker image
docker build -t aloft-backend .

# Run with docker-compose
docker-compose up

# Stop services
docker-compose down

# Remove volumes (WARNING: deletes data)
docker-compose down -v

# View logs
docker-compose logs -f backend
```

## Project Conventions

### Code Style

- **Line length**: 100 characters (configured in pyproject.toml)
- **Python version**: 3.12+ (3.12 recommended for full audio support)
- **Import order**: Use ruff's isort rules (standard library → third-party → local)
- **Type hints**: Required for all function signatures
- **Docstrings**: Use Google-style docstrings for functions and classes

### API Design

- **Route prefix**: All routes are prefixed with `/v1/` for versioning
- **Response format**: Consistent JSON responses with appropriate HTTP status codes
- **Error handling**: Use HTTPException with descriptive messages
- **Authentication**: JWT Bearer tokens required for protected endpoints
- **Rate limiting**: Per-endpoint rate limits defined in `app/core/dependencies.py`

### Database Conventions

- **Collection naming**: Plural, lowercase (e.g., `users`, `pois`, `stories`)
- **Index naming**: Descriptive names for indexes (e.g., `users_email_unique`)
- **TTL**: Use TTL for time-based data (sessions, cache, rate limits)
- **Transactions**: Use MongoDB transactions for multi-document operations

### Service Layer Pattern

- **Clients** (`app/clients/`): External API integrations (Groq, ElevenLabs, etc.)
- **Services** (`app/services/`): Business logic and data manipulation
- **Repositories** (`app/services/*_repository.py`): Database access layer
- **Routers** (`app/routers/`): HTTP endpoint handlers (thin, delegate to services)

### Error Handling

- **Custom exceptions**: Define domain-specific exceptions in service modules
- **Logging**: Use structured logging with appropriate log levels
- **Graceful degradation**: Design for optional dependencies (Redis, external APIs)
- **User-facing errors**: Never expose internal details in API responses

### Security Best Practices

- **Secrets management**: Use environment variables and SecretStr for sensitive data
- **Input validation**: Use Pydantic models for all request/response validation
- **SQL injection**: Not applicable (MongoDB), but still validate all inputs
- **Rate limiting**: Protect expensive operations with rate limits
- **CORS**: Configure allowed origins per environment
- **CSP**: Configure Content-Security-Policy headers per environment
- **CSP Report-Only**: Enable `CSP_REPORT_ONLY=true` in development/staging to test CSP without blocking requests
- **Correlation IDs**: Automatically added to all requests for distributed tracing
- **Structured Logging**: JSON logs in production, console logs in development

## Configuration

### Required Environment Variables

For development, create a `.env` file based on `.env.example`:

```bash
# Core configuration
ENVIRONMENT=development
MONGODB_URI=mongodb://localhost:27017/?directConnection=true
MONGODB_DB_NAME=aloft
REDIS_URL=redis://localhost:6379/0

# Security
JWT_SECRET_KEY=your-secret-key-here
CORS_ALLOWED_ORIGINS=["*"]

# API Keys
GROQ_API_KEY=your_groq_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
AVIATIONSTACK_API_KEY=your_aviationstack_api_key
```

### Feature Flags

Configure optional features in `.env`:

```bash
# POI sources
POI_SOURCE_WIKIDATA_ENABLED=false
POI_SOURCE_GEONAMES_ENABLED=false
POI_SOURCE_OVERPASS_ENABLED=false

# Audio storage
# Set R2 credentials for cloud storage, leave unset for local disk
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key_id
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET_NAME=your_bucket_name
```

## CI/CD Pipeline

The project uses GitHub Actions for CI/CD (`.github/workflows/ci.yml`):

1. **Test**: Runs pytest with coverage on Python 3.12
2. **Lint**: Runs ruff check and format check
3. **Build**: Builds Docker image and tests import

### Running CI Locally

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run linting
ruff check .
ruff format --check .

# Run tests
pytest --cov=app --cov-report=xml --cov-report=term -v

# Build Docker image
docker build -t aloft-backend:test .
docker run --rm aloft-backend:test python -c "import app.main; print('Import successful')"
```

## Common Tasks

### Adding a New API Endpoint

1. Create Pydantic models in `app/models/` if needed
2. Add service logic in `app/services/`
3. Create router in `app/routers/`
4. Register router in `app/main.py`
5. Add rate limiting in `app/core/dependencies.py` if needed
6. Write tests in `tests/`

### Adding a New External API Client

1. Create client in `app/clients/`
2. Implement retry logic and error handling
3. Add configuration to `app/core/config.py`
4. Add API key to `.env.example`
5. Write tests in `tests/test_*.py`

### Database Schema Changes

1. Update Pydantic models in `app/models/`
2. Add index definitions in `app/core/db.py` (ensure_indexes function)
3. Update repository methods in `app/services/*_repository.py`
4. Write migration tests if needed

### Debugging Tips

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Check MongoDB connection
curl http://localhost:8000/health/ready

# View Redis keys (requires redis-cli)
redis-cli KEYS "*"

# Check rate limit status
redis-cli GET "ratelimit:*"
```

## Performance Considerations

- **Async I/O**: Use async/await for all I/O operations
- **Connection pooling**: Reuse HTTP clients (via app.state.http_client)
- **Caching**: Use Redis for frequently accessed data
- **Batch operations**: Use bulk operations where possible
- **Indexing**: Ensure proper database indexes for query patterns

## Troubleshooting

### Common Issues

**MongoDB connection fails**
- Check MONGODB_URI in .env
- Ensure MongoDB is running (docker-compose up mongodb)
- Check network connectivity

**Redis connection fails**
- Redis is optional for core functionality
- Check REDIS_URL in .env
- Rate limiting will fail open if Redis is unavailable

**Audio synthesis fails**
- Check ELEVENLABS_API_KEY is valid
- Verify voice ID exists for your account
- Check quota limits on ElevenLabs dashboard

**Tests fail**
- Ensure all environment variables are set
- Check MongoDB and Redis are running
- Run `pytest -v` for detailed output

## Additional Resources

- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **Pydantic Documentation**: https://docs.pydantic.dev/
- **Motor Documentation**: https://motor.readthedocs.io/
- **Redis Documentation**: https://redis.io/docs/
- **Project README**: See `README.md` in project root
