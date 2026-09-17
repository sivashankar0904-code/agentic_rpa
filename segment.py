"""
Split a preprocessed captcha into its individual characters.

These captchas cannot be segmented by the usual projection-profile method:
adjacent glyphs touch at the ink level, so the vertical ink profile never
returns to zero between characters (measured: minima bottom out around 4-9
pixels, never 0). Equal-width slicing does not work either -- the text block
is a very consistent width (114.8 +/- 4.2 px over 24 samples) but the glyphs
inside it are not uniformly pitched, so cutting into 6 equal columns lands on
average-density columns rather than gaps (measured ratio 1.01 against the
block mean, i.e. no better than an arbitrary cut).

What does work is treating each boundary as a *seam*: start from the nominal
equal-width position, then find the lowest-cost path through the ink near it.
Allowing the cut to bend around a stroke roughly halves the ink it crosses
(18.0 -> 8.2 average over the same samples).

Usage:
    python segment.py <preprocessed_image> <output_dir>
"""

import os
import sys

import cv2
import numpy as np

CAPTCHA_LENGTH = 6
SEARCH_RADIUS = 10
MIN_INK_PER_COLUMN = 4

# Cost per pixel of sideways travel, against 1.0 per ink pixel crossed. Tuned
# by sweeping against the ink a seam actually cuts through: 0.5 barely lets the
# seam bend at all (13.1 ink crossed), while 0.0 cuts the least ink (4.0) but
# lets a seam wander 7.6px and risks drifting into the neighbouring character.
# 0.05 gets essentially all of the benefit (4.3) at a controlled ~4.7px bend.
SEAM_BIAS = 0.05


def text_bounds(binary: np.ndarray, min_ink: int = MIN_INK_PER_COLUMN) -> tuple[int, int]:
    """Left and right edge of the text block, ignoring sparse noise columns."""
    profile = (binary == 0).sum(axis=0)
    solid = np.where(profile >= min_ink)[0]
    if len(solid) == 0:
        return 0, binary.shape[1]
    return int(solid.min()), int(solid.max()) + 1


def _carve_seam(ink: np.ndarray, start_column: int, radius: int) -> np.ndarray:
    """Lowest-cost top-to-bottom path within +/- radius of start_column.

    Returns one column index per row. The seam may step at most one pixel
    sideways per row, so it can bend around a stroke without wandering off
    into the neighbouring character.
    """
    height, width = ink.shape
    left = max(0, start_column - radius)
    right = min(width, start_column + radius + 1)
    band = ink[:, left:right].astype(np.float64)
    band_width = band.shape[1]

    # Bias towards staying near the nominal cut, so that on a blank band the
    # seam does not drift to an arbitrary edge of the search window.
    bias = np.abs(np.arange(band_width) - (start_column - left)) * SEAM_BIAS
    cost = band + bias

    total = cost.copy()
    back = np.zeros_like(total, dtype=np.int32)
    for row in range(1, height):
        for col in range(band_width):
            lo = max(0, col - 1)
            hi = min(band_width, col + 2)
            step = int(np.argmin(total[row - 1, lo:hi])) + lo
            back[row, col] = step
            total[row, col] += total[row - 1, step]

    seam = np.zeros(height, dtype=np.int32)
    seam[-1] = int(np.argmin(total[-1]))
    for row in range(height - 1, 0, -1):
        seam[row - 1] = back[row, seam[row]]
    return seam + left


def character_seams(binary: np.ndarray, count: int = CAPTCHA_LENGTH,
                    radius: int = SEARCH_RADIUS) -> list[np.ndarray]:
    """The count-1 internal cut seams separating the characters."""
    ink = (binary == 0).astype(np.float64)
    left, right = text_bounds(binary)
    pitch = (right - left) / float(count)
    return [
        _carve_seam(ink, int(round(left + pitch * i)), radius)
        for i in range(1, count)
    ]


def split_characters(binary: np.ndarray, count: int = CAPTCHA_LENGTH,
                     radius: int = SEARCH_RADIUS) -> list[np.ndarray]:
    """Split into count images, one per character, each cropped to its ink.

    Pixels on the far side of a seam are whitened rather than included, so a
    neighbouring character's stroke does not leak into this character's crop.
    """
    height, width = binary.shape
    left, right = text_bounds(binary)
    seams = character_seams(binary, count, radius)
    columns = np.arange(width)[None, :]

    pieces = []
    for index in range(count):
        piece = binary.copy()

        if index > 0:
            before = seams[index - 1][:, None]
            piece[columns < before] = 255
        else:
            piece[:, :left] = 255

        if index < count - 1:
            after = seams[index][:, None]
            piece[columns >= after] = 255
        else:
            piece[:, right:] = 255

        pieces.append(_crop_to_ink(_drop_neighbour_bleed(piece)))
    return pieces


