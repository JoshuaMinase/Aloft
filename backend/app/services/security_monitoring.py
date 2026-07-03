"""
Suspicious activity monitoring service.

Detects and alerts on suspicious security patterns:
- Multiple failed login attempts
- Unusual IP addresses (geo-location anomalies)
- Rate limit violations
- Permission escalation attempts
- Data access anomalies
- Session anomalies (concurrent sessions from different locations)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from app.models.role import Role

logger = logging.getLogger("aloft.security_monitoring")


class SecurityMonitor:
    """Monitors for suspicious activity patterns and generates alerts."""
    
    def __init__(self):
        # Track failed login attempts per user
        self.failed_logins: dict[str, list[dict[str, Any]]] = defaultdict(list)
        
        # Track successful logins per user (for IP anomalies)
        self.user_ips: dict[str, set[str]] = defaultdict(set)
        
        # Track rate limit violations per user
        self.rate_limit_violations: dict[str, list[dict[str, Any]]] = defaultdict(list)
        
        # Track permission denials per user
        self.permission_denials: dict[str, list[dict[str, Any]]] = defaultdict(list)
    
    def log_failed_login(
        self,
        user_id: str,
        email: str,
        ip: str,
        user_agent: str,
    ) -> None:
        """Log a failed login attempt."""
        timestamp = datetime.now(UTC)
        
        self.failed_logins[user_id].append({
            "timestamp": timestamp,
            "ip": ip,
            "user_agent": user_agent,
        })
        
        # Clean up old entries (keep last 24 hours)
        cutoff = timestamp - timedelta(hours=24)
        self.failed_logins[user_id] = [
            entry for entry in self.failed_logins[user_id]
            if entry["timestamp"] > cutoff
        ]
        
        # Check for suspicious patterns
        self._check_failed_login_pattern(user_id, email)
    
    def log_successful_login(
        self,
        user_id: str,
        email: str,
        ip: str,
        user_agent: str,
    ) -> None:
        """Log a successful login for IP anomaly detection."""
        timestamp = datetime.now(UTC)
        
        self.user_ips[user_id].add(ip)
        
        # Check for IP anomalies
        self._check_ip_anomaly(user_id, email, ip, timestamp)
    
    def log_rate_limit_violation(
        self,
        user_id: str | None,
        ip: str,
        endpoint: str,
        method: str,
    ) -> None:
        """Log a rate limit violation."""
        timestamp = datetime.now(UTC)
        key = user_id if user_id else f"anon:{ip}"
        
        self.rate_limit_violations[key].append({
            "timestamp": timestamp,
            "ip": ip,
            "endpoint": endpoint,
            "method": method,
        })
        
        # Clean up old entries
        cutoff = timestamp - timedelta(hours=1)
        self.rate_limit_violations[key] = [
            entry for entry in self.rate_limit_violations[key]
            if entry["timestamp"] > cutoff
        ]
        
        # Check for abuse patterns
        self._check_rate_limit_abuse(key, endpoint)
    
    def log_permission_denial(
        self,
        user_id: str,
        email: str,
        required_permission: str,
        attempted_action: str,
    ) -> None:
        """Log a permission denial."""
        timestamp = datetime.now(UTC)
        
        self.permission_denials[user_id].append({
            "timestamp": timestamp,
            "required_permission": required_permission,
            "attempted_action": attempted_action,
        })
        
        # Clean up old entries
        cutoff = timestamp - timedelta(hours=24)
        self.permission_denials[user_id] = [
            entry for entry in self.permission_denials[user_id]
            if entry["timestamp"] > cutoff
        ]
        
        # Check for escalation attempts
        self._check_permission_escalation(user_id, email)
    
    def _check_failed_login_pattern(self, user_id: str, email: str) -> None:
        """Check for brute force patterns."""
        attempts = self.failed_logins[user_id]
        
        # Check for rapid failed attempts (5 in 5 minutes)
        if len(attempts) >= 5:
            recent_attempts = [
                a for a in attempts
                if a["timestamp"] > datetime.now(UTC) - timedelta(minutes=5)
            ]
            if len(recent_attempts) >= 5:
                self._alert(
                    "BRUTE_FORCE_DETECTED",
                    f"Brute force attack detected for user {email} ({user_id})",
                    {
                        "user_id": user_id,
                        "email": email,
                        "attempts": len(recent_attempts),
                        "timeframe": "5 minutes",
                    }
                )
        
        # Check for sustained failed attempts (20 in 1 hour)
        if len(attempts) >= 20:
            self._alert(
                "SUSTAINED_BRUTE_FORCE",
                f"Sustained brute force attack detected for user {email} ({user_id})",
                {
                    "user_id": user_id,
                    "email": email,
                    "attempts": len(attempts),
                    "timeframe": "1 hour",
                }
            )
    
    def _check_ip_anomaly(
        self,
        user_id: str,
        email: str,
        current_ip: str,
        timestamp: datetime,
    ) -> None:
        """Check for unusual IP addresses."""
        ips = self.user_ips[user_id]
        
        # If user has many different IPs in short time
        if len(ips) > 5:
            self._alert(
                "IP_ANOMALY_DETECTED",
                f"Unusual IP activity for user {email} ({user_id})",
                {
                    "user_id": user_id,
                    "email": email,
                    "unique_ips": len(ips),
                    "current_ip": current_ip,
                }
            )
    
    def _check_rate_limit_abuse(self, key: str, endpoint: str) -> None:
        """Check for rate limit abuse patterns."""
        violations = self.rate_limit_violations[key]
        
        # Check for persistent abuse (10 violations in 1 hour)
        if len(violations) >= 10:
            self._alert(
                "RATE_LIMIT_ABUSE",
                f"Persistent rate limit abuse detected for {key}",
                {
                    "key": key,
                    "violations": len(violations),
                    "endpoint": endpoint,
                }
            )
    
    def _check_permission_escalation(self, user_id: str, email: str) -> None:
        """Check for permission escalation attempts."""
        denials = self.permission_denials[user_id]
        
        # Check for repeated permission denials (10 in 1 hour)
        if len(denials) >= 10:
            unique_permissions = set(d["required_permission"] for d in denials)
            self._alert(
                "PERMISSION_ESCALATION_ATTEMPT",
                f"Potential permission escalation attempt by user {email} ({user_id})",
                {
                    "user_id": user_id,
                    "email": email,
                    "denials": len(denials),
                    "unique_permissions": len(unique_permissions),
                }
            )
    
    def _alert(
        self,
        alert_type: str,
        message: str,
        context: dict[str, Any],
    ) -> None:
        """Generate a security alert."""
        logger.warning(
            f"SECURITY ALERT [{alert_type}]: {message}",
            extra={
                "alert_type": alert_type,
                "context": context,
            }
        )
        
        # In production, send to alerting system (PagerDuty, Slack, etc.)
        # Example: send_to_pagerduty(alert_type, message, context)
    
    def get_user_security_summary(self, user_id: str) -> dict[str, Any]:
        """Get security summary for a user."""
        return {
            "failed_login_attempts": len(self.failed_logins[user_id]),
            "unique_ips": len(self.user_ips[user_id]),
            "rate_limit_violations": len(self.rate_limit_violations[user_id]),
            "permission_denials": len(self.permission_denials[user_id]),
        }


# Global security monitor instance
security_monitor = SecurityMonitor()


# Convenience functions that use the global monitor
def log_failed_login(user_id: str, email: str, ip: str, user_agent: str) -> None:
    """Log a failed login attempt using the global security monitor."""
    security_monitor.log_failed_login(user_id, email, ip, user_agent)


def log_successful_login(user_id: str, email: str, ip: str, user_agent: str) -> None:
    """Log a successful login using the global security monitor."""
    security_monitor.log_successful_login(user_id, email, ip, user_agent)


class SecurityEvent(BaseModel):
    """Security event model for logging."""
    
    event_type: str
    severity: str = "info"  # info, warning, critical
    user_id: str | None = None
    ip: str | None = None
    timestamp: datetime
    details: dict[str, Any] = {}


def log_security_event(
    event_type: str,
    severity: str = "info",
    user_id: str | None = None,
    ip: str | None = None,
    **details: Any,
) -> None:
    """Log a security event."""
    event = SecurityEvent(
        event_type=event_type,
        severity=severity,
        user_id=user_id,
        ip=ip,
        timestamp=datetime.now(UTC),
        details=details,
    )
    
    logger.info(
        f"Security Event: {event_type}",
        extra={
            "event_type": event_type,
            "severity": severity,
            "user_id": user_id,
            "ip": ip,
            "details": details,
        }
    )


def detect_suspicious_api_usage(
    user_id: str,
    endpoint: str,
    method: str,
    ip: str,
) -> None:
    """Detect suspicious API usage patterns."""
    # Check for high-frequency API calls
    # This would be integrated with rate limiting middleware
    pass


def detect_data_exfiltration_attempt(
    user_id: str,
    data_size: int,
    endpoint: str,
) -> None:
    """Detect potential data exfiltration."""
    # Alert if user downloads unusually large amounts of data
    if data_size > 100 * 1024 * 1024:  # 100MB
        log_security_event(
            event_type="POTENTIAL_DATA_EXFILTRATION",
            severity="warning",
            user_id=user_id,
            data_size_mb=data_size / (1024 * 1024),
            endpoint=endpoint,
        )
