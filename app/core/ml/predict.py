"""Inference: load the current captcha-cnn-latest.pt weights and predict text
for a single captcha image.

Decoupled from Celery/MinIO the same way train.py is: predict_captcha() just
takes raw model + image bytes, so it's unit-testable without a broker or
object store in the loop. The MinIO download happens one layer up, in
app/tasks/predict_tasks.py, mirroring training_tasks.py's split.
"""

import io

import torch
from PIL import Image

from app.core.ml.captcha_cnn import (
    CaptchaCNN,
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
    decode_prediction,
)


def predict_captcha(model_bytes: bytes, image_bytes: bytes) -> str:
    """Run a single captcha image through the trained model and return its
    predicted text (CAPTCHA_LENGTH characters, see captcha_cnn.py)."""
    model = CaptchaCNN()
    state_dict = torch.load(io.BytesIO(model_bytes), map_location="cpu", weights_only=True)
    model.load_state_dict(state_dict)
    model.eval()

    image = Image.open(io.BytesIO(image_bytes)).convert("L")
    image = image.resize((IMAGE_WIDTH, IMAGE_HEIGHT))
    pixels = torch.frombuffer(bytearray(image.tobytes()), dtype=torch.uint8)
    pixels = pixels.reshape(1, 1, IMAGE_HEIGHT, IMAGE_WIDTH).float() / 255.0

    with torch.no_grad():
        logits = model(pixels)  # (1, CAPTCHA_LENGTH, NUM_CLASSES)

    return decode_prediction(logits[0])
