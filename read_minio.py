"""
Read an object from MinIO.

Connection settings come from config.py (MINIO_URL, MINIO_USERNAME,
MINIO_PASSWORD) -- never from environment variables / .env.

Usage:
    python read_minio.py <bucket> <object_key> [output_file]

If output_file is omitted, the object's bytes are written to stdout.
"""

import sys

import boto3

from config import MINIO_URL, MINIO_USERNAME, MINIO_PASSWORD


def get_minio_client():
    """Create a boto3 S3 client configured to talk to the local MinIO server."""
    return boto3.client(
        "s3",
        endpoint_url=MINIO_URL,
        aws_access_key_id=MINIO_USERNAME,
        aws_secret_access_key=MINIO_PASSWORD,
        # MinIO doesn't do virtual-hosted-style buckets by default on localhost.
        config=boto3.session.Config(s3={"addressing_style": "path"}),
    )


def read_object(client, bucket: str, key: str) -> bytes:
    """Fetch a single object's bytes from a MinIO bucket."""
    response = client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def main() -> None:
    if len(sys.argv) not in (3, 4):
        print(f"Usage: python {sys.argv[0]} <bucket> <object_key> [output_file]")
        sys.exit(1)

    bucket, key = sys.argv[1], sys.argv[2]
    output_file = sys.argv[3] if len(sys.argv) == 4 else None

    client = get_minio_client()
    data = read_object(client, bucket, key)

    if output_file:
        with open(output_file, "wb") as f:
            f.write(data)
        print(f"Wrote {len(data)} bytes to {output_file}")
    else:
        sys.stdout.buffer.write(data)


if __name__ == "__main__":
    main()
