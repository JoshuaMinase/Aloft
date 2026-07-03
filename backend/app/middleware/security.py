"""
Security middleware for HTTP headers and security hardening.

Implements OWASP-recommended security headers and protections:
- Content Security Policy (CSP)
- Strict-Transport-Security (HSTS)
- X-Content-Type-Options
- X-Frame-Options
- X-XSS-Protection
- Referrer-Policy
- Permissions-Policy
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to all HTTP responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        
        # Content Security Policy
        # Restricts sources of content (scripts, styles, images, etc.)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' https://api.openai.com https://api.elevenlabs.io; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self';"
        )
        
        # Strict-Transport-Security
        # Enforces HTTPS for 1 year including subdomains
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )
        
        # X-Content-Type-Options
        # Prevents MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # X-Frame-Options
        # Prevents clickjacking attacks
        response.headers["X-Frame-Options"] = "DENY"
        
        # X-XSS-Protection
        # Enables XSS filter (mostly for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Referrer-Policy
        # Controls how much referrer information is sent
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Permissions-Policy (formerly Feature-Policy)
        # Controls browser features access
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=()"
        )
        
        # X-DNS-Prefetch-Control
        # Controls DNS prefetching
        response.headers["X-DNS-Prefetch-Control"] = "off"
        
        # Cross-Origin-Opener-Policy
        # Controls cross-origin opener access
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        
        # Cross-Origin-Resource-Policy
        # Controls cross-origin resource access
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        
        # Cache-Control for sensitive endpoints
        # Prevents caching of sensitive data
        if request.url.path in ["/v1/auth/me", "/v1/auth/login", "/v1/auth/refresh"]:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs all HTTP requests for security auditing and monitoring."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract client information
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Log request
        import logging
        logger = logging.getLogger("aloft.security")
        
        logger.info(
            f"Request: {request.method} {request.url.path} | "
            f"IP: {client_ip} | "
            f"User-Agent: {user_agent} | "
            f"Auth: {'Present' if 'authorization' in request.headers else 'Missing'}"
        )
        
        # Process request
        response = await call_next(request)
        
        # Log response
        logger.info(
            f"Response: {response.status_code} | "
            f"Path: {request.url.path} | "
            f"IP: {client_ip}"
        )
        
        return response


class RateLimitLoggingMiddleware(BaseHTTPMiddleware):
    """Logs rate limit violations for security monitoring."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        
        # Log rate limit violations
        if response.status_code == 429:
            import logging
            logger = logging.getLogger("aloft.security")
            
            client_ip = request.client.host if request.client else "unknown"
            logger.warning(
                f"Rate limit violation: {request.method} {request.url.path} | "
                f"IP: {client_ip} | "
                f"User-Agent: {request.headers.get('user-agent', 'unknown')}"
            )
            
            # Log to security monitor
            try:
                from app.services.security_monitoring import (
                    log_security_event,
                    security_monitor,
                )
                
                # Extract user_id from JWT if present
                user_id = None
                auth_header = request.headers.get("authorization")
                if auth_header and auth_header.startswith("Bearer "):
                    # In production, decode JWT to get user_id
                    pass
                
                security_monitor.log_rate_limit_violation(
                    user_id=user_id,
                    ip=client_ip,
                    endpoint=str(request.url.path),
                    method=request.method,
                )
                
                log_security_event(
                    event_type="RATE_LIMIT_VIOLATION",
                    severity="warning",
                    user_id=user_id,
                    ip=client_ip,
                    endpoint=str(request.url.path),
                    method=request.method,
                )
            except Exception as e:
                # Don't break the middleware if security monitoring fails
                logger.error(f"Failed to log to security monitor: {e}")
        
        return response
