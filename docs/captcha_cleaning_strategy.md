# Captcha Cleaning Strategy

Derived by measuring the actual pixel structure of captchas pulled from the
`rpa-captchas` MinIO bucket, then testing candidate pipelines against two
quantitative metrics (defined at the end). Supersedes the ad-hoc
median-blur + fixed-threshold approach currently in `preprocess.py`.

## 1. What the image is actually made of

Measurements, not guesses:

| Property | Measured value |
| --- | --- |
| Image size | 50x182 (occasionally 52x184) |
| Background lattice | Strictly periodic, **exactly 1px wide**, period **exactly 6px** |
| Lattice phase | Varies per image (must be detected, not assumed) |
| Lattice ink value | **18** |
| Character stroke ink value | **18** (identical) |
| Character stroke width | 3-5px |
| Background brightness | **~58 on the left, ~130 on the right** (>2x gradient) |
| Red line | r-g up to 220; crosses the text, position varies per image |

Two of these facts drive the entire design:

**(a) The lattice and the characters are drawn in the same ink value (18).**
No intensity threshold — global, Otsu, adaptive, or otherwise — can separate
them. Every threshold-first approach is doomed before it starts. They differ
only in *geometry*: the lattice is 1px wide, strokes are 3-5px.

**(b) The background has a >2x left-to-right brightness gradient.**
The current fixed `threshold=65` sits *above* most of the left-hand background
and far *below* the right-hand background, so the left half floods to black
while the right half thresholds correctly. This is the direct cause of the
"solid blob with holes punched in it" output, and it is why the failure looks
different on every image.

A further measurement worth recording, because it corrects an intuitive but
wrong reading: the characters are painted **over** the lattice and occlude it.
Inside a glyph, lattice-aligned pixels and their neighbours differ by ~3 grey
levels; in the background they differ by ~156. So a lattice pixel is an
artifact only where it is dramatically darker than the pixels flanking it.

## 2. The strategy

Order matters. Each step is justified by a measurement above.

1. **Remove thin lines (twice).** A pixel is lattice only when *both* flanking
   pixels — horizontally or vertically — are much brighter than it. Inside a
   3-5px stroke at least one flank is also ink, so strokes survive untouched.
   Replace a detected lattice pixel with the mean of its two flanks, which
   preserves the background gradient instead of flattening it. Run twice: the
   first pass clears the lines, the second clears the lattice *intersections*
   (where both flanks are themselves lattice, so pass one cannot judge them).

   The contrast test must be **proportional** (`flank - pixel > 0.30 * flank`),
   not a fixed jump. The same lattice drops 174 -> 18 on the bright side but
   only 95 -> 46 on the dark side; a fixed threshold either misses the dark
   half or eats real ink in the bright half. Swept 0.25-0.50: flat and optimal
   across 0.25-0.35, degrading above.

2. **Remove the red line by channel difference, then inpaint.** `r - g > 30`
   is a direct, illumination-robust redness test (the line reaches 220, grey
   background and black ink sit at 0) and is simpler and tighter than the
   two-range HSV mask. Dilate the mask by 2px to catch anti-aliased edges.
   Inpaint *after* the lattice is gone, so the inpainter samples clean
   neighbours rather than grid lines.

3. **Sauvola local thresholding** (`window=25, k=0.3`), implemented with box
   filters — no new dependency. `t = mean * (1 + k * (std/r - 1))` adapts to
   the illumination gradient without needing an explicit background model.
   This is what replaces the fixed threshold, and it is the reason the left
   half no longer floods.

4. **Strip the border frame** (3px). The 1px frame thresholds as ink and, at
   184px wide, contributes more margin ink than everything else combined.

### Rejected alternatives, and why

Recording these so they are not re-attempted:

- **Global/Otsu thresholding after background flattening** — Otsu lands at
  t=103 on a flattened image whose character/background valley sits near 50,
  sweeping mid-grey texture into ink.
- **Morphological background estimation (`MORPH_OPEN`) then division** — any
  kernel large enough to exclude 3-5px strokes from the background model also
  swallows the characters; kernels that preserve characters model the lattice
  as background instead.
- **Masked inpainting of the lattice guarded by local contrast** — the guard
  cannot fire where a glyph crosses the lattice (no contrast there), so the
  hatch survives *inside the text*, which is exactly where it matters.
