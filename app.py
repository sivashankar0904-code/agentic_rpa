"""
Fetch captcha images from the MinIO "rpa-captchas" bucket, clean and split
them into characters, and write one stitched image per captcha to a local
folder.

Each output is the six characters normalised to a uniform size and laid out
with gaps between them, so no character is larger than its neighbours and
touching glyphs end up visibly separated. See
docs/captcha_cleaning_strategy.md.

Usage:
    python app.py                       # default limit
    python app.py --all                 # every object in the bucket
    python app.py --limit 50            # first 50
    python app.py --out some/folder     # write somewhere else
"""

import argparse
import os

import cv2
import numpy as np

from config import MINIO_URL  # noqa: F401  (re-exported context for readers)
from read_minio import get_minio_client
from preprocess import clean_grayscale, remove_border, sauvola
from segment import split_grayscale_with_masks, stitch

BUCKET_NAME = "rpa-captchas"
OUTPUT_DIR = "stitched"
DEFAULT_LIMIT = 10


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


def save_image(image: np.ndarray, key: str, output_dir: str) -> str:
    """Write an image to the output folder, named after its object key."""
    filename = os.path.basename(key)
    output_path = os.path.join(output_dir, filename)
    cv2.imwrite(output_path, image)
    return output_path


def stitch_captcha(image: np.ndarray) -> np.ndarray:
    """Raw captcha -> cleaned, split, and re-stitched with even spacing."""
    gray = clean_grayscale(image)
    binary = remove_border(sauvola(gray), thickness=3)
    return stitch(split_grayscale_with_masks(gray, binary))


def process_bucket(bucket: str = BUCKET_NAME, output_dir: str = OUTPUT_DIR,
                   limit: int | None = DEFAULT_LIMIT) -> None:
    """Download captchas from the bucket, stitch them, and save them locally."""
    client = get_minio_client()
    ensure_output_dir(output_dir)

    keys = list_captcha_keys(client, bucket)
    print(f"Found {len(keys)} object(s) in bucket '{bucket}'")

    if limit is not None:
        keys = keys[:limit]
        print(f"Processing {len(keys)} of them (limit: {limit})")
    else:
        print(f"Processing all {len(keys)}")

    succeeded = 0
    failed = 0
    for key in keys:
        try:
            image = download_image(client, bucket, key)
            save_image(stitch_captcha(image), key, output_dir)
            succeeded += 1
        except Exception as exc:
            failed += 1
            print(f"Failed to process {key}: {exc}")

    print(f"Wrote {succeeded} image(s) to '{output_dir}/'" +
          (f", {failed} failed" if failed else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=OUTPUT_DIR, help="output folder")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help="how many objects to process")
    parser.add_argument("--all", action="store_true",
                        help="process every object in the bucket")
    args = parser.parse_args()

    process_bucket(output_dir=args.out, limit=None if args.all else args.limit)


if __name__ == "__main__":
    main()
