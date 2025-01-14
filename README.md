# Pan Google Vision Function

## Overview
This Azure Function serves as the AI vision processing stage in our serverless pipeline. Triggered by blob storage events, it processes images using Google Cloud Vision API, extracting text and labels while maintaining both active and archived results.

## Key Features
- Blob-triggered execution
- Google Vision AI integration
- Text and label detection
- Image format optimization
- Dual storage strategy (active/archive)
- Exponential backoff retry mechanism
- Comprehensive error handling and logging
- Automatic AI processing trigger

## Technical Details

### Environment Variables
```
AZURE_STORAGE_CONNECTION_STRING=your_storage_connection
GOOGLE_APPLICATION_CREDENTIALS_B64=base64_encoded_credentials
GOOGLE_CREDENTIALS_FILE=path_to_credentials (local development)
GOOGLE_SCOPES=vision_api_scope
AIOPEN_PROCESS_URL=next_function_url (optional)
```

### Blob Storage Structure
- Trigger Container: `image`
  - Monitors for new uploads
- Process Container: 
  - `latest_result.json`: Current processing results
- Process-Archive Container:
  - `result_[timestamp].json`: Timestamped result archives

### Function Configuration
- Trigger: Blob Storage
- Path: `image/{name}`
- Retry Strategy: 
  - Type: Exponential backoff
  - Max Retries: 3
  - Minimum Interval: 10 seconds
  - Maximum Interval: 60 seconds

### Processing Steps
1. Validates environment and blob content
2. Initializes Azure and Google Vision clients
3. Optimizes image format (converts to JPEG if needed)
4. Performs Vision API analysis:
   - Text detection
   - Label detection
5. Stores results in both active and archive containers
6. Optionally triggers next pipeline stage

### Vision AI Features
- Text Detection:
  - Extracts all text content from images
  - Maintains original text structure
- Label Detection:
  - Identifies objects and scenes
  - Includes confidence scores
  - Up to 50 labels per image

## Pipeline Integration

### Previous Stage
Receives images from the upload function:
[pan-format-upload Repository](https://github.com/Fruitloop24/pan-format-upload)

### Next Stage
Triggers AI analysis function for context-aware processing:
[pan-ai Repository](https://github.com/Fruitloop24/pan-ai)

### Data Flow
1. Monitors `image` container for new uploads
2. Processes images through Google Vision
3. Stores structured results in `process` container
4. Archives results with timestamps
5. Triggers next pipeline stage if configured

## Deployment Requirements
- Azure Functions Core Tools
- Python 3.9+
- Azure Storage Account
- Google Cloud Project with Vision API enabled
- Google Service Account credentials

## Local Development
1. Clone the repository
2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```
3. Install dependencies:
```bash
pip install -r requirements.txt
```
4. Set up local.settings.json with required environment variables
5. Start the function:
```bash
func start
```

## Security Notes
- Supports both file-based and base64-encoded Google credentials
- Credentials should never be committed to the repository
- Use secure environment variables in production
- Implement proper RBAC in production environments

## Error Handling
- Environment validation
- Blob content validation
- Client initialization errors
- Image processing errors
- API response validation
- Storage operation errors
- Full error logging with tracebacks

## Contributing
Contributions welcome! Please read the contributing guidelines and submit pull requests for any improvements.

## License
MIT License - see LICENSE file for details