def split_grayscale_with_masks(gray: np.ndarray, binary: np.ndarray,
                               count: int = CAPTCHA_LENGTH,
                               radius: int = SEARCH_RADIUS) -> list[tuple[np.ndarray, np.ndarray]]:
    """Split the *grayscale* image using seams computed from the binary one.

    Returns (grayscale_crop, binary_crop) pairs. The binary crop says which
    pixels are ink, which normalise_contrast needs to pick its black and white
    reference levels.

    This is the variant worth feeding a CNN. Thresholding is only needed to
    locate the characters; applying the resulting seams to the grayscale keeps
    the faint connecting pixels that binarisation removes, so strokes that come
    out fragmented in a binary crop stay intact here. See
    docs/captcha_finetune_strategy.md, which trains on grayscale crops.
    """
    height, width = binary.shape
    left, right = text_bounds(binary)
    seams = character_seams(binary, count, radius)
    columns = np.arange(width)[None, :]

    pieces = []
    for index in range(count):
        piece = gray.copy()
        mask = binary.copy()

        if index > 0:
            outside = columns < seams[index - 1][:, None]
            piece[outside] = 255
            mask[outside] = 255
        else:
            piece[:, :left] = 255
            mask[:, :left] = 255

        if index < count - 1:
            outside = columns >= seams[index][:, None]
            piece[outside] = 255
            mask[outside] = 255
        else:
            piece[:, right:] = 255
            mask[:, right:] = 255

        # Take the crop box from the binary mask: on the grayscale the ink
        # (18-46) and the background (up to ~220) are separated by a broad
        # ramp, so any single grayscale cutoff either keeps the whole frame or
        # eats the stroke edges. The mask already encodes that decision.
        pieces.append((_crop_like(piece, mask), _crop_like(mask, mask)))
    return pieces


def split_grayscale(gray: np.ndarray, binary: np.ndarray, count: int = CAPTCHA_LENGTH,
                    radius: int = SEARCH_RADIUS) -> list[np.ndarray]:
    """Grayscale character crops (see split_grayscale_with_masks)."""
    return [piece for piece, _ in split_grayscale_with_masks(gray, binary, count, radius)]


