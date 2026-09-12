"""
Captcha image preprocessing pipeline.

Each function performs exactly one operation and returns a new image
(numpy array), so steps can be composed, reordered, or tested independently.

Usage:
    python preprocess.py 001c218e-5ce3-4f79-b2af-23af8e6b7c5d.png output.png
"""

import sys

import cv2
import numpy as np


def remove_red_line(image: np.ndarray) -> np.ndarray:
    """
    Remove the red strike-through line by color (not grayscale intensity,
    since red and the dark-gray characters/background can share similar
    grayscale values). Detects red pixels in HSV, then inpaints over them
    using surrounding context. Operates on the original BGR image.
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # Red wraps around the HSV hue circle, so cover both ends.
    lower_red_1 = np.array([0, 70, 50])
    upper_red_1 = np.array([10, 255, 255])
    lower_red_2 = np.array([170, 70, 50])
    upper_red_2 = np.array([180, 255, 255])

    mask_1 = cv2.inRange(hsv, lower_red_1, upper_red_1)
    mask_2 = cv2.inRange(hsv, lower_red_2, upper_red_2)
    red_mask = cv2.bitwise_or(mask_1, mask_2)

    # Slightly thicken the mask so anti-aliased edge pixels are covered too.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    red_mask = cv2.dilate(red_mask, kernel, iterations=1)

    repaired = cv2.inpaint(image, red_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    return repaired


def to_grayscale(image: np.ndarray) -> np.ndarray:
    """Convert a BGR image to single-channel grayscale."""
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def remove_dot_pattern(gray: np.ndarray, ksize: int = 5) -> np.ndarray:
    """
    Remove the regular dotted background texture with a median blur.

    Must run on grayscale *before* thresholding: the background dots are
    roughly the same pixel-thickness as the character strokes, so once the
    image is binarized, morphological opening can no longer tell dots from
    strokes apart and either leaves the dots or eats the strokes. On
    grayscale, a median blur suppresses the small isolated dots (each
    surrounded by background) while a real stroke's run of dark pixels
    survives the median.
    """
    return cv2.medianBlur(gray, ksize)


def binarize(gray: np.ndarray, threshold: int = 65) -> np.ndarray:
    """
    Convert grayscale to black-on-white binary using a fixed threshold.

    The background is a dark diagonal-hatch/gradient pattern whose intensity
    range overlaps the characters, so adaptive methods (Otsu, CLAHE-boosted
    Otsu) end up keeping the hatch alongside the text. A fixed threshold
    tuned to this captcha's dark-hatch/mid-gray-character split isolates the
    characters far more cleanly.
    """
    _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
    return binary


def remove_border(binary: np.ndarray, thickness: int = 2) -> np.ndarray:
    """
    Whiten a thin strip around the image edge.

    The captcha has a 1px outline frame that would otherwise connect to
    every other dark region touching the border, merging unrelated blobs
    into one connected component.
    """
    cleaned = binary.copy()
    cleaned[:thickness, :] = 255
    cleaned[-thickness:, :] = 255
    cleaned[:, :thickness] = 255
    cleaned[:, -thickness:] = 255
    return cleaned


def remove_small_noise(binary: np.ndarray) -> np.ndarray:
    """Remove small isolated speckle left over from the background texture."""
    # Characters are black-on-white here; invert so they're the foreground
    # (morphological opening erodes/dilates the foreground).
    inverted = cv2.bitwise_not(binary)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    opened = cv2.morphologyEx(inverted, cv2.MORPH_OPEN, kernel, iterations=1)
    return cv2.bitwise_not(opened)


def upscale(image: np.ndarray, scale: float = 3.0) -> np.ndarray:
    """
    Upscale the image so downstream OCR has more pixels to work with.

    Uses nearest-neighbor interpolation: the image is already binary
    (pure black/white) at this point, and a smoothing interpolation
    (e.g. cubic) would reintroduce gray fringing at edges.
    """
    height, width = image.shape[:2]
    new_size = (int(width * scale), int(height * scale))
    return cv2.resize(image, new_size, interpolation=cv2.INTER_NEAREST)


def preprocess_captcha(image: np.ndarray) -> np.ndarray:
    """Run the full preprocessing pipeline over a raw captcha image."""
    line_removed = remove_red_line(image)
    gray = to_grayscale(line_removed)
    dot_removed = remove_dot_pattern(gray)
    binary = binarize(dot_removed)
    no_border = remove_border(binary)
    cleaned = remove_small_noise(no_border)
    return upscale(cleaned)


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <input_image> <output_image>")
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]

    image = cv2.imread(input_path)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {input_path}")

    result = preprocess_captcha(image)
    cv2.imwrite(output_path, result)
    print(f"Wrote preprocessed image to {output_path}")


if __name__ == "__main__":
    main()