- **Unguarded inpainting of the whole lattice** — smears strokes outward; the
  inpaint radius pulls ink into the gaps.
- **Fourier notch filtering** — the lattice is a clean set of spectral spikes
  (5.75-5.78px plus harmonics), so this is viable in principle, but it risks
  ringing on the glyph edges and the spatial method already works.
- **Histogram valley-seeking** — collapsed to zero ink on 4 of 12 samples when
  the dark peak landed at the search boundary. Too brittle.
- **Dilation / erosion of characters** — see `preprocess.py`; dilation worsens
  the fusion, and erosion cannot re-split glyphs that are already merged.

## 3. Results

Measured over 12 randomly sampled captchas, current pipeline vs this strategy:

| Metric | Current | New | Meaning |
| --- | --- | --- | --- |
| Margin-ink fraction | 0.109 | **0.075** | Ink outside the text band; lower is cleaner |
| Glyph-sized components | 1.67 | **3.00** | Separated characters found; 6 is ideal |

Background is ~31% cleaner and character separation nearly doubles. Visually
the difference is large: the current pipeline returns heavy fused blobs, while
this returns legible digit strings (`911801`, `870?70`, `63?012`, `564?087`)
on a clean white ground.

## 4. Known limits

- **Character fusion is not fully solved.** 3.00 separated components against
  an ideal of 6 means glyphs still touch. This is inherent to the source
  rendering — a threshold sweep from 40 to 110 on the raw image showed
  adjacent glyphs touching at the *ink* level in many captchas — so no
  cleaning step can separate them. Splitting them is a **segmentation**
  problem, not a cleaning one, and should be treated separately (projection
  profiles, watershed on the distance transform, or letting a CTC/sequence
  model avoid segmentation altogether).
- Faint red-line residue survives as scattered dots where the line crossed a
  glyph and the inpaint had only ink to sample from.
- Tuned against 12 samples out of 1364 available. Worth re-checking the
  `ratio` and Sauvola parameters against a larger batch before relying on it.

## 5. Character segmentation

Implemented in `segment.py`. Measurements over 24 tuning samples, validated on
40 unseen ones.

Two standard approaches were tested and rejected against this data:

- **Projection-profile splitting** — the vertical ink profile never returns to
  zero between glyphs (minima bottom out at 4-9 px), because adjacent
  characters touch at the ink level. There are no gaps to find.
- **Fixed-width slicing** (as used by CNN captcha notebooks trained on clean,
  well-separated datasets) — the text block itself is remarkably consistent
  (starts at column 28.4 +/- 1.1, width 114.8 +/- 4.2 over 24 samples, i.e.
  ~19px per character), which makes this tempting. But the glyphs inside the
  block are *not* uniformly pitched: cutting into 6 equal columns lands on
  columns of average ink density (measured ratio 1.01 against the block mean),
  so the cuts fall through glyphs as often as between them.

What works is a **seam carve**. Start from the nominal equal-width boundary,
then find the minimum-cost top-to-bottom path within +/-10px, where cost is
ink crossed plus a small penalty per pixel of sideways travel. The seam may
step one pixel sideways per row, so it bends around a stroke instead of
slicing through it.

Tuning, by sweeping against the ink each seam actually cuts:

| Sideways penalty | Ink crossed | Seam bend |
| --- | --- | --- |
| 0.5 (initial) | 13.06 | 1.2px |
| 0.1 | 5.33 | 3.8px |
| **0.05 (chosen)** | **4.30** | **4.7px** |
| 0.0 | 3.97 | 7.6px |

0.0 cuts marginally less ink but lets a seam wander far enough to drift into
the neighbouring character, so 0.05 is the operating point.

Results on 40 unseen captchas: mean 4.12 ink pixels crossed per seam (median
4.0, p90 9.0), 2% of seams cutting badly, **0 empty crops out of 240**, and
70% of crops containing exactly one connected component.

### Crop size varies by position -- normalise

Raw crops are not a consistent size, and the pattern is systematic: the 4th
character always comes out noticeably the widest (~29px against ~21px at the
ends), looking zoomed relative to its neighbours.

