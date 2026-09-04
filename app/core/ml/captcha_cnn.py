"""CNN architecture for 6-character alphanumeric captcha recognition.

PyTorch reimplementation of the reference architecture at
https://github.com/SIDD58/Captcha-recognition-using-CNN (conv/pool/batchnorm
stack -> flatten -> one dense head per character position). Ported to
PyTorch rather than the reference's TensorFlow/Keras because the worker
image is python:3.12-alpine (musl): TensorFlow has no prebuilt musl wheels,
while PyTorch's CPU wheels install cleanly there.

CAPTCHA_LENGTH is 6, not the reference repo's 5 — the real GST captchas
this pipeline trains on are always 6 characters (confirmed against actual
labeled data; a labeled '752728' broke the original CAPTCHA_LENGTH=5
assumption). Fixed-length, not variable — if that assumption turns out to
be wrong, this needs a real architecture change (e.g. padding/masking to a
max length, or a CTC/sequence model), not just another constant tweak.

Input: single-channel (grayscale) 50 (height) x 200 (width) images, matching
the reference dataset's fixed captcha image size.
Output: CAPTCHA_LENGTH independent 36-way classifications, one per
character position (26 lowercase letters + 10 digits).
"""

import torch
from torch import nn

CHARSET = "abcdefghijklmnopqrstuvwxyz0123456789"
NUM_CLASSES = len(CHARSET)
CAPTCHA_LENGTH = 6
IMAGE_HEIGHT = 50
IMAGE_WIDTH = 200

_CHAR_TO_INDEX = {char: index for index, char in enumerate(CHARSET)}


def encode_label(text: str) -> list[int]:
    """Map a captcha's ground-truth text to one class index per position."""
    text = text.strip().lower()
    if len(text) != CAPTCHA_LENGTH:
        raise ValueError(f"Expected a {CAPTCHA_LENGTH}-character label, got {text!r}")
    return [_CHAR_TO_INDEX[char] for char in text]


def decode_prediction(logits: torch.Tensor) -> str:
    """Turn a (CAPTCHA_LENGTH, NUM_CLASSES) logits tensor back into text."""
    indices = logits.argmax(dim=-1).tolist()
    return "".join(CHARSET[index] for index in indices)


class CaptchaCNN(nn.Module):
    """Shared conv backbone feeding CAPTCHA_LENGTH independent classifier heads."""

    def __init__(self) -> None:
        super().__init__()

        self.backbone = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )

        # After three 2x2 max-pools: 50x200 -> 6x25.
        flattened_size = 128 * (IMAGE_HEIGHT // 8) * (IMAGE_WIDTH // 8)

        self.shared_dense = nn.Sequential(
            nn.Flatten(),
            nn.Linear(flattened_size, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
        )

        # One independent head per character position.
        self.heads = nn.ModuleList(
            nn.Linear(256, NUM_CLASSES) for _ in range(CAPTCHA_LENGTH)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, 1, IMAGE_HEIGHT, IMAGE_WIDTH) -> (batch, CAPTCHA_LENGTH, NUM_CLASSES)."""
        features = self.backbone(x)
        shared = self.shared_dense(features)
        head_outputs = [head(shared) for head in self.heads]
        return torch.stack(head_outputs, dim=1)
