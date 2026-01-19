import os
import requests
import datetime
import logging
import boto3
from flask import jsonify, Request
from google.cloud import storage
from google.cloud import logging as cloud_logging
from botocore.exceptions import ClientError
from google.api_core.exceptions import GoogleAPICallError

# --- Logging Setup ---
logging_client = cloud_logging.Client()
logging_client.setup_logging()
logger = logging.getLogger("aws-s3-gcs-transfer")
logger.setLevel(logging.INFO)

# --- Configuration  ---
AWS_ROLE_ARN = os.environ.get("AWS_ROLE_ARN", "arn:aws:iam::001614206647:role/hbl-aws-cam-role-finops-hdfc-ltd")
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "hbl-aws-aps1-finops-genai-chatbot-gcpsync-bucket")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "finops-agent-aws-billing-files")
GCS_DESTINATION_FOLDER = os.environ.get("GCS_DESTINATION_FOLDER", "hdfc_aws")


month_map = {
    1: 'January', 2: 'February', 3: 'March', 4: 'April',
    5: 'May', 6: 'June', 7: 'July', 8: 'August',
    9: 'September', 10: 'October', 11: 'November', 12: 'December'
}
days_dict = {
    '1': 31,
    '2': 28,
    '3': 31,
    '4': 30,
    '5': 31,
    '6': 30,
    '7': 31,
    '8': 31,
    '9': 30,
    '10': 31,
    '11': 30,
    '12': 31
}
def get_aws_credentials():
    try:
        logger.info("Fetching GCP metadata token for AWS federation.")
        metadata_server_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=sts.amazonaws.com"
        token_response = requests.get(metadata_server_url, headers={"Metadata-Flavor": "Google"})
        token_response.raise_for_status()
        gcp_token = token_response.text

        sts_client = boto3.client('sts', region_name=AWS_REGION)
        response = sts_client.assume_role_with_web_identity(
            RoleArn=AWS_ROLE_ARN,
            RoleSessionName="gcp-cloudrun-s3-gcs-transfer",
            WebIdentityToken=gcp_token,
            DurationSeconds=3600
        )
        credentials = response['Credentials']
        return {
            'aws_access_key_id': credentials['AccessKeyId'],
            'aws_secret_access_key': credentials['SecretAccessKey'],
            'aws_session_token': credentials['SessionToken']
        }
    except Exception as e:
        logger.error(f"Credential Error: {e}")
        raise

# def _get_target_prefix(year, month, date_folder_prefix):
#     """
#     Calculates the target blob prefix
#     """
#     try:

#         billing_period = f"BILLING_PERIOD={year}-{month:02d}"
       
#         target_prefix = f"hbl-aws-aps1-finops-genai-chatbot-gcpsync-bucket/finops-genai-chatbot-gcpsync-data-export/data/{billing_period}/{date_folder_prefix}"
        
#         month_name = month_map[month]
#         return target_prefix, month_name
   
#     except Exception as e:
#         logger.exception(f"Error calculating prefix for {year}-{month}: {e}")
#         raise

def _get_previous_date_with_offset():
    """
    Calculates the target date by manually subtracting 3 days.
    Handles month boundaries using a days-per-month dictionary.
    """

    today = datetime.date.today()
    current_day = today.day
    current_month = today.month
    current_year = today.year

    def is_leap_year(year):
        return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

    days_dict["2"] = 29 if is_leap_year(current_year) else 28

    try:
        target_date = today.replace(day=current_day - 3)
        target_year = target_date.year
        target_month = target_date.month

    except ValueError:
        previous_month = current_month - 1
        previous_year = current_year

        if previous_month == 0:
            previous_month = 12
            previous_year -= 1

        days_in_previous_month = days_dict[str(previous_month)]

        adjusted_day = current_day - 3 + days_in_previous_month

        target_date = datetime.date(previous_year, previous_month, adjusted_day)
        target_year = target_date.year
        target_month = target_date.month

    return target_date, target_year, target_month


def entry_point(request):
    try:
        aws_creds = get_aws_credentials()
        s3_client = boto3.client('s3', region_name=AWS_REGION, **aws_creds)
        
        gcs_client = storage.Client()
        gcs_bucket = gcs_client.bucket(GCS_BUCKET_NAME)


        found_files = []

        target_date, target_year, target_month = _get_previous_date_with_offset()
        target_date_str = target_date.strftime("%Y-%m-%d")

        billing_period_prefix = f"hbl-aws-aps1-finops-genai-chatbot-gcpsync-bucket/finops-genai-chatbot-gcpsync-data-export/data/BILLING_PERIOD={target_year}-{target_month:02d}/"
        
        logger.info(f"Scanning base prefix: {billing_period_prefix} looking for folder starting with {target_date_str}")

        # Find the Specific Date Folder 
        # We list the billing period folder to find the T-3 specific subfolder
        paginator = s3_client.get_paginator('list_objects_v2')
        page_iterator = paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=billing_period_prefix, Delimiter='/')

        target_folder_prefix = None

        for page in page_iterator:
            # CommonPrefixes contains the subfolders
            if 'CommonPrefixes' in page:
                for prefix_obj in page['CommonPrefixes']:
                    folder_path = prefix_obj['Prefix']
                    folder_name = folder_path.rstrip('/').split('/')[-1]
                    
                    # Check if this folder starts with  T-3 date
                    if folder_name.startswith(target_date_str):
                        target_folder_prefix = folder_path
                        break # Found it
            if target_folder_prefix:
                break
        
        if not target_folder_prefix:
            msg = f"No folder found for date {target_date_str} in {billing_period_prefix}"
            logger.warning(msg)
            return jsonify({"status": "skipped", "message": msg}), 200

        logger.info(f"Found target alphanumeric folder: {target_folder_prefix}")

        # List Files in the Identified Folder
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix=target_folder_prefix)

        if 'Contents' not in response:
            logger.info(f"No files found inside {target_folder_prefix}")
            return jsonify({"status": "skipped", "message": "Folder exists but is empty"}), 200

        # Filter for Parquet files
        all_objects = response['Contents']
        data_files = [
            obj for obj in all_objects 
            if not obj['Key'].endswith('/') and 'parquet' in obj['Key']
        ]

        if not data_files:
            logger.info(f"No parquet files found in {target_folder_prefix}")
            return jsonify({"status": "skipped", "message": "No parquet files found"}), 200

        # Sort by LastModified to get the latest
        latest_file_obj = sorted(data_files, key=lambda x: x['LastModified'], reverse=True)[0]
        latest_key = latest_file_obj['Key']
        
        # Transfer Logic
        # Extract filename
        original_filename = latest_key.split('/')[-1]
        month_name = month_map[target_month]
        # Business Rule: "MONTH_filename" format
        new_filename = f"{month_name}_{target_date_str}_{original_filename}"
        
        gcs_destination_path = os.path.join(GCS_DESTINATION_FOLDER, new_filename)
        
        logger.info(f"Transferring {latest_key} -> gs://{GCS_BUCKET_NAME}/{gcs_destination_path}")
        
        # Stream upload
        s3_obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=latest_key)
        blob = gcs_bucket.blob(gcs_destination_path)
        blob.upload_from_file(s3_obj['Body'])
        
        found_files.append(gcs_destination_path)
        
        logger.info("Transfer completed successfully.")

        return jsonify({
            "status": "success",
            "objects_transferred": 1,
            "transferred_file": gcs_destination_path
        })

    except (ClientError, GoogleAPICallError, Exception) as e:
        logger.critical(f"A critical error occurred: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500    
    except Exception as e:
        logger.critical(f"Critical Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500