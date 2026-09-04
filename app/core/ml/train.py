"""Training loop for CaptchaCNN, decoupled from Celery/MinIO/Postgres.

Takes plain in-memory (image_bytes, label) pairs and returns trained model
weights as bytes, so it can be unit-tested without a broker, object store,
or database in the loop. Metrics/params/the final model are logged to
MLflow (see app/core/config/config.py's mlflow_* settings) so a training
run is visible in the MLflow UI, not just worker logs.
"""

import io
from dataclasses import dataclass

import mlflow
import mlflow.pytorch
import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset

from app.core.config.config import get_settings
from app.core.logging.logging import get_logger
from app.core.ml.captcha_cnn import (
    CAPTCHA_LENGTH,
    IMAGE_HEIGHT,
    IMAGE_WIDTH,
    CaptchaCNN,
    encode_label,
)

logger = get_logger(__name__)

DEFAULT_EPOCHS = 60  # matches the reference repo's training run


@dataclass
class TrainingResult:
    """Everything training_tasks.py needs to persist a completed run —
    the weights for MinIO, the rest for model_versions (see
    app/core/model_versions/)."""

    model_bytes: bytes
    final_loss: float
    final_accuracy: float
    mlflow_run_id: str


class _CaptchaDataset(Dataset):
    """Decodes raw captcha image bytes + text labels into model-ready tensors."""

    def __init__(self, samples: list[tuple[bytes, str]]) -> None:
        self._samples = samples

    def __len__(self) -> int:
        return len(self._samples)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        image_bytes, label = self._samples[index]

        image = Image.open(io.BytesIO(image_bytes)).convert("L")
        image = image.resize((IMAGE_WIDTH, IMAGE_HEIGHT))
        pixels = torch.frombuffer(bytearray(image.tobytes()), dtype=torch.uint8)
        pixels = pixels.reshape(1, IMAGE_HEIGHT, IMAGE_WIDTH).float() / 255.0

        target = torch.tensor(encode_label(label), dtype=torch.long)
        return pixels, target


def train_captcha_model(
    samples: list[tuple[bytes, str]],
    epochs: int = DEFAULT_EPOCHS,
    batch_size: int = 32,
    learning_rate: float = 1e-3,
) -> TrainingResult:
    """Train a CaptchaCNN on labeled captcha images.

    samples: (raw_image_bytes, ground_truth_text) pairs, e.g. downloaded from
    the rpa-captchas MinIO bucket and joined against the Postgres labels
    table. Returns a TrainingResult: torch.save()'d state_dict bytes (ready
    for captcha_model_store.save_model()) plus the final epoch's
    loss/accuracy and this run's MLflow run id (ready for
    model_versions.record_model_version()).
    """
    if not samples:
        raise ValueError("train_captcha_model requires at least one labeled sample")

    dataset = _CaptchaDataset(samples)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    model = CaptchaCNN()
    model.train()

    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    criterion = nn.CrossEntropyLoss()

    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment_name)

    with mlflow.start_run() as run:
        mlflow.log_params(
            {
                "epochs": epochs,
                "batch_size": batch_size,
                "learning_rate": learning_rate,
                "sample_count": len(samples),
            }
        )

        avg_loss = 0.0
        accuracy = 0.0

        for epoch in range(epochs):
            epoch_loss = 0.0
            correct_positions = 0
            total_positions = 0

            for images, targets in loader:
                optimizer.zero_grad()

                logits = model(images)  # (batch, CAPTCHA_LENGTH, NUM_CLASSES)
                # Sum per-position cross-entropy losses across all CAPTCHA_LENGTH heads.
                loss = sum(
                    criterion(logits[:, position, :], targets[:, position])
                    for position in range(CAPTCHA_LENGTH)
                )

                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()

                predictions = logits.argmax(dim=-1)  # (batch, CAPTCHA_LENGTH)
                correct_positions += (predictions == targets).sum().item()
                total_positions += targets.numel()

            avg_loss = epoch_loss / len(loader)
            accuracy = correct_positions / total_positions
            logger.info(
                "epoch %d/%d - loss %.4f - per-char accuracy %.4f",
                epoch + 1, epochs, avg_loss, accuracy,
            )
            mlflow.log_metrics({"loss": avg_loss, "per_char_accuracy": accuracy}, step=epoch)

        buffer = io.BytesIO()
        torch.save(model.state_dict(), buffer)
        model_bytes = buffer.getvalue()

        # Logged to MLflow for browsing/comparison across runs in its UI;
        # the MinIO upload in app/tasks/training_tasks.py (via
        # captcha_model_store.save_model) remains the copy the RPA flow
        # actually loads back for inference.
        mlflow.pytorch.log_model(model, artifact_path="model")

        mlflow_run_id = run.info.run_id

    return TrainingResult(
        model_bytes=model_bytes,
        final_loss=avg_loss,
        final_accuracy=accuracy,
        mlflow_run_id=mlflow_run_id,
    )
