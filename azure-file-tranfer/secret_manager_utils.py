import os
from google.cloud import secretmanager
from google.api_core import client_options
import logging
from google.cloud import logging as cloud_logging

# --- Configuration ---
PROJECT_NUMBER = os.environ.get("PROJECT_NUMBER", "172022487918")
REGION_ID = os.environ.get("REGION_ID", "asia-south1")
SECRET_ID = os.environ.get("SECRET_ID", "hbl-finops-azure")
SECRET_VERSION = "latest"

# --- Cloud Logging Setup ---
logging_client = cloud_logging.Client()
logging_client.setup_logging()
logger = logging.getLogger("azure-gcs-transfer-access-secret-value")
logger.setLevel(logging.INFO)

def access_secrets():
    """
    Internal logic to fetch the secret using regional endpoints.
    """ 
    # Regional endpoint construction
    #api_endpoint = f"secretmanager.{REGION_ID}.rep.googleapis.com:443"
    # client_opts = client_options.ClientOptions(api_endpoint=api_endpoint)
    
    try:
        client = secretmanager.SecretManagerServiceClient()
        
        # Build resource name
        name = f"projects/{PROJECT_NUMBER}/secrets/{SECRET_ID}/versions/{SECRET_VERSION}"

        # FIX: Changed logger(...) to logger.info(...)
        # logger.info(f"Connecting to endpoint: {api_endpoint}")
        logger.info(f"Retrieving resource: {name}")
        
        response = client.access_secret_version(request={"name": name})
        logger.info(f"Successfully retrieved the secret for {SECRET_ID}")
        
        return response.payload.data.decode("UTF-8")

    except Exception as e:
        logger.error(f"An error occurred while accessing the secret '{SECRET_ID}': {e}")
        raise RuntimeError(f"Secret Manager Error: {str(e)}")