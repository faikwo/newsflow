# NewsFlow Security Hardening

This document describes the security improvements made to NewsFlow to make it production-ready.

## Summary of Fixes

### 🔴 CRITICAL (Fixed)

#### 1. Hardcoded JWT Secret [auth.py]
**Issue:** The auth module had a fallback secret that could allow authentication bypass.
```python
# BEFORE (VULNERABLE):
SECRET_KEY = os.getenv("SECRET_KEY", "newsflow-secret-change-in-production-please")

# AFTER (SECURE):
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable must be set")
```

**Additional protection:** `main.py` also validates this on startup and exits if not set.

#### 2. SQL Injection in Admin Functions [auth.py]
**Issue:** The `admin_update_user()` function used dynamic SQL construction with f-strings.
```python
# BEFORE (VULNERABLE):
fields.append("username = ?"); values.append(update.username)
# ...
await db.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)

# AFTER (SECURE):
if update.username is not None:
    await db.execute("UPDATE users SET username = ? WHERE id = ?", (update.username, target_id))
if update.email is not None:
    await db.execute("UPDATE users SET email = ? WHERE id = ?", (update.email, target_id))
# ... separate parameterized queries
```

Also hardened `_delete_user_data()` with a whitelist of table/column names.

---

### 🟠 HIGH (Fixed)

#### 3. Weak Password Requirements [auth.py]
**Issue:** No password complexity enforcement.

