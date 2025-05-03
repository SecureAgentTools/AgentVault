import logging
import json
import io
from typing import Dict, Any, Optional, Union

import boto3
from botocore.exceptions import ClientError

# Import settings to get S3 configuration
from .config import settings

logger = logging.getLogger(__name__)

# --- S3 Client Initialization ---
# Determine if using MinIO based on endpoint URL presence
if settings.MINIO_ENDPOINT_URL:
    logger.info(f"Using MinIO endpoint for S3: {settings.MINIO_ENDPOINT_URL}")
    s3_client = boto3.client(
        's3',
        endpoint_url=settings.MINIO_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or 'minioadmin', # Default MinIO creds
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or 'minioadmin',
        region_name=settings.AWS_REGION or 'us-east-1' # Region is less critical for MinIO but still needed
    )
else:
    logger.info(f"Using AWS S3 endpoint (Region: {settings.AWS_REGION or 'default'})")
    # Check for necessary AWS credentials
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY or not settings.AWS_REGION:
        logger.warning("AWS S3 credentials (ID, Key, Region) not fully configured in environment. Boto3 will rely on default credential chain (e.g., IAM role, ~/.aws/credentials).")
    s3_client = boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION
        # Boto3 will use default credential chain if keys are None
    )

# --- Helper Functions ---

def _parse_s3_uri(s3_uri: str) -> Optional[Dict[str, str]]:
    """Parses an S3 URI (s3://bucket/key) into bucket and key."""
    if not s3_uri or not s3_uri.startswith("s3://"):
        logger.error(f"Invalid S3 URI format: {s3_uri}")
        return None
    parts = s3_uri[5:].split('/', 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        logger.error(f"Invalid S3 URI format (missing bucket or key): {s3_uri}")
        return None
    return {"bucket": parts[0], "key": parts[1]}

async def upload_to_s3(data: Union[Dict[str, Any], List[Any], str], bucket: str, key: str, is_json: bool = True) -> Optional[str]:
    """
    Uploads Python dictionary/list (as JSON) or string data to S3/MinIO.

    Args:
        data: The dictionary, list, or string to upload.
        bucket: The target S3 bucket name.
        key: The target S3 object key (path within the bucket).
        is_json: If True, serialize dict/list to JSON before uploading. If False, treat data as raw string.

    Returns:
        The S3 URI (s3://bucket/key) if successful, None otherwise.
    """
    if not bucket:
        logger.error("S3 upload failed: Bucket name is not configured.")
        return None
    if not data:
        logger.warning(f"Attempted to upload empty data to s3://{bucket}/{key}. Skipping upload.")
        return None # Or return the URI anyway if an empty object is desired?

    logger.info(f"Uploading data to s3://{bucket}/{key}...")
    try:
        if is_json:
            # Serialize dictionary/list to JSON bytes
            try:
                content_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode('utf-8')
                content_type = 'application/json'
            except TypeError as e:
                logger.error(f"Failed to serialize data to JSON for S3 upload (key={key}): {e}", exc_info=True)
                return None
        else:
            # Assume data is already a string, encode to bytes
            if not isinstance(data, str):
                 logger.error(f"Data must be a string when is_json=False for S3 upload (key={key}). Got {type(data)}.")
                 return None
            content_bytes = data.encode('utf-8')
            content_type = 'text/plain' # Or determine based on key extension?

        # Use a BytesIO buffer to upload
        buffer = io.BytesIO(content_bytes)
        s3_client.upload_fileobj(buffer, bucket, key, ExtraArgs={'ContentType': content_type})

        s3_uri = f"s3://{bucket}/{key}"
        logger.info(f"Successfully uploaded data to {s3_uri}")
        return s3_uri
    except ClientError as e:
        logger.error(f"S3 ClientError uploading to s3://{bucket}/{key}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.exception(f"Unexpected error uploading to s3://{bucket}/{key}: {e}")
        return None

async def download_from_s3(s3_uri: str, is_json: bool = True) -> Optional[Union[Dict[str, Any], List[Any], str]]:
    """
    Downloads data (JSON object/list or raw string) from S3/MinIO.

    Args:
        s3_uri: The S3 URI (s3://bucket/key) to download from.
        is_json: If True, attempt to parse the downloaded content as JSON.
                 If False, return the raw string content.

    Returns:
        The downloaded data (dict, list, or str) or None if download/parsing fails.
    """
    parsed_uri = _parse_s3_uri(s3_uri)
    if not parsed_uri:
        return None

    bucket = parsed_uri["bucket"]
    key = parsed_uri["key"]
    logger.info(f"Downloading data from {s3_uri}...")

    try:
        buffer = io.BytesIO()
        s3_client.download_fileobj(bucket, key, buffer)
        buffer.seek(0) # Rewind buffer to the beginning
        content_bytes = buffer.read()
        logger.info(f"Successfully downloaded {len(content_bytes)} bytes from {s3_uri}")

        # Decode bytes to string
        try:
            content_str = content_bytes.decode('utf-8')
        except UnicodeDecodeError as e:
            logger.error(f"Failed to decode S3 content as UTF-8 from {s3_uri}: {e}. Trying latin-1 fallback.")
            try:
                content_str = content_bytes.decode('latin-1') # Fallback encoding
            except Exception as decode_err:
                 logger.error(f"Failed to decode S3 content with fallback encoding from {s3_uri}: {decode_err}")
                 return None # Cannot decode

        if is_json:
            # Parse string as JSON
            try:
                data = json.loads(content_str)
                logger.debug(f"Successfully parsed JSON data from {s3_uri}")
                return data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse downloaded content as JSON from {s3_uri}: {e}", exc_info=True)
                logger.debug(f"Content snippet: {content_str[:200]}...")
                return None
        else:
            # Return raw string
            return content_str

    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            logger.error(f"S3 object not found at {s3_uri}")
        elif e.response['Error']['Code'] == 'NoSuchBucket':
             logger.error(f"S3 bucket '{bucket}' not found.")
        else:
            logger.error(f"S3 ClientError downloading from {s3_uri}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.exception(f"Unexpected error downloading from {s3_uri}: {e}")
        return None

logger.info("S3 Utilities initialized.")
