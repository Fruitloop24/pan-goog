import logging
import base64
from azure.storage.blob import BlobServiceClient
from google.oauth2 import service_account
from googleapiclient.discovery import build
import azure.functions as func
from dotenv import load_dotenv
import os
import json
from datetime import datetime

# Load environment variables
load_dotenv()

# Initialize Blob Service Client
connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
if not connection_string:
    raise ValueError("Missing AZURE_STORAGE_CONNECTION_STRING in environment variables.")
blob_service_client = BlobServiceClient.from_connection_string(connection_string)

# Initialize Google Service Account credentials
google_credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
google_scopes = [os.getenv("GOOGLE_SCOPES")]
if not google_credentials_file or not google_scopes:
    raise ValueError("Missing Google credentials configuration in environment variables.")
credentials = service_account.Credentials.from_service_account_file(
    google_credentials_file, scopes=google_scopes
)

# Initialize the Google Vision API client
vision_service = build("vision", "v1", credentials=credentials)

# Function App Definition
app = func.FunctionApp()

@app.function_name(name="goog")
@app.blob_trigger(arg_name="blob", 
                 path="vision/data/{name}",
                 connection="AzureWebJobsStorage") 
@app.route(route="goog")  # Adding explicit route
def goog_function(blob: func.InputStream) -> None:
    logging.info('Python blob trigger function started')
    """
    Triggered when a blob is created or updated in the vision/data path.
    Downloads the blob content, processes it with Google Vision API, 
    and saves the result to cat/categories while archiving old versions.
    """
    try:
        logging.info(f"Blob Triggered: {blob.name}")
        logging.info(f"Blob Size: {blob.length} bytes")

        # Read the blob content
        blob_content = blob.read()

        # Encode the blob content in base64 for the Vision API
        blob_base64 = base64.b64encode(blob_content).decode('utf-8')

        # Vision API request body
        logging.info("Preparing request to Google Vision API...")
        request_body = {
            "requests": [
                {
                    "image": {"content": blob_base64},
                    "features": [{"type": "TEXT_DETECTION"}, {"type": "LABEL_DETECTION"}],
                }
            ]
        }

        # Call the Vision API
        logging.info("Calling Google Vision API...")
        response = vision_service.images().annotate(body=request_body).execute()

        # Parse the response
        text_annotations = response.get("responses", [{}])[0].get("textAnnotations", [])
        label_annotations = response.get("responses", [{}])[0].get("labelAnnotations", [])

        parsed_data = {
            "text_annotations": [{"text": t["description"]} for t in text_annotations],
            "label_annotations": [
                {"label": l["description"], "confidence": l["score"]}
                for l in label_annotations
            ],
        }

        # Save parsed data to Azure Blob as cat/categories
        output_blob_client = blob_service_client.get_blob_client(
            container="cat", blob="categories"
        )

        # Archive existing data blob if it exists
        if output_blob_client.exists():
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            archive_blob_client = blob_service_client.get_blob_client(
                container="cat", blob=f"archive/categories_{timestamp}.json"
            )
            archive_blob_client.start_copy_from_url(output_blob_client.url)
            output_blob_client.delete_blob()
            logging.info(f"Existing data blob archived as 'archive/categories_{timestamp}.json'.")

        # Upload the new data to cat/categories
        output_blob_client.upload_blob(json.dumps(parsed_data, indent=2), overwrite=True)
        logging.info("Parsed data saved to Azure Blob successfully.")
        logging.info("Image processed successfully")
        return

    except Exception as e:
        logging.error(f"Error processing image with Google Vision: {e}")
        logging.error(f"Error processing image with Google Vision: {e}")
        raise
