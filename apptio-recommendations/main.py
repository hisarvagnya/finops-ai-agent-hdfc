import json
import requests
from functions_framework import http
from google.cloud import storage
from google.cloud import secretmanager
from google.api_core import client_options
import config 

def access_secrets(secret_id):
    """ Function to access regional secrets from Google Secret Manager """
    print(f"INFO: Accessing Secret Manager for {secret_id}...")
    api_endpoint = f"secretmanager.{config.REGION_ID}.rep.googleapis.com:443"
    client_opts = client_options.ClientOptions(api_endpoint=api_endpoint)
    client = secretmanager.SecretManagerServiceClient(client_options=client_opts)
    name = f"projects/{config.PROJECT_ID}/locations/{config.REGION_ID}/secrets/{secret_id}/versions/{config.SECRET_VERSION}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

def upload_to_gcs(data, folder_name, file_name):
    """ Function to upload data to Google Cloud Storge Bucket """
    client = storage.Client()
    bucket = client.bucket(config.BUCKET_NAME)
    if folder_name:
        blob_path = f"{folder_name}/{file_name}.json"
    else:
        blob_path = f"{file_name}.json"
    blob = bucket.blob(blob_path)
    blob.upload_from_string(data=json.dumps(data, indent=2), content_type='application/json')
    return blob_path

def get_apptio_token(key_access, key_secret):
    """ Function to login to Apptio and retrieve apptio-token """
    print("INFO: Initiating Apptio Login...")
    payload = {"keyAccess": key_access, "keySecret": key_secret}
    response = requests.post(config.LOGIN_URL, json=payload, timeout=30)
    response.raise_for_status()
    token = response.headers.get("apptio-opentoken")
    if not token:
        raise ValueError("Auth error: apptio-opentoken missing")
    print("SUCCESS: Apptio Login token retrieved.")
    return token

@http
def multi_cloud_handler(request):
    results = {}
    print("--- STARTING MULTI-CLOUD RECOMMENDATIONS SYNC ---")
    try:
         # Setup Auth
        key_access = access_secrets(config.KEY_ACCESS_ID)
        key_secret = access_secrets(config.KEY_SECRET_ID)
        token = get_apptio_token(key_access, key_secret)
        
        for provider_name, provider_info in config.PROVIDERS.items():
            results[provider_name] = []
            folder = provider_info["folder"]
            
            for resource in provider_info["resources"]:
                try:
                    print(f"INFO: Fetching {provider_name.upper()}: {resource['name']} recommendations...")
                    
                    headers = {
                        "apptio-opentoken": token,
                        "apptio-current-environment": config.ENV_ID,
                        "Content-Type": "application/json"
                    }
                    
                    res = requests.get(resource['url'], headers=headers, timeout=30)
                    res.raise_for_status()
                    
                    path = upload_to_gcs(res.json(), folder, resource['file'])
                    print(f"SUCCESS: {provider_name.upper()}: : {resource['name']} data uploaded to {path}")
                    
                    results[provider_name].append({
                        "resource": resource['name'],
                        "status": "success",
                        "path": path
                    })
                    
                except Exception as e:
                    print(f"ERROR: Failed {provider_name} {resource['name']}: {str(e)}")
                    results[provider_name].append({
                        "resource": resource['name'],
                        "status": "failed",
                        "error": str(e)
                    })

        return json.dumps(results), 200, {"Content-Type": "application/json"}

    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        return json.dumps({"error": str(e)}), 500