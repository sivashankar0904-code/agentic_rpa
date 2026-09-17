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


def red_mask(image: np.ndarray, margin: int = 30, grow: int = 2) -> np.ndarray:
    """
    Mask the red line by channel difference rather than HSV ranges.

    r - g is a direct, illumination-robust measure of redness here: the line
    reaches r - g = 220 while both the grey background and the black ink sit
    at 0. Simpler and tighter than the two-range HSV mask in remove_red_line,
    which has to cover both ends of the hue circle.
    """
    _, green, red = cv2.split(image)
    diff = red.astype(np.int16) - green.astype(np.int16)
    mask = (diff > margin).astype(np.uint8) * 255

    if grow:
        # Catch the anti-aliased edge pixels either side of the line.
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grow * 2 + 1, grow * 2 + 1))
        mask = cv2.dilate(mask, kernel)
    return mask


def remove_thin_lines(gray: np.ndarray, ratio: float = 0.30) -> np.ndarray:
    """
    Erase the 1px background lattice, keeping anything thicker.

    The lattice and the character strokes are drawn in the *same* ink value
    (measured on real captchas: both exactly 18), so no intensity threshold
    can separate them -- which is why the fixed-threshold approach could
    never work. They differ in geometry: the lattice is exactly 1px wide
    (period 6, phase varying per image), character strokes are 3-5px.

    So a pixel is lattice only when both pixels flanking it -- horizontally
    or vertically -- are much brighter than it. Inside a stroke at least one
    flank is also ink, so strokes survive untouched. A detected pixel is
    replaced by the mean of its two flanks, which preserves the background
    gradient rather than flattening it.

    The contrast test is proportional, not a fixed jump: the same lattice
    drops 174 -> 18 on the bright side of the image but only 95 -> 46 on the
    dark side, so a fixed threshold either misses the dark half or eats real
    ink in the bright half. Swept 0.25-0.50; flat and optimal over 0.25-0.35.

    Run this twice. The first pass clears the lines; the second clears the
    lattice intersections, where both flanks are themselves lattice and so
    the first pass cannot judge them.
    """
    gf = gray.astype(np.float32)

    horizontal_flank = np.full_like(gf, np.inf)
    horizontal_flank[:, 1:-1] = np.minimum(gf[:, :-2], gf[:, 2:])
    vertical_flank = np.full_like(gf, np.inf)
    vertical_flank[1:-1, :] = np.minimum(gf[:-2, :], gf[2:, :])

    is_horizontal = (horizontal_flank - gf) > ratio * horizontal_flank
    is_vertical = (vertical_flank - gf) > ratio * vertical_flank

    horizontal_fill = np.zeros_like(gf)
    horizontal_fill[:, 1:-1] = (gf[:, :-2] + gf[:, 2:]) / 2.0
    vertical_fill = np.zeros_like(gf)
    vertical_fill[1:-1, :] = (gf[:-2, :] + gf[2:, :]) / 2.0

    out = gf.copy()
    out = np.where(is_horizontal & is_vertical, (horizontal_fill + vertical_fill) / 2.0, out)
    out = np.where(is_horizontal & ~is_vertical, horizontal_fill, out)
    out = np.where(is_vertical & ~is_horizontal, vertical_fill, out)
    return np.clip(out, 0, 255).astype(np.uint8)


def sauvola(gray: np.ndarray, window: int = 25, k: float = 0.3, r: float = 128.0) -> np.ndarray:
    """
    Sauvola local thresholding: t = mean * (1 + k * (std / r - 1)).

    Replaces the fixed global threshold. The background carries a >2x
    left-to-right brightness gradient (~58 on the left, ~130 on the right),
    so any single global threshold sits above the left-hand background and
    below the right-hand one -- flooding the left half to black while the
    right half thresholds correctly. Sauvola adapts to that gradient without
    needing an explicit background model, and leaves low-contrast regions as
    background instead of promoting their texture to ink.

    Implemented with box filters so this needs no extra dependency.
    """
    gf = gray.astype(np.float32)
    mean = cv2.boxFilter(gf, -1, (window, window), normalize=True, borderType=cv2.BORDER_REPLICATE)
    mean_sq = cv2.boxFilter(gf * gf, -1, (window, window), normalize=True, borderType=cv2.BORDER_REPLICATE)
    std = np.sqrt(np.maximum(mean_sq - mean * mean, 0))
    threshold = mean * (1.0 + k * (std / r - 1.0))
    return np.where(gf > threshold, 255, 0).astype(np.uint8)


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


