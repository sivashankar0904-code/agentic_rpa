"""
Fetch captcha images from the MinIO "rpa-captchas" bucket, run them through
the preprocessing pipeline, and write the results to a local "preprocessed"
folder.

Usage:
    python app.py
"""

import os

import cv2
import numpy as np

from config import MINIO_URL  # noqa: F401  (re-exported context for readers)
from read_minio import get_minio_client
from preprocess import preprocess_captcha

BUCKET_NAME = "rpa-captchas"
OUTPUT_DIR = "preprocessed"


def list_captcha_keys(client, bucket: str) -> list[str]:
    """List every object key in the bucket, handling pagination."""
    keys = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def download_image(client, bucket: str, key: str) -> np.ndarray:
    """Fetch one object from MinIO and decode it as an OpenCV image."""
    response = client.get_object(Bucket=bucket, Key=key)
    data = response["Body"].read()
    image_array = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not decode image for key: {key}")
    return image


def ensure_output_dir(path: str) -> None:
    """Create the local output folder if it doesn't already exist."""
    os.makedirs(path, exist_ok=True)


def save_preprocessed_image(image: np.ndarray, key: str, output_dir: str) -> str:
    """Write a preprocessed image to the output folder, named after its key."""
    filename = os.path.basename(key)
    output_path = os.path.join(output_dir, filename)
    cv2.imwrite(output_path, image)
    return output_path


def process_bucket(bucket: str = BUCKET_NAME, output_dir: str = OUTPUT_DIR) -> None:
    """Download every captcha in the bucket, preprocess it, and save it locally."""
    client = get_minio_client()
    ensure_output_dir(output_dir)

    keys = list_captcha_keys(client, bucket)
    print(f"Found {len(keys)} object(s) in bucket '{bucket}'")

    for key in keys:
        try:
            image = download_image(client, bucket, key)
            processed = preprocess_captcha(image)
            output_path = save_preprocessed_image(processed, key, output_dir)
            print(f"Processed {key} -> {output_path}")
        except Exception as exc:
            print(f"Failed to process {key}: {exc}")


def main() -> None:
    process_bucket()


if __name__ == "__main__":
    main()
