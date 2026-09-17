"""
Project configuration constants.

MinIO settings are read from environment variables (same key names as used
elsewhere: MINIO_URL, MINIO_USERNAME, MINIO_PASSWORD).
"""

import os

from dotenv import load_dotenv

load_dotenv()

# MinIO (S3-compatible object storage)
MINIO_URL = os.environ["MINIO_URL"]
MINIO_USERNAME = os.environ["MINIO_USERNAME"]
MINIO_PASSWORD = os.environ["MINIO_PASSWORD"]
