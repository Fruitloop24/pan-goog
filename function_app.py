import logging
import base64
from io import BytesIO
from azure.storage.blob import BlobServiceClient
from google.oauth2 import service_account
from googleapiclient.discovery import build
import azure.functions as func
from dotenv import load_dotenv
import os
import json
import requests
from datetime import datetime
from PIL import Image

# Load environment variables
load_dotenv()

app = func.FunctionApp()

@app.function_name(name="ImageProcessingTrigger")
@app.function_name(name="pan-goog")
@app.blob_trigger(arg_name="myblob", 
                 path="image/{name}",
                 connection="AzureWebJobsStorage")
@app.retry(strategy="exponential_backoff", 
          max_retry_count=3, 
          minimum_interval="00:00:10", 
          maximum_interval="00:01:00")
def blob_trigger_function(myblob: func.InputStream):
    """
    Azure Function triggered by blob storage uploads.
    Processes images using Google Vision API and stores results.
    """
    try:
        logging.info("Starting blob trigger function execution...")
        
        # Environment variables
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        google_credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
        google_credentials_b64 = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_B64")
        google_scopes = [os.getenv("GOOGLE_SCOPES")]

        # Log environment variable status
        logging.info(f"Environment variables status:")
        logging.info(f"AZURE_STORAGE_CONNECTION_STRING exists: {bool(connection_string)}")
        logging.info(f"GOOGLE_CREDENTIALS_FILE exists: {bool(google_credentials_file)}")
        logging.info(f"GOOGLE_APPLICATION_CREDENTIALS_B64 exists: {bool(google_credentials_b64)}")
        logging.info(f"GOOGLE_SCOPES exists: {bool(google_scopes[0])}")

        # Validate environment variables
        if not connection_string:
            raise ValueError("Missing AZURE_STORAGE_CONNECTION_STRING")
        if not (google_credentials_file or google_credentials_b64):
            raise ValueError("Missing both GOOGLE_CREDENTIALS_FILE and GOOGLE_APPLICATION_CREDENTIALS_B64")
        if not google_scopes[0]:
            raise ValueError("Missing GOOGLE_SCOPES")

        logging.info(f"Processing blob:\n"
                    f"Name: {myblob.name}\n"
                    f"Size: {myblob.length} bytes\n"
                    f"URI: {myblob.uri}")

        # Validate blob content
        if myblob.length == 0:
            raise ValueError("Empty blob received")

        # Initialize Azure Blob Service Client
        logging.info("Initializing Azure Blob Service Client...")
        try:
            blob_service_client = BlobServiceClient.from_connection_string(connection_string)
            logging.info("Azure Blob Service Client initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize Azure Blob Service Client: {str(e)}")
            raise

        # Initialize Google Vision API
        logging.info("Initializing Google Vision API...")
        try:
            # Try to get credentials from base64 environment variable first
            credentials_b64 = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_B64")
            if credentials_b64:
                # Decode base64 credentials and create service account credentials
                credentials_json = base64.b64decode(credentials_b64).decode('utf-8')
                credentials_info = json.loads(credentials_json)
                credentials = service_account.Credentials.from_service_account_info(
                    credentials_info, scopes=google_scopes
                )
                logging.info("Successfully loaded credentials from base64 environment variable")
            else:
                # Fall back to file-based credentials (for local development)
                credentials = service_account.Credentials.from_service_account_file(
                    google_credentials_file, scopes=google_scopes
                )
                logging.info("Successfully loaded credentials from file")
            
            vision_service = build("vision", "v1", credentials=credentials)
            logging.info("Google Vision API initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize Google Vision API: {str(e)}")
            raise

        # Process the blob content
        logging.info("Reading blob content...")
        image_data = myblob.read()
        
        # Convert image to JPEG format
        logging.info("Opening image with PIL...")
        try:
            image = Image.open(BytesIO(image_data))
        except Exception as e:
            logging.error(f"Failed to open image: {str(e)}")
            raise
        
        # Convert to RGB if needed (in case of RGBA images)
        if image.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background
        
        # Save as JPEG in memory
        buffered = BytesIO()
        image.save(buffered, format="JPEG", quality=95)
        
        # Encode image for Vision API
        encoded_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # Vision API request
        request_body = {
            "requests": [{
                "image": {"content": encoded_image},
                "features": [
                    {"type": "TEXT_DETECTION", "maxResults": 50}, 
                    {"type": "LABEL_DETECTION", "maxResults": 50}
                ],
            }]
        }

        # Call Vision API
        logging.info("Calling Google Vision API...")
        response = vision_service.images().annotate(body=request_body).execute()
        
        if not response.get("responses"):
            logging.error("Empty response from Vision API")
            raise ValueError("No response data from Vision API")

        # Parse response
        logging.info("Parsing Vision API response...")
        api_response = response.get("responses", [{}])[0]
        text_annotations = api_response.get("textAnnotations", [])
        label_annotations = api_response.get("labelAnnotations", [])
        
        logging.info(f"Found {len(text_annotations)} text annotations and {len(label_annotations)} labels")

        parsed_data = {
            "text_annotations": [{"text": t["description"]} for t in text_annotations],
            "label_annotations": [
                {"label": l["description"], "confidence": l["score"]}
                for l in label_annotations
            ],
            "processed_image": myblob.name,
            "processed_at": datetime.utcnow().isoformat()
        }

        # Save latest result to process container
        process_blob_name = "latest_result.json"
        process_blob_client = blob_service_client.get_blob_client(
            container="process", 
            blob=process_blob_name
        )

        # Upload to process container
        logging.info(f"Uploading results to process container: {process_blob_name}")
        process_blob_client.upload_blob(json.dumps(parsed_data, indent=2), overwrite=True)
        logging.info(f"Results saved to process container as '{process_blob_name}'")

        # Create a timestamped copy of the data for archiving
        archive_data = parsed_data.copy()
        archive_data["archived_at"] = datetime.utcnow().isoformat()
        
        # Save single timestamped copy to process-archive container
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        archive_blob_name = f"result_{timestamp}.json"
        archive_blob_client = blob_service_client.get_blob_client(
            container="process-archive", 
            blob=archive_blob_name
        )

        # Upload single copy to process-archive container
        logging.info(f"Archiving results to process-archive container: {archive_blob_name}")
        archive_blob_client.upload_blob(json.dumps(archive_data, indent=2))
        logging.info(f"Results archived to process-archive container as '{archive_blob_name}'")

    except ValueError as ve:
        logging.error(f"Validation error: {str(ve)}", exc_info=True)
        raise
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}", exc_info=True)
        # Log the full error details
        import traceback
        logging.error(f"Full traceback:\n{traceback.format_exc()}")
        raise
