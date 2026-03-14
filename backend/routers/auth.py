"""
Authentication router with hardened security:
- No hardcoded secrets (must be set via environment)
- Strong password requirements enforced
- SQL injection protection via whitelist approach
- Proper timezone-aware JWT tokens
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, validator, EmailStr
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
import os
import re
import warnings
from database import get_db, DB_PATH
import aiosqlite

router = APIRouter()

warnings.filterwarnings("ignore", ".*error reading bcrypt version.*")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# SECURITY FIX: No hardcoded fallback - app will refuse to start without SECRET_KEY
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "FATAL: SECRET_KEY environment variable must be set. "
        "Generate one with: openssl rand -hex 32"
    )

ALGORITHM = "HS256"
# SECURITY FIX: Reduced token lifetime from 7 days to 24 hours (LOW-01)
# For production, consider implementing refresh tokens for longer sessions
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Password complexity requirements
PASSWORD_MIN_LENGTH = 12
PASSWORD_REGEX = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*(),.?":{}|<>\[\]\\/\-_+=])[a-zA-Z\d!@#$%^&*(),.?":{}|<>\[\]\\/\-_+=]{12,}$'
)

# SQL injection protection: Whitelist of allowed table/column names for user data deletion
USER_DATA_TABLES = {
    "user_article_interactions": "user_id",
    "user_topics": "user_id",
    "user_settings": "user_id",
    "user_topic_affinity": "user_id",
    "article_clicks": "user_id",
    "share_links": "user_id",
    "saved_articles": "user_id",
    "digest_schedule": "user_id",
    "custom_feeds": "user_id",
}


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

    @validator('username')
    def validate_username(cls, v):
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters')
        if len(v) > 50:
            raise ValueError('Username must be less than 50 characters')
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Username can only contain letters, numbers, underscores, and hyphens')
        return v

    @validator('password')
    def validate_password(cls, v):
        if len(v) < PASSWORD_MIN_LENGTH:
            raise ValueError(f'Password must be at least {PASSWORD_MIN_LENGTH} characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>\[\]\\/\-_+=]', v):
            raise ValueError('Password must contain at least one special character (!@#$%^&* etc.)')
        return v


class Token(BaseModel):
    access_token: str
    token_type: str
    username: str
    is_admin: bool


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    is_admin: Optional[bool] = None

    @validator('password')
    def validate_password_optional(cls, v):
        if v is None or v == '':
            return v
        if len(v) < PASSWORD_MIN_LENGTH:
            raise ValueError(f'Password must be at least {PASSWORD_MIN_LENGTH} characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>\[\]\\/\-_+=]', v):
            raise ValueError('Password must contain at least one special character')
        return v


def create_access_token(data: dict):
    """Create JWT token with timezone-aware expiration."""
    to_encode = data.copy()
    # SECURITY FIX: Use timezone-aware datetime (not deprecated utcnow())
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = int(user_id_str)
    except (JWTError, ValueError):
        raise credentials_exception

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
            user = await cur.fetchone()
    if user is None:
        raise credentials_exception
    return dict(user)


async def get_admin_user(current_user: dict = Depends(get_current_user)):
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


async def _delete_user_data(db, user_id: int):
    """
    Delete all data belonging to a user.
    SECURITY FIX: Uses whitelist to prevent SQL injection.
    """
    # SECURITY FIX: Whitelist-based table/column names prevent SQL injection
    for table, col in USER_DATA_TABLES.items():
        await db.execute(f"DELETE FROM {table} WHERE {col} = ?", (user_id,))
    await db.execute("DELETE FROM users WHERE id = ?", (user_id,))


@router.get("/signup-enabled")
async def signup_enabled():
    """Public endpoint — lets the login page know whether to show the register tab."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT value FROM app_settings WHERE key = 'allow_signups'"
        ) as cur:
            row = await cur.fetchone()
    enabled = (row["value"] if row else "true").lower() not in ("false", "0", "no")
    return {"enabled": enabled}


@router.post("/register", response_model=Token)
@limiter.limit("5/minute")
async def register(request: Request, user: UserCreate):
    # Check if signups are enabled (always allow if no users exist yet)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) as count FROM users") as cur:
            count_row = await cur.fetchone()
        user_count = count_row["count"]

        if user_count > 0:
            async with db.execute(
                "SELECT value FROM app_settings WHERE key = 'allow_signups'"
            ) as cur:
                setting = await cur.fetchone()
            allowed = (setting["value"] if setting else "true").lower() not in ("false", "0", "no")
            if not allowed:
                raise HTTPException(status_code=403, detail="New registrations are currently disabled.")

        async with db.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (user.username, user.email)
        ) as cur:
            existing = await cur.fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="Username or email already exists")

        is_admin = 1 if user_count == 0 else 0
        hashed = pwd_context.hash(user.password)
        async with db.execute(
            "INSERT INTO users (username, email, hashed_password, is_admin) VALUES (?, ?, ?, ?)",
            (user.username, user.email, hashed, is_admin)
        ) as cur:
            user_id = cur.lastrowid
        await db.commit()

    token = create_access_token({"sub": user_id})
    return Token(access_token=token, token_type="bearer", username=user.username, is_admin=bool(is_admin))


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE username = ?", (form_data.username,)) as cur:
            user = await cur.fetchone()

    if not user or not pwd_context.verify(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    token = create_access_token({"sub": user["id"]})
    return Token(access_token=token, token_type="bearer",
                 username=user["username"], is_admin=bool(user["is_admin"]))


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {k: v for k, v in current_user.items() if k != "hashed_password"}


@router.delete("/me")
async def delete_own_account(current_user: dict = Depends(get_current_user)):
    """User deletes their own account. Blocked if they are the only admin."""
    user_id = current_user["id"]
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if current_user.get("is_admin"):
            async with db.execute(
                "SELECT COUNT(*) as c FROM users WHERE is_admin = 1"
            ) as cur:
                row = await cur.fetchone()
            if row["c"] <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="You are the only admin. Promote another user to admin before deleting your account."
                )
        await _delete_user_data(db, user_id)
        await db.commit()
    return {"status": "ok", "message": "Account deleted"}