def remove_small_components(binary: np.ndarray, min_area: int = 15) -> np.ndarray:
    """
    Drop every connected dark component smaller than min_area.

    Measured across a 23-image sample (via cv2.connectedComponentsWithStats):
    non-character component areas span a continuum from 1px up into the
    hundreds, with no clean gap separating noise from real (sometimes
    small, sometimes naturally-separated) character pieces — e.g. a
    genuinely disconnected stroke tip measured at 183px, well above border
    dashes measured as small as 25px. Position doesn't discriminate either:
    every real character blob in the sample touches the border-clearing
    strip (frame-to-frame text), exactly like the leftover dash/tick
    artifacts do, so filtering by edge-adjacency would delete real
    characters along with the artifacts it's meant to catch (confirmed by
    checking the largest, unambiguously-real component in every sample —
    all sit flush against the cleared border strip too).

    Given no reliable rule to separate the two, this stays deliberately
    conservative: min_area=15 sits right above the observed gap where the
    bulk of pure speckle ends (areas 1-15px cover the noise; the smallest
    genuine border/dash artifact seen was 25px). It removes unambiguous
    speckle only and knowingly leaves larger border/dash decoration in
    place rather than risk deleting real character content — that residue
    is a smaller downstream problem than losing a character, especially
    since the eventual CNN training input is the grayscale crop, not this
    binary mask (see docs/captcha_finetune_strategy.md).
    """
    # Characters are black-on-white here; invert so they're the foreground
    # (connectedComponentsWithStats labels foreground/non-zero pixels).
    inverted = cv2.bitwise_not(binary)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(inverted, connectivity=8)

    filtered = np.zeros_like(inverted)
    for label in range(1, num_labels):  # skip label 0, the background
        if stats[label, cv2.CC_STAT_AREA] >= min_area:
            filtered[labels == label] = 255

    return cv2.bitwise_not(filtered)

def dilate_characters(binary: np.ndarray, ksize: int = 2, iterations: int = 1) -> np.ndarray:
    """
    Thicken character strokes that come out too thin after denoising.

    The median blur and fixed-threshold steps can erode strokes down to
    near-disconnected slivers, which hurts downstream OCR. Characters are
    black-on-white here, so invert before dilating (dilation grows the
    foreground) and invert back afterward.

    Not part of the default pipeline: on this captcha set, characters
    already touch/overlap in the source font at the ink level (confirmed by
    comparing raw-image thresholds against connected-component analysis),
    so dilating only thickens the fusion further. Kept as an opt-in tool for
    a future dataset/threshold combination that actually renders strokes
    too thin.
    """
    inverted = cv2.bitwise_not(binary)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
    dilated = cv2.dilate(inverted, kernel, iterations=iterations)
    return cv2.bitwise_not(dilated)


def erode_characters(binary: np.ndarray, ksize: int = 2, iterations: int = 1) -> np.ndarray:
    """
    Thin character strokes that come out too thick or fused after denoising.

    Counterpart to dilate_characters: useful when strokes bleed into each
    other or the font renders heavier than expected. Characters are
    black-on-white here, so invert before eroding (erosion shrinks the
    foreground) and invert back afterward.

    Not part of the default pipeline: erosion cannot split characters that
    are already fused into one connected blob (once two strokes touch, the
    touching pixels are interior, not edge, so eroding by the same amount
    that dilated them shaves the outside without separating the merged
    core) — confirmed on real samples where dilate+erode nets out to a
    thicker, still-fused blob rather than the original separated strokes.
    """
    inverted = cv2.bitwise_not(binary)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
    eroded = cv2.erode(inverted, kernel, iterations=iterations)
    return cv2.bitwise_not(eroded)


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


def clean_grayscale(image: np.ndarray) -> np.ndarray:
    """
    Remove both background distractors, returning a clean grayscale image.

    This is the half of the pipeline worth feeding a CNN (see
    docs/captcha_finetune_strategy.md, which trains on grayscale crops rather
    than binary masks): the lattice and the red line are gone, but the
    grayscale detail that helps disambiguate touching strokes is still there.
    """
    gray = to_grayscale(image)
    # Twice: pass one clears the lattice lines, pass two their intersections.
    gray = remove_thin_lines(gray)
    gray = remove_thin_lines(gray)
    # Inpaint the red line only after the lattice is gone, so the inpainter
    # samples clean neighbours instead of grid pixels.
    return cv2.inpaint(gray, red_mask(image), 3, cv2.INPAINT_TELEA)


def preprocess_captcha(image: np.ndarray) -> np.ndarray:
    """
    Run the full preprocessing pipeline over a raw captcha image.

    Strategy and the measurements behind it: docs/captcha_cleaning_strategy.md.
    """
    cleaned = clean_grayscale(image)
    binary = sauvola(cleaned)
    # The 1px frame thresholds as ink and, spanning the full width, dominates
    # every other stray mark; 3px covers it plus its anti-aliased edge.
    no_border = remove_border(binary, thickness=3)
    return upscale(no_border)


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
