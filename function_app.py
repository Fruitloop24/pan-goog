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
@app.blob_trigger(arg_name="myblob", 
                 path="image/data",
                 connection="AzureWebJobsStorage")
def blob_trigger_function(myblob: func.InputStream):
    """
    Azure Function triggered by blob storage uploads.
    Processes images using Google Vision API and stores results.
    """
    try:
        # Environment variables
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        google_credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
        google_scopes = [os.getenv("GOOGLE_SCOPES")]

        logging.info(f"Processing blob:\n"
                    f"Name: {myblob.name}\n"
                    f"Size: {myblob.length} bytes\n"
                    f"URI: {myblob.uri}")

        # Initialize Azure Blob Service Client
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)

        # Initialize Google Vision API
        credentials = service_account.Credentials.from_service_account_file(
            google_credentials_file, scopes=google_scopes
        )
        vision_service = build("vision", "v1", credentials=credentials)

        # Process the blob content
        image_data = myblob.read()
        
        # Convert image to JPEG format
        image = Image.open(BytesIO(image_data))
        
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

        # Parse response
        text_annotations = response.get("responses", [{}])[0].get("textAnnotations", [])
        label_annotations = response.get("responses", [{}])[0].get("labelAnnotations", [])

        parsed_data = {
            "text_annotations": [{"text": t["description"]} for t in text_annotations],
            "label_annotations": [
                {"label": l["description"], "confidence": l["score"]}
                for l in label_annotations
            ],
            "processed_image": myblob.name,
            "processed_at": datetime.utcnow().isoformat()
        }

        # Save results to vision/data
        output_blob_client = blob_service_client.get_blob_client(
            container="goog", 
            blob="data"
        )

        # Archive existing data if present
        if output_blob_client.exists():
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            archive_blob_client = blob_service_client.get_blob_client(
                container="vision",
                blob=f"archive/data_{timestamp}.json"
            )
            archive_blob_client.start_copy_from_url(output_blob_client.url)
            output_blob_client.delete_blob()
            logging.info(f"Existing data archived as 'archive/data_{timestamp}.json'")

        # Upload new results
        output_blob_client.upload_blob(json.dumps(parsed_data, indent=2), overwrite=True)
        logging.info("Vision API results saved successfully")


    except Exception as e:
        logging.error(f"Error processing image: {str(e)}", exc_info=True)
        raise