# ── Admin: list all users ─────────────────────────────────────────────────────

@router.get("/users")
async def list_users(admin: dict = Depends(get_admin_user)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, username, email, is_admin, created_at FROM users ORDER BY id"
        ) as cur:
            users = [dict(r) for r in await cur.fetchall()]
    return {"users": users}


# ── Admin: update any user ────────────────────────────────────────────────────

@router.patch("/users/{target_id}")
async def admin_update_user(
    target_id: int,
    update: UserUpdate,
    admin: dict = Depends(get_admin_user)
):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE id = ?", (target_id,)) as cur:
            target = await cur.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")

        # Guard: can't demote the last admin
        if update.is_admin is False and target["is_admin"]:
            async with db.execute("SELECT COUNT(*) as c FROM users WHERE is_admin = 1") as cur:
                row = await cur.fetchone()
            if row["c"] <= 1:
                raise HTTPException(status_code=400, detail="Cannot demote the only admin")

        # SECURITY FIX: Use parameterized updates instead of dynamic SQL construction
        updates_made = False
        
        if update.username is not None:
            await db.execute("UPDATE users SET username = ? WHERE id = ?", (update.username, target_id))
            updates_made = True
            
        if update.email is not None:
            await db.execute("UPDATE users SET email = ? WHERE id = ?", (update.email, target_id))
            updates_made = True
            
        if update.password is not None and update.password.strip():
            hashed = pwd_context.hash(update.password)
            await db.execute("UPDATE users SET hashed_password = ? WHERE id = ?", (hashed, target_id))
            updates_made = True
            
        if update.is_admin is not None:
            await db.execute("UPDATE users SET is_admin = ? WHERE id = ?", (1 if update.is_admin else 0, target_id))
            updates_made = True

        if updates_made:
            await db.commit()

    return {"status": "ok"}


# ── Admin: delete any user ────────────────────────────────────────────────────

@router.delete("/users/{target_id}")
async def admin_delete_user(
    target_id: int,
    admin: dict = Depends(get_admin_user)
):
    if target_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Use 'Delete my account' to delete your own account")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE id = ?", (target_id,)) as cur:
            target = await cur.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")

        if target["is_admin"]:
            async with db.execute("SELECT COUNT(*) as c FROM users WHERE is_admin = 1") as cur:
                row = await cur.fetchone()
            if row["c"] <= 1:
                raise HTTPException(status_code=400, detail="Cannot delete the only admin account")

        await _delete_user_data(db, target_id)
        await db.commit()

    return {"status": "ok"}


# ── Password reset ────────────────────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    password: str

    @validator('password')
    def validate_new_password(cls, v):
        if len(v) < PASSWORD_MIN_LENGTH:
            raise ValueError(f'Password must be at least {PASSWORD_MIN_LENGTH} characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>\[\]\\/\-_+=]', v):
            raise ValueError('Password must contain at least one special character')
        return v


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(request: Request, body: ForgotPasswordRequest):
    """
    Always returns 200 so attackers cannot enumerate registered emails.
    Sends a reset link only if the email exists and SMTP is configured.
    """
    import secrets as _secrets
    from services.email_service import send_password_reset_email

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id FROM users WHERE email = ?", (body.email,)) as cur:
            user = await cur.fetchone()

        if user:
            # Expire any existing unused tokens for this user first
            await db.execute(
                "UPDATE password_resets SET used = 1 WHERE user_id = ? AND used = 0",
                (user["id"],)
            )
            token = _secrets.token_urlsafe(32)
            await db.execute(
                "INSERT INTO password_resets (user_id, token) VALUES (?, ?)",
                (user["id"], token)
            )
            await db.commit()

            try:
                await send_password_reset_email(body.email, token)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Password reset email failed: {e}")

    return {"status": "ok", "message": "If that email is registered you will receive a reset link shortly."}


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(request: Request, body: ResetPasswordRequest):
    """Validate the token, enforce 1-hour expiry, then set the new password."""
    from datetime import datetime, timezone, timedelta

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM password_resets WHERE token = ? AND used = 0",
            (body.token,)
        ) as cur:
            reset = await cur.fetchone()

        if not reset:
            raise HTTPException(status_code=400, detail="Invalid or expired reset link.")

        created = datetime.fromisoformat(reset["created_at"]).replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - created > timedelta(hours=1):
            await db.execute(
                "UPDATE password_resets SET used = 1 WHERE id = ?", (reset["id"],)
            )
            await db.commit()
            raise HTTPException(status_code=400, detail="Reset link has expired. Please request a new one.")

        hashed = pwd_context.hash(body.password)
        await db.execute(
            "UPDATE users SET hashed_password = ? WHERE id = ?",
            (hashed, reset["user_id"])
        )
        await db.execute(
            "UPDATE password_resets SET used = 1 WHERE id = ?", (reset["id"],)
        )
        await db.commit()

    return {"status": "ok", "message": "Password updated successfully. You can now sign in."}
