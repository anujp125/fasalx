import firebase_admin
from firebase_admin import credentials, firestore
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

db = None

def init_firebase():
    global db
    try:
        if settings.FIREBASE_CREDENTIALS_PATH:
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)
        else:
            # Fallback to default credentials if path not provided (e.g. running on GCP or with GOOGLE_APPLICATION_CREDENTIALS set)
            firebase_admin.initialize_app()
            
        db = firestore.client()
        logger.info("Firebase Admin initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin: {e}")
        # Not raising here to allow app to start even if Firebase fails during dev
        # In prod, you might want to raise

def get_db():
    """
    Returns the Firestore client instance.
    """
    if db is None:
        init_firebase()
    return db
