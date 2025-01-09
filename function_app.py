import logging
import azure.functions as func
import json

app = func.FunctionApp()

@app.function_name(name="BlobTrigger1")
@app.blob_trigger(arg_name="myblob", 
                 path="samples-workitems/{name}",
                 connection="AzureWebJobsStorage")
def blob_trigger_function(myblob: func.InputStream):
    """
    Simple blob trigger function for testing deployment
    """
    try:
        logging.info(f"Python blob trigger function processed blob \n"
                    f"Name: {myblob.name}\n"
                    f"Size: {myblob.length} bytes")
        
        # Read blob content
        blob_content = myblob.read()
        
        # Basic processing - just log the first 100 bytes
        logging.info(f"Blob content preview: {blob_content[:100]}")
        
        return json.dumps({
            "processed": True,
            "blob_name": myblob.name,
            "size": myblob.length
        })
        
    except Exception as e:
        logging.error(f"Error processing blob: {str(e)}")
        raise
