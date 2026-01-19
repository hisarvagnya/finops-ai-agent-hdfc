import os
import logging
import datetime 
import secret_manager_utils as secret_manager_client
from flask import jsonify, Request
from google.cloud import storage
from google.cloud import logging as cloud_logging
from azure.identity import ClientSecretCredential
from azure.storage.blob import BlobServiceClient
from google.api_core.exceptions import GoogleAPICallError

# --- Cloud Logging Setup ---
# Initialize the Cloud Logging client
logging_client = cloud_logging.Client()
logging_client.setup_logging()

# Create a custom logger
logger = logging.getLogger("azure-gcs-transfer")
logger.setLevel(logging.INFO)

for lib in ["azure.core", "azure.identity", "azure.storage.blob", "urllib3"]:
    logging.getLogger(lib).setLevel(logging.ERROR)


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

class Config:
    """Loads configuration from environment variables."""

    def __init__(self):
        # Azure SPN Credentials
        self.tenant_id = "827fd022-05a6-4e57-be9c-cc069b6ae62d"
        self.client_id = "b16521f7-1e2b-4fa4-8311-408363d1c25e"

        try:
            self.client_secret = secret_manager_client.access_secrets()
        except Exception as e:
            logger.error(f"Failed to initialize client secret: {e}")
        # self.client_secret= "c6M8Q~mKy-zGZCVZ~DLu9dZoAn_1kwp0egUSMa-C"  # secret *value*
             
        # Azure Blob Storage Details
        self.storage_account_name = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "finopsapptioexportprod")
        self.container_name = os.environ.get("AZURE_CONTAINER_NAME", "azurecostdailyexportsforchatbot")

        # Google Cloud Storage Details
        self.gcs_bucket_name = os.environ.get("GCS_BUCKET_NAME", "finops-agent-azure-billing-files")
        self.gcs_destination_folder = "daily_azure_billing_files"
 
        self._validate()

    def _validate(self):
        required = {
            "AZURE_TENANT_ID": self.tenant_id,
            "AZURE_CLIENT_ID": self.client_id,
            "AZURE_CLIENT_SECRET": self.client_secret,
            "AZURE_STORAGE_ACCOUNT_NAME": self.storage_account_name,
            "AZURE_CONTAINER_NAME": self.container_name,
            "GCS_BUCKET_NAME": self.gcs_bucket_name,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

class DataTransferService:
    def __init__(self, config: Config):
        self.config = config
        self.gcs_bucket = None
        self.azure_container_client = None

    def _get_gcs_bucket(self):
        """Connects to the GCS bucket."""
        try:
            client = storage.Client()
            bucket = client.bucket(self.config.gcs_bucket_name)
            if not bucket.exists():
                logger.warning("GCS bucket '%s' not found or inaccessible.", self.config.gcs_bucket_name)
            else:
                logger.info("Connected to GCS bucket: %s", self.config.gcs_bucket_name)
            return bucket
        except GoogleAPICallError as e:
            logger.exception("Failed to connect to GCS: %s", e)
            raise

    def _get_azure_container_client(self):
        """Connects to Azure Blob Storage container."""
        try:
            storage_account_url = f"https://{self.config.storage_account_name}.blob.core.windows.net"
            credential = ClientSecretCredential(
                tenant_id=self.config.tenant_id,
                client_id=self.config.client_id,
                client_secret=self.config.client_secret,
            )

            blob_service_client = BlobServiceClient(
                account_url=storage_account_url,
                credential=credential,
                connection_timeout=60,
            )
            container_client = blob_service_client.get_container_client(self.config.container_name)
            logger.info("Connected to Azure container: %s", self.config.container_name)
            return container_client
        except Exception as e:
            logger.exception("Failed to connect to Azure Blob Storage: %s", e)
            raise

    def _get_previous_date_with_offset(self):
        """
        Calculates the target date folder to get the data from Azure S3 blob storage
        """

        today = datetime.date.today()
        current_day = today.day
        current_month = today.month
        current_year = today.year

        def is_leap_year(year):
            return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

        days_dict["2"] = 29 if is_leap_year(current_year) else 28

        try:
            target_date = today.replace(day=current_day - 1)
            target_year = target_date.year
            target_month = target_date.month

        except ValueError:
            previous_month = current_month - 1
            previous_year = current_year

            if previous_month == 0:
                previous_month = 12
                previous_year -= 1

            days_in_previous_month = days_dict[str(previous_month)]

            adjusted_day = current_day - 1 + days_in_previous_month

            target_date = datetime.date(previous_year, previous_month, adjusted_day)
            target_year = target_date.year
            target_month = target_date.month
        
        month_folder_prefix = datetime.date(target_year, target_month, 1)
        month_folder_prefix= month_folder_prefix.strftime("%Y-%m")

        target_date_str = target_date.strftime("%d-%m-%Y") 
        date_folder = f"ABSDailyFileforChatBot_{target_date_str}"

        full_prefix = f"{month_folder_prefix}/{date_folder}"
        logger.info(f"Targeting Azure Prefix (Yesterday): {full_prefix}")
        return full_prefix


    # @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _transfer_single_blob(self, blob):
        """Streams a single Azure blob into GCS."""
        try:
            if not os.path.basename(blob.name):
                logger.debug("Skipping directory blob: %s", blob.name)
                return
            
            filename = os.path.basename(blob.name)
            dest_path = f"{self.config.gcs_destination_folder}/{filename}".lstrip("/")
            logger.info(f"Streaming Azure blob: '{blob.name}' -> GCS '{dest_path}'")

            

            azure_blob_client = self.azure_container_client.get_blob_client(blob.name)
            gcs_blob = self.gcs_bucket.blob(dest_path)

            downloader = azure_blob_client.download_blob()
            with gcs_blob.open("wb", timeout=450) as gcs_file:
                for chunk in downloader.chunks():
                    gcs_file.write(chunk)

            logger.info("Successfully streamed '%s' to GCS.", blob.name)

        except Exception as e:
            logger.exception("Error transferring blob '%s': %s", blob.name, e)
            raise

    def transfer_all_blobs(self, target_prefix: str):
        """Lists and transfers all blobs for a given prefix."""
        files_transferred = 0
        files_failed = 0
       
        try:
            logger.info("Starting blob transfer loop for prefix: %s", target_prefix)
            blob_list = self.azure_container_client.list_blobs(name_starts_with=target_prefix)
           
            for blob in blob_list:
                try:
                    self._transfer_single_blob(blob)
                    files_transferred += 1
                except Exception as e:
                    # Log and continue if one file fails
                    logger.exception("Failed to transfer blob '%s': %s", blob.name, e)
                    files_failed += 1
               
            logger.info(
                "Transfer complete for prefix %s. Files transferred: %d, Files failed: %d",
                target_prefix,
                files_transferred,
                files_failed
            )
           
        except Exception as e:
            logger.exception("Critical error during blob listing for prefix %s: %s", target_prefix, e)
            raise

    def run(self) -> dict:
        """Performs connectivity check and runs the one-time backfill."""
        logger.info("Starting connectivity check...")

        gcs_connected = False
        azure_connected = False
       
        logger.info(f"All files will be placed in GCS folder: {self.config.gcs_destination_folder}")

        try:
            self.gcs_bucket = self._get_gcs_bucket()
            gcs_connected = True
        except Exception:
            pass

        try:
            self.azure_container_client = self._get_azure_container_client()
            azure_connected = True
        except Exception:
            pass

        if gcs_connected and azure_connected:
            logger.info("Connectivity check passed. Starting transfer of CSV file from Azure Blob Storage to GCS Bucket.")

            try:
            
                target_prefix = self._get_previous_date_with_offset()
                        
                self.transfer_all_blobs(target_prefix)
                    
            except Exception as e:
                    logger.exception(f"--- Failed to process file {target_prefix}: {e} ---")
            
            logger.info("--- TRANSFER FOR THE DAY COMPLETE. ---")
           
        else:
            logger.error(
                "Connectivity check failed. Azure: %s, GCS: %s",
                azure_connected,
                gcs_connected
            )

        return {"gcs_connected": gcs_connected, "azure_connected": azure_connected}


def entry_point(request: Request):
    """HTTP entry point for Cloud Run."""
    try:
        config = Config()
        service = DataTransferService(config)
        result = service.run()
        status_code = 200 if (result["gcs_connected"] and result["azure_connected"]) else 503
        return jsonify({"status": "check_complete", "connectivity": result}), status_code
    except ValueError as ve:
        logger.error("Configuration error: %s", ve)
        return jsonify({"status": "error", "message": str(ve)}), 400
    except Exception as e:
        logger.critical("Unhandled error: %s", e, exc_info=True)
        return jsonify({"status": "error", "message": "Internal server error"}), 500
        
#--------------------------------------------------------------------

# import os
# import logging
# import datetime
# import time
# from flask import jsonify, Request
# from google.cloud import storage
# from google.cloud import logging as cloud_logging
# from azure.identity import ClientSecretCredential
# from azure.storage.blob import BlobServiceClient
# from google.api_core.exceptions import GoogleAPICallError

# # --- Cloud Logging Setup ---
# # Initialize the Cloud Logging client
# logging_client = cloud_logging.Client()
# logging_client.setup_logging()

# # Create a custom logger
# logger = logging.getLogger("azure-gcs-transfer")
# logger.setLevel(logging.INFO)

# for lib in ["azure.core", "azure.identity", "azure.storage.blob", "urllib3"]:
#     logging.getLogger(lib).setLevel(logging.ERROR)


# month_map = {
#     1: 'January', 2: 'February', 3: 'March', 4: 'April',
#     5: 'May', 6: 'June', 7: 'July', 8: 'August',
#     9: 'September', 10: 'October', 11: 'November', 12: 'December'
# }
# days_dict = {
#     '1': 31,
#     '2': 28,
#     '3': 31,
#     '4': 30,
#     '5': 31,
#     '6': 30,
#     '7': 31,
#     '8': 31,
#     '9': 30,
#     '10': 31,
#     '11': 30,
#     '12': 31
# }

# class Config:
#     """Loads configuration from environment variables."""

#     def __init__(self):
#         # Azure SPN Credentials
#         self.tenant_id = "827fd022-05a6-4e57-be9c-cc069b6ae62d"
#         self.client_id = "b16521f7-1e2b-4fa4-8311-408363d1c25e"
#         self.client_secret = "c6M8Q~mKy-zGZCVZ~DLu9dZoAn_1kwp0egUSMa-C"  # secret *value*
 
#         # Azure Blob Storage Details
#         self.storage_account_name = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "finopsapptioexportprod")
#         self.container_name = os.environ.get("AZURE_CONTAINER_NAME", "azurecostdailyexportsforchatbot")

#         # Google Cloud Storage Details
#         self.gcs_bucket_name = os.environ.get("GCS_BUCKET_NAME", "finops-agent-azure-billing-files")
#         self.gcs_destination_folder = "daily_azure_billing_files"
 
#         self._validate()

#     def _validate(self):
#         required = {
#             "AZURE_TENANT_ID": self.tenant_id,
#             "AZURE_CLIENT_ID": self.client_id,
#             "AZURE_CLIENT_SECRET": self.client_secret,
#             "AZURE_STORAGE_ACCOUNT_NAME": self.storage_account_name,
#             "AZURE_CONTAINER_NAME": self.container_name,
#             "GCS_BUCKET_NAME": self.gcs_bucket_name,
#         }
#         missing = [k for k, v in required.items() if not v]
#         if missing:
#             raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

# class DataTransferService:
#     def __init__(self, config: Config):
#         self.config = config
#         self.gcs_bucket = None
#         self.azure_container_client = None

#     def _get_gcs_bucket(self):
#         """Connects to the GCS bucket."""
#         try:
#             client = storage.Client()
#             bucket = client.bucket(self.config.gcs_bucket_name)
#             if not bucket.exists():
#                 logger.warning("GCS bucket '%s' not found or inaccessible.", self.config.gcs_bucket_name)
#             else:
#                 logger.info("Connected to GCS bucket: %s", self.config.gcs_bucket_name)
#             return bucket
#         except GoogleAPICallError as e:
#             logger.exception("Failed to connect to GCS: %s", e)
#             raise

#     def _get_azure_container_client(self):
#         """Connects to Azure Blob Storage container."""
#         try:
#             storage_account_url = f"https://{self.config.storage_account_name}.blob.core.windows.net"
#             credential = ClientSecretCredential(
#                 tenant_id=self.config.tenant_id,
#                 client_id=self.config.client_id,
#                 client_secret=self.config.client_secret,
#             )

#             blob_service_client = BlobServiceClient(
#                 account_url=storage_account_url,
#                 credential=credential,
#                 connection_timeout=60,
#             )
#             container_client = blob_service_client.get_container_client(self.config.container_name)
#             logger.info("Connected to Azure container: %s", self.config.container_name)
#             return container_client
#         except Exception as e:
#             logger.exception("Failed to connect to Azure Blob Storage: %s", e)
#             raise

#     def _get_previous_date_with_offset(self):
#         """
#         Calculates the target date by manually subtracting 3 days.
#         Handles month boundaries using a days-per-month dictionary.
#         """

#         today = datetime.date.today()
#         current_day = today.day
#         current_month = today.month
#         current_year = today.year

#         def is_leap_year(year):
#             return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

#         days_dict["2"] = 29 if is_leap_year(current_year) else 28

#         try:
#             target_date = today.replace(day=current_day - 2)
#             target_year = target_date.year
#             target_month = target_date.month

#         except ValueError:
#             previous_month = current_month - 1
#             previous_year = current_year

#             if previous_month == 0:
#                 previous_month = 12
#                 previous_year -= 1

#             days_in_previous_month = days_dict[str(previous_month)]

#             adjusted_day = current_day - 2 + days_in_previous_month

#             target_date = datetime.date(previous_year, previous_month, adjusted_day)
#             target_year = target_date.year
#             target_month = target_date.month
        
#         month_folder_prefix = datetime.date(target_year, target_month, 1)
#         month_folder_prefix= month_folder_prefix.strftime("%YYYY-%mm")

#         target_date_str = target_date.strftime("%d-%m-%Y") 
#         date_folder = f"ABSDailyFileforChatBot_{target_date_str}"

#         return month_folder_prefix, date_folder


#     # @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
#     def _transfer_single_blob(self, blob):
#         """Streams a single Azure blob into GCS."""
#         try:
#             if not os.path.basename(blob.name):
#                 logger.debug("Skipping directory blob: %s", blob.name)
#                 return
            
#             filename = os.path.basename(blob.name)
#             dest_path = f"{self.config.gcs_destination_folder}/{filename}".lstrip("/")
#             # size_mb = blob.size / (1024 * 1024) if blob.size else 0
#             logger.info(f"Streaming Azure blob: '{blob.name}' -> GCS '{dest_path}'")

#             azure_blob_client = self.azure_container_client.get_blob_client(blob.name)
#             gcs_blob = self.gcs_bucket.blob(dest_path)

#             downloader = azure_blob_client.download_blob()
#             with gcs_blob.open("wb", timeout=450) as gcs_file:
#                 for chunk in downloader.chunks():
#                     gcs_file.write(chunk)

#             logger.info("Successfully streamed '%s' to GCS.", blob.name)

#         except Exception as e:
#             logger.exception("Error transferring blob '%s': %s", blob.name, e)
#             raise

#     def transfer_all_blobs(self, target_prefix: str):
#         """Lists and transfers all blobs for a given prefix."""
#         files_transferred = 0
#         files_failed = 0
       
#         try:
#             logger.info("Starting blob transfer loop for prefix: %s", target_prefix)
#             blob_list = self.azure_container_client.list_blobs(name_starts_with=target_prefix)
           
#             for blob in blob_list:
#                 try:
#                     self._transfer_single_blob(blob)
#                     files_transferred += 1
#                 except Exception as e:
#                     # Log and continue if one file fails
#                     logger.exception("Failed to transfer blob '%s': %s", blob.name, e)
#                     files_failed += 1
               
#             logger.info(
#                 "Transfer complete for prefix %s. Files transferred: %d, Files failed: %d",
#                 target_prefix,
#                 files_transferred,
#                 files_failed
#             )
           
#         except Exception as e:
#             logger.exception("Critical error during blob listing for prefix %s: %s", target_prefix, e)
#             raise

#     def run(self) -> dict:
#         """Performs connectivity check and runs the one-time backfill."""
#         logger.info("Starting connectivity check...")

#         gcs_connected = False
#         azure_connected = False
       
#         logger.info(f"All files will be placed in GCS folder: {self.config.gcs_destination_folder}")

#         try:
#             self.gcs_bucket = self._get_gcs_bucket()
#             gcs_connected = True
#         except Exception:
#             pass

#         try:
#             self.azure_container_client = self._get_azure_container_client()
#             azure_connected = True
#         except Exception:
#             pass

#         if gcs_connected and azure_connected:
#             logger.info("Connectivity check passed. Starting transfer of CSV file from Azure Blob Storage.")

#             for i in range(16, 18):

#                 try:
            
#                     # month_folder, date_folder = self._get_previous_date_with_offset()

#                     # target_prefix = f"{month_folder}/{date_folder}"
#                     month_folder = "2025-12"
#                     target_date = datetime.date(2025, 12, i)
#                     target_date_str = target_date.strftime("%d-%m-%Y")

#                     date_folder = f"ABSDailyFileforChatBot_{target_date_str}"

#                     target_prefix = f"{month_folder}/{date_folder}"
                        
#                     self.transfer_all_blobs(target_prefix)
                    
#                 except Exception as e:
#                         logger.exception(f"--- Failed to process month {target_prefix}: {e} ---")
#                         # Continue to the next month
            
#                 logger.info("--- TRANSFER FOR THE DAY COMPLETE. ---")
           
#         else:
#             logger.error(
#                 "Connectivity check failed. Azure: %s, GCS: %s",
#                 azure_connected,
#                 gcs_connected
#             )

#         return {"gcs_connected": gcs_connected, "azure_connected": azure_connected}


# def entry_point(request: Request):
#     """HTTP entry point for Cloud Run."""
#     try:
#         config = Config()
#         service = DataTransferService(config)
#         result = service.run()
#         status_code = 200 if (result["gcs_connected"] and result["azure_connected"]) else 503
#         return jsonify({"status": "check_complete", "connectivity": result}), status_code
#     except ValueError as ve:
#         logger.error("Configuration error: %s", ve)
#         return jsonify({"status": "error", "message": str(ve)}), 400
#     except Exception as e:
#         logger.critical("Unhandled error: %s", e, exc_info=True)
#         return jsonify({"status": "error", "message": "Internal server error"}), 500