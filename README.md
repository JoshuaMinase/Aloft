# Aloft

<div align="center">

**Turn any commercial flight into a live, contextual audio tour**

[![CI Status](https://github.com/JoshuaMinase/Aloft/workflows/CI/badge.svg)](https://github.com/JoshuaMinase/Aloft/actions)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

</div>

## Overview

Aloft is a location-based audio storytelling platform that transforms commercial flights into immersive experiences. Using real-time flight tracking, geospatial data, and AI-generated content, Aloft delivers contextually relevant stories about points of interest visible from the aircraft.

### Key Features

- **Real-time Flight Tracking**: Live position updates via OpenSky Network API
- **Contextual Story Generation**: AI-powered narratives using Groq LLM
- **Geospatial POI Discovery**: Multi-source point-of-interest detection (Wikipedia, Wikidata, GeoNames, OpenStreetMap)
- **Text-to-Speech Integration**: Natural voice synthesis via ElevenLabs
- **Smart Audio Mixing**: Background music blended with narration
- **Progressive Web App**: Mobile-first interface for in-flight use
- **Robust Architecture**: FastAPI backend with MongoDB, Redis, and Docker support

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Mobile App    │    │   FastAPI       │    │  External APIs  │
│   (React Native)│◄──►│   Backend       │◄──►│  (Groq, ElevenLabs,│
└─────────────────┘    │   (Python 3.12+)│    │   AviationStack)│
                       └────────┬────────┘    └─────────────────┘
                                │
                ┌───────────────┼───────────────┐
                ▼               ▼               ▼
          ┌──────────┐   ┌──────────┐   ┌──────────┐
          │ MongoDB  │   │  Redis   │   │   R2     │
          │ (Primary)│   │ (Cache)  │   │ (Storage)│
          └──────────┘   └──────────┘   └──────────┘
```

## Tech Stack

### Backend
- **Framework**: FastAPI with async/await
- **Database**: MongoDB with Motor (async driver)
- **Cache**: Redis for rate limiting and session management
- **Audio Processing**: NumPy + SoundFile
- **Authentication**: JWT with access/refresh tokens
- **Validation**: Pydantic v2
- **Testing**: Pytest with comprehensive coverage
- **Containerization**: Docker + Docker Compose

### External Integrations
- **OpenSky Network**: Real-time flight tracking
- **Groq**: LLM for story generation
- **ElevenLabs**: Text-to-speech synthesis
- **AviationStack**: Flight data enrichment
- **Wikipedia/Wikidata**: POI information
- **GeoNames**: Geospatial data
- **OpenStreetMap**: Map data via Overpass API

## Quick Start

### Prerequisites
- Python 3.12 or higher
- MongoDB 4.4+
- Redis 6.0+ (optional, for rate limiting)
- Docker (optional, for containerized deployment)

### Installation

```bash
# Clone the repository
git clone https://github.com/JoshuaMinase/Aloft.git
cd Aloft

# Navigate to backend
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys and configuration
```

### Configuration

Required environment variables in `.env`:

```env
# Core
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

### Running the Application

```bash
# Development server with auto-reload
uvicorn app.main:app --reload

# Production server
gunicorn app.main:app --config gunicorn.conf.py

# Docker Compose (includes MongoDB and Redis)
docker-compose up --build
```

The API will be available at `http://localhost:8000`

### API Documentation

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html --cov-report=term

# Run specific test file
pytest tests/test_audio_mixing.py

# Run with verbose output
pytest -v
```

### Code Quality

```bash
# Linting
ruff check .

# Auto-fix linting issues
ruff check . --fix

# Format code
ruff format .
```

### Project Structure

```
aloft/
└── backend/
    ├── app/
    │   ├── clients/      # External API integrations
    │   ├── core/         # Configuration, database, Redis
    │   ├── middleware/   # Custom middleware
    │   ├── models/       # Pydantic models
    │   ├── routers/      # FastAPI route handlers
    │   ├── services/     # Business logic
    │   └── utils/        # Utilities
    ├── tests/            # Test suite
    ├── scripts/          # Utility scripts
    ├── music_assets/     # Background music files
    └── legal_docs/       # Legal documents
```

## Security

- **Authentication**: JWT-based with access/refresh token pattern
- **Password Security**: Bcrypt hashing with salt
- **Rate Limiting**: Redis-backed per-endpoint limits
- **Input Validation**: Comprehensive Pydantic validation
- **CORS**: Configurable per environment
- **CSP**: Content-Security-Policy headers
- **Secrets Management**: Environment variables with SecretStr
- **Correlation IDs**: Request tracing across services

## Deployment

### Docker

```bash
# Build image
docker build -t aloft-backend .

# Run container
docker run -p 8000:8000 --env-file .env aloft-backend
```

### Docker Compose

```bash
# Start all services (MongoDB, Redis, Backend)
docker-compose up --build

# Stop services
docker-compose down

# View logs
docker-compose logs -f backend
```

## API Endpoints

### Core Endpoints
- `POST /v1/auth/signup` - User registration
- `POST /v1/auth/login` - User authentication
- `GET /v1/flights/{flight_id}` - Flight information
- `POST /v1/pois/discover` - Discover points of interest
- `POST /v1/stories/{poi_id}` - Generate POI story
- `POST /v1/audio/{poi_id}` - Generate audio narration
- `POST /v1/sessions/start` - Start tracking session
- `POST /v1/sessions/{session_id}/position` - Update aircraft position

See `/docs` for complete API documentation.

## Monitoring & Observability

- **Structured Logging**: JSON logs in production, console in development
- **Health Checks**: `/health/ready` and `/health/live` endpoints
- **Correlation IDs**: Automatic request tracing
- **Error Handling**: Comprehensive exception handling with user-friendly messages

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **OpenSky Network** for real-time flight data
- **Groq** for AI story generation
- **ElevenLabs** for text-to-speech synthesis
- **Wikipedia, Wikidata, GeoNames, OpenStreetMap** for geospatial data

---

**Note**: This is a personal project for demonstration purposes. External API keys are required for full functionality.
