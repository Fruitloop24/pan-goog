import logging
import azure.functions as func
import json
from datetime import datetime
from typing import Optional

app = func.FunctionApp()

def validate_blob_content(content: bytes) -> tuple[bool, Optional[str]]:
    """
    Validates the blob content
    Returns: (is_valid, error_message)
    """
    try:
        if len(content) == 0:
            return False, "Blob content is empty"
        
        # Try to decode and parse as JSON to validate format
        json.loads(content.decode('utf-8'))
        return True, None
    except UnicodeDecodeError:
        return False, "Content is not valid UTF-8"
    except json.JSONDecodeError:
        return False, "Content is not valid JSON"
    except Exception as e:
        return False, f"Validation error: {str(e)}"

@app.function_name(name="BlobTrigger1")
@app.blob_trigger(arg_name="myblob", 
                 path="samples-workitems/{name}",
                 connection="AzureWebJobsStorage")
def blob_trigger_function(myblob: func.InputStream):
    """
    Azure Function triggered by blob storage uploads.
    Processes JSON content and performs validation.
    """
    function_start_time = datetime.utcnow()
    
    try:
        logging.info(f"Python blob trigger function processing blob:\n"
                    f"Name: {myblob.name}\n"
                    f"Size: {myblob.length} bytes\n"
                    f"URI: {myblob.uri}")

        # Read blob content
        blob_content = myblob.read()
        
        # Validate content
        is_valid, error_message = validate_blob_content(blob_content)
        if not is_valid:
            raise ValueError(f"Invalid blob content: {error_message}")

        # Process the content (assuming JSON)
        content_json = json.loads(blob_content.decode('utf-8'))
        
        # Log processing details
        logging.info(f"Successfully processed blob {myblob.name}")
        logging.debug(f"Content keys: {list(content_json.keys())}")
        
        processing_time = (datetime.utcnow() - function_start_time).total_seconds()
        
        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "processed": True,
                "blob_name": myblob.name,
                "size": myblob.length,
                "processing_time_seconds": processing_time,
                "processed_at": datetime.utcnow().isoformat()
            }),
            mimetype="application/json",
            status_code=200
        )
        
    except ValueError as ve:
        logging.error(f"Validation error processing blob {myblob.name}: {str(ve)}")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "error": str(ve),
                "blob_name": myblob.name
            }),
            mimetype="application/json",
            status_code=400
        )
    except Exception as e:
        logging.error(f"Error processing blob {myblob.name}: {str(e)}", exc_info=True)
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "error": "Internal server error",
                "blob_name": myblob.name
            }),
            mimetype="application/json",
            status_code=500
        )
