# Contributing to Aloft

Thank you for your interest in contributing to Aloft! This document provides guidelines and instructions for contributing to the project.

## Getting Started

### Prerequisites

- Python 3.12 or higher
- MongoDB 4.4+
- Redis 6.0+ (optional)
- Docker (optional)
- Git

### Setting Up Development Environment

1. **Fork and Clone**
   ```bash
   # Fork the repository on GitHub
   git clone https://github.com/YOUR_USERNAME/Aloft.git
   cd Aloft
   ```

2. **Create Virtual Environment**
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

4. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Run Tests**
   ```bash
   pytest
   ```

## Development Workflow

### Branch Strategy

- `main` - Production-ready code
- `develop` - Integration branch for features
- `feature/*` - New features
- `bugfix/*` - Bug fixes
- `hotfix/*` - Critical production fixes

### Creating a Branch

```bash
git checkout -b feature/your-feature-name
```

### Making Changes

1. **Code Style**
   - Follow existing code style (100 character line length)
   - Use type hints for all function signatures
   - Write docstrings for functions and classes
   - Run `ruff check .` and `ruff format .` before committing

2. **Testing**
   - Write tests for new functionality
   - Ensure all existing tests pass
   - Aim for high test coverage
   - Run `pytest --cov=app` to check coverage

3. **Commit Messages**
   - Use clear, descriptive commit messages
   - Format: `type: subject`
   - Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
   - Example: `feat: add user authentication endpoint`

### Pull Request Process

1. **Update Documentation**
   - Update README.md if needed
   - Add comments to complex code
   - Update API documentation

2. **Submit PR**
   - Push to your fork
   - Create pull request to `main` or `develop`
   - Fill out the PR template
   - Link related issues

3. **Code Review**
   - Address review feedback
   - Keep PRs focused and small
   - Respond to comments promptly

## Code Standards

### Python Code Style

- **Line Length**: 100 characters
- **Import Order**: Standard library → third-party → local
- **Type Hints**: Required for all function signatures
- **Docstrings**: Google-style docstrings
- **Naming**: 
  - Functions: `snake_case`
  - Classes: `PascalCase`
  - Constants: `UPPER_SNAKE_CASE`

### API Design

- **Routes**: Prefixed with `/v1/` for versioning
- **Responses**: Consistent JSON format
- **Errors**: HTTPException with descriptive messages
- **Validation**: Pydantic models for all inputs/outputs

### Database Conventions

- **Collections**: Plural, lowercase (e.g., `users`, `pois`)
- **Indexes**: Descriptive names (e.g., `users_email_unique`)
- **TTL**: Use for time-based data (sessions, cache)

## Testing Guidelines

### Writing Tests

- **Unit Tests**: Test individual functions/classes
- **Integration Tests**: Test API endpoints
- **Coverage**: Aim for >80% coverage
- **Naming**: `test_<function>_<scenario>`

### Test Structure

```python
def test_function_scenario():
    # Arrange
    input_data = setup_test_data()
    
    # Act
    result = function_to_test(input_data)
    
    # Assert
    assert result == expected_output
```

### Running Tests

```bash
# All tests
pytest

# Specific file
pytest tests/test_auth.py

# With coverage
pytest --cov=app --cov-report=html

# Verbose output
pytest -v
```

## Documentation

### Code Documentation

- Docstrings for all public functions/classes
- Inline comments for complex logic
- Type hints for all parameters

### Project Documentation

- README.md: Project overview and quick start
- CONTRIBUTING.md: Contribution guidelines (this file)
- docs/DEVELOPMENT.md: Detailed development guide
- API docs: Auto-generated via FastAPI

## Issue Reporting

### Bug Reports

Include:
- Description of the bug
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment details (Python version, OS)
- Logs/error messages

### Feature Requests

Include:
- Description of the feature
- Use case
- Proposed implementation (if known)
- Alternatives considered

## Code of Conduct

### Be Respectful

- Respect different viewpoints and experiences
- Accept constructive criticism
- Focus on what is best for the community
- Show empathy towards other community members

### Be Inclusive

- Welcome newcomers and help them learn
- Be considerate in your interactions
- Use inclusive language

### Be Professional

- Keep discussions professional
- Avoid personal attacks
- Focus on the code, not the person

## Getting Help

- **Documentation**: Check docs/ folder
- **Issues**: Search existing GitHub issues
- **Discussions**: Use GitHub Discussions for questions
- **Email**: Contact maintainers for private matters

## Recognition

Contributors will be recognized in:
- CONTRIBUTORS.md file
- Release notes
- Project documentation

Thank you for contributing to Aloft! 🚀
