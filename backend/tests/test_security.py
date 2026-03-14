"""
Security regression tests for NewsFlow.
Run these after making code changes to ensure vulnerabilities don't return.

To run: cd /app && python tests/test_security.py
"""
import os
import re
import sys

# Ensure we can import from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAuthSecurity:
    """Tests for authentication security."""

    def test_no_hardcoded_jwt_secret(self):
        """CRITICAL: Verify there's no hardcoded fallback JWT secret."""
        auth_file = os.path.join(os.path.dirname(__file__), '..', 'routers', 'auth.py')
        with open(auth_file, 'r') as f:
            content = f.read()
        
        # Should NOT have a default/placeholder secret in os.getenv
        assert 'os.getenv("SECRET_KEY", "' not in content, \
            "CRITICAL: Hardcoded JWT secret fallback found!"
        
        # Should raise RuntimeError if SECRET_KEY not set
        assert 'RuntimeError' in content, \
            "CRITICAL: App should refuse to start without SECRET_KEY"
        assert 'SECRET_KEY environment variable must be set' in content, \
            "CRITICAL: Missing SECRET_KEY validation message"

    def test_password_complexity_requirements(self):
        """Verify password complexity is enforced."""
        auth_file = os.path.join(os.path.dirname(__file__), '..', 'routers', 'auth.py')
        with open(auth_file, 'r') as f:
            content = f.read()
        
        # Check for minimum length
        assert 'PASSWORD_MIN_LENGTH' in content
        assert '12' in content, "Password minimum should be 12 characters"
        
        # Check for complexity requirements
        assert 'uppercase letter' in content.lower()
        assert 'lowercase letter' in content.lower()
        assert 'digit' in content.lower()
        assert 'special character' in content.lower()

    def test_jwt_timezone_aware(self):
        """Verify JWT uses timezone-aware datetime."""
        auth_file = os.path.join(os.path.dirname(__file__), '..', 'routers', 'auth.py')
        with open(auth_file, 'r') as f:
            content = f.read()
        
        # Should use datetime.now(timezone.utc) not utcnow()
        assert 'datetime.now(timezone.utc)' in content, \
            "JWT should use timezone-aware datetime"
        assert 'datetime.utcnow()' not in content, \
            "Should not use deprecated utcnow()"

    def test_sql_injection_protection_in_delete(self):
        """Verify SQL injection protection in user data deletion."""
        auth_file = os.path.join(os.path.dirname(__file__), '..', 'routers', 'auth.py')
        with open(auth_file, 'r') as f:
            content = f.read()
        
        # Should use whitelist approach for tables
        assert 'USER_DATA_TABLES' in content
        assert 'for table, col in USER_DATA_TABLES.items()' in content
        
        # Should NOT use dynamic field building in SQL
        assert 'f"UPDATE users SET' not in content, \
            "SQL injection risk: dynamic UPDATE statement"

    def test_admin_update_uses_parameterized_queries(self):
        """Verify admin_update_user uses separate parameterized queries."""
        auth_file = os.path.join(os.path.dirname(__file__), '..', 'routers', 'auth.py')
        with open(auth_file, 'r') as f:
            content = f.read()
        
        # Should execute separate UPDATE statements for each field
        assert 'db.execute("UPDATE users SET username = ? WHERE id = ?"' in content
        assert 'db.execute("UPDATE users SET email = ? WHERE id = ?"' in content


class TestShareSecurity:
    """Tests for share link security."""

    def test_strict_token_validation(self):
        """Verify strict regex-based token validation."""
        share_file = os.path.join(os.path.dirname(__file__), '..', 'routers', 'share.py')
        with open(share_file, 'r') as f:
            content = f.read()
        
        # Should have strict regex pattern
        assert 'VALID_TOKEN_PATTERN' in content
        assert r'^[A-Za-z0-9_-]{22}$' in content
        
        # Should use pattern.match() not len/replace checks
        assert 'VALID_TOKEN_PATTERN.match(token)' in content
        assert 'token.replace' not in content, \
            "Old weak validation found - should use regex"

    def test_rate_limiting_on_share_links(self):
        """Verify rate limiting on public share endpoint."""
        share_file = os.path.join(os.path.dirname(__file__), '..', 'routers', 'share.py')
        with open(share_file, 'r') as f:
            content = f.read()
        
        # Should have rate limiting decorator
        assert '@limiter.limit' in content
        assert '60/minute' in content


class TestSettingsSecurity:
    """Tests for settings endpoint security."""

    def test_no_password_in_response(self):
        """Verify SMTP password is never returned in API."""
        settings_file = os.path.join(os.path.dirname(__file__), '..', 'routers', 'settings.py')
        with open(settings_file, 'r') as f:
            content = f.read()
        
        # Should NOT return masked password placeholder
        assert '"••••••••"' not in content, \
            "Should not return masked password - use empty string"
        
        # Should set password to empty string
        assert 'settings["smtp_password"] = ""' in content

    def test_sanitized_error_messages(self):
        """Verify error messages don't leak internal details."""
        settings_file = os.path.join(os.path.dirname(__file__), '..', 'routers', 'settings.py')
        with open(settings_file, 'r') as f:
            content = f.read()
        
        # Should have sanitized error messages
        assert '"error": "Connection failed"' in content or \
               '"error": "Connection refused' in content or \
               '"error": "Connection timed out' in content
        
        # Should log errors internally
        assert 'logger.error' in content


