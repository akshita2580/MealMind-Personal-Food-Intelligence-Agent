"""
Security utilities for encrypting sensitive data at rest and PKCE generation.
"""
import os
import base64
import hashlib
import secrets
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

def get_encryption_key() -> bytes:
    """
    Get the encryption key from environment variables.
    If in production, fails fast if missing.
    In development, loads or generates a `.dev_encryption_key` file.
    """
    env = os.getenv("ENVIRONMENT", "development").lower()
    key = os.getenv("ENCRYPTION_KEY")
    
    if key:
        return key.encode('utf-8')
        
    if env == "production" or env == "prod":
        raise RuntimeError("FATAL: ENCRYPTION_KEY must be set in production environment")
        
    # Development fallback
    dev_key_path = ".dev_encryption_key"
    if os.path.exists(dev_key_path):
        with open(dev_key_path, "rb") as f:
            dev_key = f.read().strip()
            logger.warning("ENCRYPTION_KEY not set. Using existing %s for local development.", dev_key_path)
            return dev_key
            
    # Generate new key for local development
    dev_key = Fernet.generate_key()
    with open(dev_key_path, "wb") as f:
        f.write(dev_key)
        
    logger.warning("ENCRYPTION_KEY not set. Generated new key in %s for local development. DO NOT USE IN PRODUCTION.", dev_key_path)
    return dev_key

_fernet = Fernet(get_encryption_key())

def encrypt_token(data: str) -> str:
    """Encrypt a token string."""
    if not data:
        return data
    return _fernet.encrypt(data.encode('utf-8')).decode('utf-8')

def decrypt_token(data: str) -> str:
    """Decrypt a token string."""
    if not data:
        return data
    try:
        return _fernet.decrypt(data.encode('utf-8')).decode('utf-8')
    except Exception:
        # If decryption fails, log it and return empty or raise
        logger.error("Failed to decrypt token")
        return ""

def generate_pkce_verifier() -> str:
    """Generate a random PKCE code verifier."""
    return secrets.token_urlsafe(64)

def generate_pkce_challenge(verifier: str) -> str:
    """Generate a PKCE code challenge from a verifier using S256."""
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    return base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')

def generate_oauth_state() -> str:
    """Generate a cryptographically random OAuth state using hex (32 chars) to prevent encoding or truncation issues."""
    return secrets.token_hex(16)
