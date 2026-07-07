# ADR 0001: Use FastAPI for Backend Framework

## Status

Accepted

## Context

The Aloft backend requires a modern, performant web framework to handle API requests, authentication, and real-time features. The application needs:

- Async/await support for high-performance I/O operations
- Automatic API documentation
- Type safety and validation
- WebSocket support for real-time flight tracking
- Easy integration with modern Python libraries

## Decision

We will use **FastAPI** as the backend framework.

### Rationale

1. **Performance**: FastAPI is built on Starlette and Pydantic, providing excellent performance with async/await support
2. **Type Safety**: Native support for Python type hints and Pydantic models ensures request/response validation
3. **Automatic Documentation**: Automatic OpenAPI/Swagger documentation generation
4. **Modern**: Built for modern Python (3.7+) with async/await support
5. **WebSocket Support**: Built-in WebSocket support for real-time features
6. **Ecosystem**: Excellent integration with popular libraries (ORMs, authentication, etc.)
7. **Developer Experience**: Clear error messages, intuitive API design

### Alternatives Considered

- **Flask**: Lacks native async support, requires additional libraries for type validation
- **Django**: Heavy framework with many features we don't need, steeper learning curve
- **Tornado**: Lower-level, requires more boilerplate for common features

## Consequences

### Positive

- Fast development with automatic validation and documentation
- Excellent performance for I/O-bound operations
- Easy to onboard new developers
- Strong type safety reduces bugs

### Negative

- Younger ecosystem compared to Flask/Django
- Some enterprise features may require additional libraries
- Learning curve for developers unfamiliar with async/await

## Implementation

FastAPI is installed via `requirements.txt`:
```
fastapi==0.136.3
uvicorn[standard]==0.34.0
```

The main application is defined in `app/main.py` with routers in `app/routers/`.

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [FastAPI Performance](https://www.techempower.com/benchmarks/)