**Fix:** Added `UserCreate` and `UserUpdate` validators requiring:
- Minimum 12 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit
- At least one special character (!@#$%^&* etc.)

#### 4. JWT Timezone Vulnerability [auth.py]
**Issue:** Used deprecated `datetime.utcnow()` which can cause session issues.
```python
# BEFORE:
expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

# AFTER:
expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
```

#### 5. Weak Share Link Token Validation [share.py]
**Issue:** Incomplete pattern matching allowed potential bypass.
```python
# BEFORE:
if len(token) > 40 or not token.replace("-", "").replace("_", "").isalnum():

# AFTER:
VALID_TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_-]{22}$')
if not VALID_TOKEN_PATTERN.match(token):
```

---

### 🟡 MEDIUM (Fixed)

#### 6. CORS Allows All Origins [main.py]
**Issue:** `allow_origins=["*"]` increases attack surface.

**Fix:** Made CORS origins configurable via `ALLOWED_ORIGINS` environment variable.
```python
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
```

#### 7. No Rate Limiting on Share Links [share.py, main.py]
**Issue:** Public share endpoint had no rate limiting.

**Fix:** Added `@limiter.limit("60/minute")` decorator to share endpoints.

#### 8. Verbose Error Messages [settings.py]
**Issue:** Error messages exposed internal details (stack traces, paths).
```python
# BEFORE:
return {"success": False, "models": [], "error": str(e)}

# AFTER:
logger.error(f"Ollama test error: {e}")  # Log internally
return {"success": False, "models": [], "error": "Connection failed"}  # Generic to user
```

---

### 🟢 LOW (Fixed)

#### 9. Insufficient Content Sanitization on Article Titles [CRITICAL]
**Issue:** Article titles from RSS/NewsAPI were stored without sanitization, allowing XSS attacks.

**Attack Scenario:**
1. Attacker creates malicious RSS feed with JavaScript in titles: `<title><script>alert(document.cookie)</script>News!</title>`
2. User subscribes to the feed
3. When displayed, JavaScript executes → session theft, account takeover

**Fix:**
```python
title = _sanitize_html(title)[:200]  # Sanitize all titles
```

#### 10. JWT Token in URL Query Parameters [HIGH]
**Issue:** The `get_user_from_query_token()` helper function accepted JWT via `?token=` query parameter.

**Attack Scenario:**
- JWT in URLs leaks to server logs, browser history, Referrer headers
- Attacker with log access can steal tokens and hijack sessions

**Fix:** Removed the function entirely. Use `Authorization: Bearer` header exclusively.

#### 11. XSS via Email Username [HIGH]
**Issue:** Username was interpolated into HTML email template without escaping.

**Attack Scenario:**
- User registers with username containing HTML/JavaScript
- Email digest contains malicious content
- Email client may execute scripts or render phishing content

**Fix:** 
```python
# BEFORE:
Good morning, {username}!

# AFTER:
Good morning, {escape(username)}!
```

#### 12. SSRF via Custom Feed Storage [MEDIUM]
**Issue:** Custom RSS feed URLs were stored without validation at creation time.

**Attack Scenario:**
- Attacker stores internal URL as custom feed
- Admin viewing feeds sees unvalidated URLs
- Future code paths might use the stored URL

**Fix:** Added `_is_safe_fetch_url()` validation in `add_custom_feed()` before INSERT.

#### 13. SSRF in Dead Code [MEDIUM]
**Issue:** `scrape_article_content()` had `follow_redirects=True` with no SSRF validation.

**Attack Scenario:**
- If function is used in future, DNS rebinding attacks possible
- Redirect chains can bypass initial URL checks

**Fix:** 
- Added `_is_safe_fetch_url()` validation
- Set `follow_redirects=False`
- Manually validate any redirect Location headers

#### 14. Weak CSP [MEDIUM]
**Issue:** Content Security Policy allowed `'unsafe-inline'` scripts.

**Impact:** Negates XSS protection if any inline script injection occurs.

**Fix:** Documented in nginx.conf. Note: `'unsafe-inline'` required for React default build. To harden further, configure React with CSP nonces or external scripts only.

#### 15. Long JWT Lifetime [LOW]
**Issue:** Tokens valid for 7 days with no revocation mechanism.

**Impact:** Stolen tokens remain valid for extended period.

**Fix:** Reduced to 24 hours. Consider implementing refresh tokens for longer sessions.

#### 16. Missing HSTS Header [LOW]
**Issue:** No `Strict-Transport-Security` header in nginx config.

**Impact:** First visit vulnerable to SSL stripping attacks.

**Fix:** Added HSTS header (commented out - uncomment after confirming HTTPS works).

---

## Security Tests

Automated tests have been added in `backend/tests/test_security.py`. Run them with:

```bash
cd backend
python tests/test_security.py
```

Or using pytest:
```bash
pip install pytest
cd backend
python -m pytest tests/test_security.py -v
```

These tests verify:
- No hardcoded secrets
- Password complexity is enforced
- JWT uses timezone-aware datetimes
- SQL injection protections are in place
- Token validation is strict
- Rate limiting is configured
- CORS is properly configured
- HTML sanitization is active (titles, author, source, summary)
- XXE protection is enabled
- SSRF protections in custom feeds
- JWT not in URLs
- Email content escaped

---

## Production Deployment Checklist

Before deploying to production:

- [ ] Set a strong `SECRET_KEY` (run `openssl rand -hex 32`)
- [ ] Configure `ALLOWED_ORIGINS` with your actual domain(s)
- [ ] Run security tests: `python backend/tests/test_security.py`
- [ ] Change default admin password if migrating from old install
- [ ] Set up HTTPS (the app enforces this for image URLs)
- [ ] Review firewall rules (only expose port 3000 or your chosen port)
- [ ] Consider adding fail2ban for additional brute-force protection
- [ ] Be cautious of third-party RSS feeds - only subscribe to trusted sources

---

## New Dependencies

Added for security:
- `bleach==6.1.0` - HTML sanitization
- `email-validator==2.1.1` - Email validation for user registration

---

## Attack Scenarios Now Mitigated

### Admin Account Takeover
**Before:** Attacker could forge admin tokens if default secret was active.  
**After:** App refuses to start without a properly set SECRET_KEY.

### Database Compromise via SQL Injection
**Before:** Admin endpoints vulnerable to SQL injection.  
**After:** All queries use parameterized statements with whitelisted table names.

### Information Disclosure via Share Links
**Before:** Token validation was weak; errors leaked internal details.  
**After:** Strict regex validation; generic error messages; rate limiting.

### XSS via Malicious Articles / RSS Feeds
**Before:** Article titles and content stored without sanitization.  
**After:** All text fields (title, author, source, summary) sanitized using bleach before storage.

### XXE via Malicious RSS Feeds
**Before:** RSS parser could resolve external XML entities.  
**After:** External entity resolution explicitly disabled in XML parser.

### SSRF via Ollama Endpoint
**Before:** Regular users could access `/api/settings/ollama/models` and probe internal networks.  
**After:** Endpoint restricted to admin users only.

### JWT Leakage via URLs
**Before:** Helper function accepted JWT in query parameters (leaks to logs/referrers).  
**After:** Function removed. JWT only accepted via Authorization header.

### XSS via Email
**Before:** Username not escaped in HTML email templates.  
**After:** All user-controlled content escaped with `html.escape()`.

### Weak Password Attacks
**Before:** Users could set passwords like "123" or "password".  
**After:** Strong password requirements enforced at registration.