def _crop_like(image: np.ndarray, mask: np.ndarray, pad: int = 1) -> np.ndarray:
    """Crop `image` to the bounding box of the ink in `mask`."""
    ys, xs = np.where(mask == 0)
    if len(xs) == 0:
        return image
    y0, y1 = max(0, ys.min() - pad), min(image.shape[0], ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(image.shape[1], xs.max() + pad + 1)
    return image[y0:y1, x0:x1]


def normalise_contrast(piece: np.ndarray, ink: np.ndarray,
                       mask_value: int = 250) -> np.ndarray:
    """Stretch a crop so its ink lands at black and its background at white.

    The captcha's left-to-right illumination gradient survives into the crops:
    measured over 30 captchas, the median level behind a character climbs from
    64 at position 0 to 130 at position 5, a 71-level spread, with per-image
    variance of +/-25 to +/-58 on top. Left alone, a CNN sees the same digit at
    a different contrast depending on where in the string it sat.

    The two reference levels are taken from the binary mask -- the median of
    the pixels it calls ink, and the median of those it calls background --
    rather than from percentiles of the crop as a whole. A percentile stretch
    fails here because a crop is mostly background, so its 5th-95th range
    spans mostly noise and gets amplified (measured: doing that *increased*
    the spread to 86.7 and doubled the variance).
    """
    work = piece.astype(np.float32)
    inside = piece < mask_value
    is_ink = ink & inside
    is_paper = (~ink) & inside
    if not is_ink.any() or not is_paper.any():
        return piece

    low = float(np.median(work[is_ink]))
    high = float(np.median(work[is_paper]))
    if high - low < 1e-3:
        return piece

    stretched = np.clip((work - low) / (high - low), 0.0, 1.0) * 255.0
    out = np.full(piece.shape, 255, np.uint8)
    out[inside] = stretched[inside].astype(np.uint8)
    return out


def normalise(piece: np.ndarray, size: int = 32, pad: int = 2) -> np.ndarray:
    """Fit a character crop into a fixed size x size box, preserving aspect.

    Raw crops are not a consistent size, and not for an interesting reason:
    a crop's bounding box spans the full sideways excursion of the two seams
    that bound it, so the more a seam had to bend, the wider the crop. Seam
    bend peaks in the middle of the captcha (measured 3.2, 5.0, 6.0, 5.7,
    3.8 px for seams 0-4, because the middle glyphs overlap most), which makes
    the 4th character's crop come out visibly the widest -- ~30px against
    ~22px at the ends -- even though the underlying slots are all ~19-21px.

    Scaling by the longest side rather than stretching to fill keeps the glyph
    proportions intact, so a '1' stays narrow instead of being smeared out to
    the width of a '0'. The result is what a CNN wants: every character the
    same size, at the same scale, centred.
    """
    inner = max(1, size - 2 * pad)
    height, width = piece.shape[:2]
    if height == 0 or width == 0:
        return np.full((size, size), 255, np.uint8)

    scale = inner / float(max(height, width))
    new_w = max(1, int(round(width * scale)))
    new_h = max(1, int(round(height * scale)))
    resized = cv2.resize(piece, (new_w, new_h), interpolation=cv2.INTER_AREA)

    canvas = np.full((size, size), 255, np.uint8)
    y0 = (size - new_h) // 2
    x0 = (size - new_w) // 2
    canvas[y0:y0 + new_h, x0:x0 + new_w] = resized
    return canvas


def stitch(pieces: list[tuple[np.ndarray, np.ndarray]], size: int = 32, gap: int = 8,
           margin: int = 8) -> np.ndarray:
    """Re-assemble normalised characters into one image, spaced apart.

    Takes the (grayscale, mask) pairs from split_grayscale_with_masks. Each
    character is contrast-normalised and scaled into the same size x size box,
    so the crop-width differences caused by seam bend disappear and no
    character looks zoomed relative to its neighbours. Laying them out with a
    blank gap between then turns glyphs that were touching in the original into
    visibly separate ones -- the fusion cannot be undone *within* a glyph, but
    it no longer runs across the boundary between them.
    """
    cells = [
        normalise(normalise_contrast(piece, mask == 0), size)
        for piece, mask in pieces
    ]
    height = size + 2 * margin
    width = 2 * margin + len(cells) * size + max(0, len(cells) - 1) * gap

    canvas = np.full((height, width), 255, np.uint8)
    x = margin
    for cell in cells:
        canvas[margin:margin + size, x:x + size] = cell
        x += size + gap
    return canvas


def _drop_neighbour_bleed(binary: np.ndarray, min_area: int = 20) -> np.ndarray:
    """Remove slivers of the adjacent character left behind by the seam.

    A seam that has to bend around a stroke can leave a thin crescent of the
    neighbouring glyph inside this crop. Such a piece is always small and
    always hugs the seam, i.e. the left or right edge of the crop, while the
    character itself is the dominant component. So: keep the largest
    component, plus any other sizeable one that is not stuck to a side edge
    (genuinely detached parts of a glyph, such as the dot of an 'i', are kept
    that way).
    """
    inverted = cv2.bitwise_not(binary)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(inverted, connectivity=8)
    if count <= 2:
        return binary

    areas = stats[1:, cv2.CC_STAT_AREA]
    largest = int(np.argmax(areas)) + 1
    width = binary.shape[1]

    keep = np.zeros(binary.shape, bool)
    for label in range(1, count):
        x, _, w, _, area = stats[label]
        touches_side = x == 0 or (x + w) >= width
        if label == largest or (area >= min_area and not touches_side):
            keep |= labels == label

    return np.where(keep, 0, 255).astype(np.uint8)


def _crop_to_ink(image: np.ndarray, pad: int = 1, threshold: int = 0) -> np.ndarray:
    """Tighten a character image down to its ink, with a small margin.

    threshold is 0 for a binary image (ink is exactly 0) and a mid-grey value
    for a grayscale one, where ink is dark but not pure black.
    """
    ys, xs = np.where(image <= threshold)
    if len(xs) == 0:
        return image
    y0, y1 = max(0, ys.min() - pad), min(image.shape[0], ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(image.shape[1], xs.max() + pad + 1)
    return image[y0:y1, x0:x1]


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <raw_captcha_image> <output_dir>")
        sys.exit(1)

    from preprocess import clean_grayscale, remove_border, sauvola

    input_path, output_dir = sys.argv[1], sys.argv[2]
    image = cv2.imread(input_path)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {input_path}")

    gray = clean_grayscale(image)
    binary = remove_border(sauvola(gray), thickness=3)
    pieces = split_grayscale_with_masks(gray, binary)

    os.makedirs(output_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(input_path))[0]

    for index, (piece, mask) in enumerate(pieces):
        out = os.path.join(output_dir, f"{stem}_{index}.png")
        cv2.imwrite(out, normalise(normalise_contrast(piece, mask == 0)))
        print(f"Wrote {out}")

    joined = os.path.join(output_dir, f"{stem}_stitched.png")
    cv2.imwrite(joined, stitch(pieces))
    print(f"Wrote {joined}")


if __name__ == "__main__":
    main()