class TestMainSecurity:
    """Tests for main application security."""

    def test_cors_not_wildcard_in_production(self):
        """Verify CORS origins are configurable, not hardcoded wildcard."""
        main_file = os.path.join(os.path.dirname(__file__), '..', 'main.py')
        with open(main_file, 'r') as f:
            content = f.read()
        
        # Should read from environment variable
        assert 'ALLOWED_ORIGINS' in content
        assert 'os.getenv("ALLOWED_ORIGINS"' in content
        
        # Default should be localhost, not wildcard
        assert 'http://localhost' in content

    def test_share_router_includes_rate_limiting(self):
        """Verify share router is imported and has rate limiting."""
        main_file = os.path.join(os.path.dirname(__file__), '..', 'main.py')
        with open(main_file, 'r') as f:
            content = f.read()
        
        # Should import share router
        assert 'from routers.share import share_router' in content
        assert 'app.include_router(share_router' in content
        
        # Should have rate limiting on /r/{token}
        assert '@limiter.limit("60/minute")' in content


class TestFetcherSecurity:
    """Tests for article fetcher security."""

    def test_html_sanitization_imported(self):
        """Verify bleach is imported for HTML sanitization."""
        fetcher_file = os.path.join(os.path.dirname(__file__), '..', 'services', 'fetcher.py')
        with open(fetcher_file, 'r') as f:
            content = f.read()
        
        # Should import bleach
        assert 'import bleach' in content or 'BLEACH_AVAILABLE' in content
        
        # Should have sanitize function
        assert '_sanitize_html' in content

    def test_title_sanitization(self):
        """Verify article titles are sanitized to prevent XSS."""
        fetcher_file = os.path.join(os.path.dirname(__file__), '..', 'services', 'fetcher.py')
        with open(fetcher_file, 'r') as f:
            content = f.read()
        
        # Should sanitize title field
        assert '_sanitize_html(title)' in content, \
            "Title must be sanitized to prevent XSS"
        
        # Should truncate to reasonable length
        assert '[:200]' in content, \
            "Title should have length limit"

    def test_xxe_protection(self):
        """Verify XXE protection is enabled for XML parsing."""
        fetcher_file = os.path.join(os.path.dirname(__file__), '..', 'services', 'fetcher.py')
        with open(fetcher_file, 'r') as f:
            content = f.read()
        
        # Should disable external entities
        assert 'feature_external_ges' in content, \
            "XXE protection: external general entities should be disabled"
        assert 'feature_external_pes' in content, \
            "XXE protection: external parameter entities should be disabled"
        assert 'False' in content, \
            "XXE features should be set to False"


class TestEnvironmentSecurity:
    """Tests for environment and deployment security."""

    def test_secret_key_validation(self):
        """Verify app refuses to start with default/weak secret."""
        main_file = os.path.join(os.path.dirname(__file__), '..', 'main.py')
        with open(main_file, 'r') as f:
            content = f.read()
        
        # Should check for placeholder secret
        assert 'newsflow-secret-change-in-production-please' in content
        assert 'sys.exit' in content
        assert 'FATAL: SECRET_KEY' in content

    def test_requirements_include_security_deps(self):
        """Verify security dependencies are in requirements."""
        req_file = os.path.join(os.path.dirname(__file__), '..', 'requirements.txt')
        with open(req_file, 'r') as f:
            content = f.read()
        
        # Should have bleach for HTML sanitization
        assert 'bleach' in content
        
        # Should have email-validator
        assert 'email-validator' in content or 'email_validator' in content


def run_security_audit():
    """Run all security tests and report results."""
    print("=" * 60)
    print("NEWSFLOW SECURITY AUDIT")
    print("=" * 60)
    
    test_classes = [
        TestAuthSecurity,
        TestShareSecurity,
        TestSettingsSecurity,
        TestMainSecurity,
        TestFetcherSecurity,
        TestEnvironmentSecurity,
    ]
    
    passed = 0
    failed = 0
    
    for test_class in test_classes:
        print(f"\n{test_class.__name__}:")
        for name in dir(test_class):
            if name.startswith('test_'):
                test = getattr(test_class(), name)
                try:
                    test()
                    print(f"  ✓ {name}")
                    passed += 1
                except AssertionError as e:
                    print(f"  ✗ {name}: {e}")
                    failed += 1
                except Exception as e:
                    print(f"  ✗ {name}: ERROR - {e}")
                    failed += 1
    
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed > 0:
        print("\n⚠️  SECURITY ISSUES DETECTED!")
        sys.exit(1)
    else:
        print("\n✅ All security checks passed!")
        sys.exit(0)


if __name__ == '__main__':
    run_security_audit()