The cause is not seam *placement* -- the seams land almost exactly on the ideal
equal-spacing fractions (measured 0.166, 0.327, 0.491, 0.673, 0.837 against an
ideal of 0.167, 0.333, 0.500, 0.667, 0.833), and the seam-to-seam slots are
near uniform at 18.3-20.8px. It is seam *bend*. A crop's bounding box spans the
full sideways excursion of the two seams around it, so the more a seam had to
bend, the wider the crop. Bend peaks in the middle, where the glyphs overlap
most:

| Seam | 0 | 1 | 2 | 3 | 4 |
| --- | --- | --- | --- | --- | --- |
| Mean bend (px) | 3.2 | 5.0 | 6.0 | 5.7 | 3.8 |

Slot 3 sits between the two most-bent seams, so it inherits both excursions.

`normalise()` fits each crop into a fixed 32x32 box, scaling by the longest
side rather than stretching to fill, so glyph proportions survive (a '1' stays
narrow instead of being smeared to the width of a '0'). The CLI emits
normalised crops.

A second bug surfaced while measuring this: every crop was exactly 50px tall,
i.e. the full image height, because the grayscale crop used a fixed cutoff of
200 while the background itself reaches 208-220. The crop box is now taken from
the binary mask, which already encodes the ink/background decision; heights now
vary properly (32.8-44.1px).

### Quality varies by position too

The same geometry means the middle characters are harder, and the end ones
easy:

| Position | 0 | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- | --- |
| Single-component crops | 90% | 64% | 67% | 64% | 67% | 93% |

Widening the search radius does not help (mean ink crossed 6.28 at radius 10
vs 6.23 at radius 18) -- there is simply no low-ink path between the middle
glyphs, because they genuinely overlap. This is the fusion limit, not a tuning
problem.

### Re-stitching into an evenly spaced image

`stitch()` normalises every character to the same 32x32 box and lays them out
with a blank gap between, producing a 48x248 image. This removes the
size disparity described above -- no character looks zoomed -- and, because the
characters are placed rather than merely cut, glyphs that touched in the
original are now visibly separate. The fusion cannot be undone *within* a
glyph, but it no longer runs across the boundary between them.

Scaling uses the longest side rather than stretching to fill, so proportions
survive: a '1' stays narrow instead of being smeared to the width of a '0'.

**Normalise contrast per character, anchored on the mask.** The illumination
gradient otherwise survives into the crops: the median level behind a character
climbs from 64 at position 0 to 130 at position 5 (a 71-level spread), with
per-image variance of +/-25 to +/-58 on top, so a CNN would see the same digit
at a different contrast depending on where it sat.

The black and white reference levels come from the binary mask -- the median of
the pixels it calls ink, and the median of those it calls background. An
obvious-looking 5th-95th percentile stretch of the crop was tried first and
made things *worse* (spread rose to 86.7, variance roughly doubled), because a
crop is mostly background so its percentile range spans mostly noise and gets
amplified. Anchoring on the mask cuts the spread to 18.5.

Verified on 40 unseen captchas: every output exactly 48x248, every cell exactly
32px, contrast spread 29.1 against 71.0 raw.

**Segment the grayscale, not the binary.** `split_grayscale` computes the
seams from the binary image (thresholding is only needed to *locate* the
characters) and applies them to the cleaned grayscale. Characters that come
out fragmented in a binary crop stay intact in the grayscale one, because
binarisation is what removes the faint pixels connecting a stroke. This is
visibly the better input and matches what the model plan already calls for.

## 6. Running it

Batch, straight from the MinIO bucket to a folder of stitched images:

```bash
uv run python app.py                    # default limit of 10
uv run python app.py --all              # every object in the bucket
uv run python app.py --limit 50
uv run python app.py --out some/folder
```

Roughly 0.13s per captcha (100 in 13.5s), so the full 1364-object bucket takes
about 3 minutes. Every output is 48x248.

Single image, also writing the six individual character crops:

```bash
uv run python segment.py <raw_captcha> <output_dir>
```

## 7. Relationship to the model plan

`docs/captcha_finetune_strategy.md` proposes training the CNN on grayscale
crops rather than binary masks. That still holds, and this strategy serves it:
steps 1-2 (lattice and red-line removal) produce a *clean grayscale* image and
are the valuable part for a CNN. Steps 3-4 (thresholding, border strip) are
only needed when a binary image is the goal — for example for classical OCR or
for human inspection of the intermediate output.
