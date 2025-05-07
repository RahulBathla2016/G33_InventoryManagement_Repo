import requests
import logging
import json
from django.conf import settings
import jwt
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create a handler that writes log messages to a file
log_file = 'api_client.log'
file_handler = logging.FileHandler(log_file)

# Create a logging format
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Add the file handler to the logger
logger.addHandler(file_handler)

# Flask API base URL
FLASK_API_URL = getattr(settings, 'FLASK_API_URL', 'http://localhost:5000/api')

# JWT settings - should match Flask API settings
JWT_SECRET_KEY = "your_secret_key_here"  # CHANGE THIS IN PRODUCTION!
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DELTA = timedelta(days=1)

def generate_token(user):
    """
    Generate a JWT token for a Django user
    
    Args:
        user: Django User object
        
    Returns:
        str: JWT token
    """
    payload = {
        'user_id': user.id,
        'username': user.username,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'exp': datetime.utcnow() + JWT_EXPIRATION_DELTA,
        'iat': datetime.utcnow()
    }
    
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token

def api_request(method, endpoint, data=None, params=None, token=None):
    """
    Helper function to make API requests to the Flask backend

    Args:
        method (str): HTTP method (GET, POST, PUT, DELETE)
        endpoint (str): API endpoint (without leading slash)
        data (dict, optional): Data to send in the request body
        params (dict, optional): Query parameters
        token (str, optional): JWT token for authentication

    Returns:
        tuple: (response_data, status_code)
    """
    url = f"{FLASK_API_URL}/{endpoint}"
    headers = {'Content-Type': 'application/json'}

    # Add authentication token if provided
    if token:
        headers['Authorization'] = f'Bearer {token}'

    logger.info(f"Making {method} request to {url}")
    logger.info(f"Headers: {headers}")
    
    if data:
        logger.info(f"Request data: {data}")

    try:
        if method == 'GET':
            response = requests.get(url, params=params, headers=headers, timeout=10)
        elif method == 'POST':
            response = requests.post(url, json=data, headers=headers, timeout=10)
        elif method == 'PUT':
            response = requests.put(url, json=data, headers=headers, timeout=10)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers, timeout=10)
        else:
            logger.error(f"Invalid method: {method}")
            return {'error': 'Invalid method'}, 400

        # Log response details
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response headers: {response.headers}")
        logger.info(f"Response content: {response.text[:500]}...")  # Log first 500 chars

        # Check if response is successful
        if response.status_code >= 400:
            logger.error(f"API Error: {response.text}")
            try:
                error_data = response.json()
                return error_data, response.status_code
            except ValueError:
                return {'error': 'Bad request', 'message': response.text}, response.status_code

        # Try to parse JSON response
        try:
            if response.text.strip():  # Check if response has content
                return response.json(), response.status_code
            else:
                logger.warning("Empty response received")
                return {}, response.status_code
        except ValueError as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
            logger.error(f"Response content: {response.text}")
            return {'error': 'Invalid JSON response from API', 'message': response.text}, 500

    except requests.exceptions.Timeout:
        logger.error(f"Request timeout for {endpoint}")
        return {'error': 'Request timed out. Please try again later.'}, 504
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error for {endpoint}")
        return {'error': 'Could not connect to the API. Please check if the API server is running.'}, 503
    except requests.RequestException as e:
        logger.error(f"Request error for {endpoint}: {str(e)}")
        return {'error': str(e)}, 500
    except Exception as e:
        logger.error(f"Unexpected error for {endpoint}: {str(e)}")
        return {'error': f'Unexpected error: {str(e)}'}, 500
