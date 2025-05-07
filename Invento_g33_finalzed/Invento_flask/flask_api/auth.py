import jwt
from functools import wraps
from flask import request, jsonify, current_app
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Secret key for JWT - should match Django's secret key or be in environment variable
JWT_SECRET_KEY = "your_secret_key_here"  # CHANGE THIS IN PRODUCTION!
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DELTA = timedelta(days=1)

def generate_token(user_id, username, is_staff=False, is_superuser=False):
    """Generate a JWT token for a user"""
    payload = {
        'user_id': user_id,
        'username': username,
        'is_staff': is_staff,
        'is_superuser': is_superuser,
        'exp': datetime.utcnow() + JWT_EXPIRATION_DELTA,
        'iat': datetime.utcnow()
    }
    
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token

def decode_token(token):
    """Decode a JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Expired token attempted to be used")
        return None
    except jwt.InvalidTokenError:
        logger.warning("Invalid token attempted to be used")
        return None

def token_required(f):
    """Decorator to protect API routes with JWT authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header:
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if not token:
            logger.warning("No token provided for protected endpoint")
            return jsonify({'error': 'Authentication token is missing'}), 401
        
        # Decode token
        payload = decode_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        # Add user info to request
        request.user = payload
        
        return f(*args, **kwargs)
    
    return decorated

def admin_required(f):
    """Decorator to restrict access to admin users only"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header:
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if not token:
            logger.warning("No token provided for admin endpoint")
            return jsonify({'error': 'Authentication token is missing'}), 401
        
        # Decode token
        payload = decode_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        # Check if user is admin
        if not payload.get('is_staff') and not payload.get('is_superuser'):
            logger.warning(f"Non-admin user {payload.get('username')} attempted to access admin endpoint")
            return jsonify({'error': 'Admin privileges required'}), 403
        
        # Add user info to request
        request.user = payload
        
        return f(*args, **kwargs)
    
    return decorated
