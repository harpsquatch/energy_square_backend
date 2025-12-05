"""
Authentication Service

Handles user authentication, password hashing, and JWT token management.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
import hashlib
import secrets
import jwt

from app.models.auth_model import User, TokenData

logger = logging.getLogger(__name__)

# Simple secret key - in production, use environment variable
SECRET_KEY = secrets.token_urlsafe(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


class AuthService:
    """Service for user authentication and token management."""
    
    def __init__(self):
        """Initialize auth service."""
        self._users_cache: dict[str, User] = {}
        self._mongodb_available = False
        logger.info("AuthService initialized")
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using SHA-256.
        
        Args:
            password: Plain text password
            
        Returns:
            Hashed password (hex string)
        """
        return hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash.
        
        Args:
            plain_password: Plain text password to verify
            hashed_password: Stored password hash
            
        Returns:
            True if password matches, False otherwise
        """
        return AuthService.hash_password(plain_password) == hashed_password
    
    @staticmethod
    def create_access_token(data: TokenData, expires_delta: Optional[timedelta] = None) -> str:
        """
        Create a JWT access token.
        
        Args:
            data: Token data to encode
            expires_delta: Token expiration time (default: 24 hours)
            
        Returns:
            Encoded JWT token
        """
        to_encode = data.dict()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def decode_access_token(token: str) -> Optional[TokenData]:
        """
        Decode and validate a JWT access token.
        
        Args:
            token: JWT token to decode
            
        Returns:
            TokenData if valid, None if invalid or expired
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id: str = payload.get("user_id")
            role: str = payload.get("role")
            member_id: Optional[str] = payload.get("member_id")
            
            if user_id is None:
                return None
            
            return TokenData(user_id=user_id, role=role, member_id=member_id)
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.JWTError as e:
            logger.warning(f"JWT decode error: {e}")
            return None
    
    async def _load_users_from_db(self):
        """Load users from MongoDB."""
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            collection = db[Collections.USERS]
            
            users = await collection.find({}).to_list(length=None)
            for user_dict in users:
                user_dict.pop('_id', None)  # Remove MongoDB _id
                user = User(**user_dict)
                self._users_cache[user.user_id] = user
            
            self._mongodb_available = True
            logger.info(f"Loaded {len(users)} users from MongoDB")
            
        except Exception as e:
            logger.warning(f"Could not load users from MongoDB: {e}")
            self._mongodb_available = False
    
    async def _save_user_to_db(self, user: User):
        """Save or update a user in MongoDB."""
        try:
            from app.db.database import get_database, Collections
            
            db = await get_database()
            collection = db[Collections.USERS]
            
            user_dict = user.dict()
            await collection.update_one(
                {"user_id": user.user_id},
                {"$set": user_dict},
                upsert=True
            )
            logger.debug(f"Saved user {user.user_id} to MongoDB")
            
        except Exception as e:
            logger.error(f"Error saving user to MongoDB: {e}")
    
    async def get_user(self, user_id: str) -> Optional[User]:
        """
        Get user by user_id.
        
        Args:
            user_id: User identifier
            
        Returns:
            User object if found, None otherwise
        """
        # Check cache first
        if user_id in self._users_cache:
            return self._users_cache[user_id]
        
        # Try loading from DB if not cached
        if not self._mongodb_available:
            await self._load_users_from_db()
        
        return self._users_cache.get(user_id)
    
    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate a user with username and password.
        
        Args:
            username: Username or email
            password: Plain text password
            
        Returns:
            User object if authentication successful, None otherwise
        """
        user = await self.get_user(username)
        
        if not user:
            logger.warning(f"User not found: {username}")
            return None
        
        if not user.is_active:
            logger.warning(f"User account is inactive: {username}")
            return None
        
        if not self.verify_password(password, user.password_hash):
            logger.warning(f"Invalid password for user: {username}")
            return None
        
        # Update last login time
        user.last_login = datetime.utcnow()
        self._users_cache[user.user_id] = user
        await self._save_user_to_db(user)
        
        logger.info(f"User authenticated successfully: {username}")
        return user
    
    async def create_user(
        self,
        user_id: str,
        password: str,
        full_name: str,
        role: str = "member",
        member_id: Optional[str] = None
    ) -> User:
        """
        Create a new user.
        
        Args:
            user_id: Unique user identifier
            password: Plain text password (will be hashed)
            full_name: User's full name
            role: User role (member, manager, admin)
            member_id: Associated member ID for dashboard access
            
        Returns:
            Created User object
        """
        password_hash = self.hash_password(password)
        
        user = User(
            user_id=user_id,
            password_hash=password_hash,
            full_name=full_name,
            role=role,
            member_id=member_id,
            created_at=datetime.utcnow(),
            is_active=True
        )
        
        self._users_cache[user.user_id] = user
        await self._save_user_to_db(user)
        
        logger.info(f"Created new user: {user_id} (role: {role})")
        return user


# Global service instance
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get the global auth service instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service

