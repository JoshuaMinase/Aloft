# Aloft

Aloft turns any commercial flight into a live audio tour.

## Python Version Compatibility

**Python 3.13 Compatibility:** The application now supports Python 3.13+ with graceful degradation for audio mixing functionality.

- **Python 3.12 or earlier:** Full functionality including audio mixing
- **Python 3.13+:** All core functionality works; audio mixing is gracefully disabled with a clear error message

**Recommended:** Python 3.12 for full audio support. Use `.python-version` file for automatic version selection with pyenv or similar tools.

## Quick Start

### Prerequisites
- Python 3.12+ (3.12 recommended for full audio support)
- MongoDB
- Redis (optional, for rate limiting and sessions)

### Installation

```bash
cd backend
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the backend directory:

```env
ENVIRONMENT=development
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=aloft
JWT_SECRET_KEY=your-secret-key-here
GROQ_API_KEY=your-groq-api-key
ELEVENLABS_API_KEY=your-elevenlabs-api-key
```

### Running the Application

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

## API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Security

This project uses:
- JWT authentication with access and refresh tokens
- Bcrypt password hashing
- Rate limiting on sensitive endpoints
- Input validation with Pydantic

## License

MIT