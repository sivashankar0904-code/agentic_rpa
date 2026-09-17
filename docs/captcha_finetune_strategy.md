# Captcha Model Fine-Tune Strategy

Based on reviewing the 10 images in `preprocessed/` (produced by the current
`preprocess.py` + `app.py` pipeline) and the CNN training pipeline that
existed before the `f6a119b` "restart from scratch" commit
(`03bd982: feat: add captcha CNN training pipeline with labeling UI and
model versioning`, since deleted from the working tree but present in git
history).

## 1. What the current preprocessed output looks like

All 10 sampled images show the same failure mode:

- **Characters are fused together.** Adjacent glyphs touch or overlap into
  one connected blob in almost every sample (e.g. `579605`, `921550`,
  `497f5?`). Individual character boundaries are frequently unrecoverable
  from the binary mask alone.
- **Some samples are over-thresholded into solid blobs with white "holes"**
  punched through the interior, instead of clean stroke outlines (most
  visible in `00d494e8-d0aa-4c7d-ad58-9f9b56dccb92.png`).
- **Speckle survives at the frame edges** — small dashes/dots near corners
  in most samples, meaning `remove_border`/`remove_small_noise` aren't
  fully catching it.
- **Stroke thickness varies a lot across samples.** Some captchas render
  with a much heavier/darker source font than others. A single fixed
  `threshold` (65) and fixed dilation `ksize` (2) can't handle that
  variance uniformly — thin-stroke images need thickening, but the same
  settings applied to already-thick images make fusion worse.

Net effect: the current `dilate_characters` → `erode_characters` pair (both
`ksize=2, iterations=1`) is close to a no-op on already-good images, but
does nothing to *fix* the over-thresholded/fused ones — dilation actively
worsens fusion on the thick-stroke samples before erosion (same kernel
size) only partially reverses it.

## 2. Why this matters for the model

The recovered `CaptchaCNN` (`app/core/ml/captcha_cnn.py` in `03bd982`) is a
**shared conv backbone + 6 independent per-position classifier heads**,
fixed at `CAPTCHA_LENGTH = 6`, trained on grayscale 50×200 crops (not the
binary mask). It doesn't explicitly segment characters — each head learns
to read "whatever is in column-range N" — but it still implicitly relies on
the input being visually clean enough that six distinguishable glyphs exist
in the image. Feeding it inputs where two characters have merged into one
blob (as several samples above show) removes information the model has no
way to recover: it would have to learn to invent a character boundary that
literally isn't there in the input.

This means **preprocessing quality is a hard ceiling on model accuracy**
before any training/fine-tuning starts, and it should be fixed first.

## 3. Recommended fine-tune strategy

### Phase 0 — Fix preprocessing before touching the model
Don't spend training runs compensating for bad inputs.

1. **Make `binarize()`'s threshold adaptive per-image, not global-fixed.**
   Try per-image Otsu restricted to a masked region (exclude the known
   hatch-pattern intensity band), or a percentile-based threshold (e.g.
   pick the threshold that keeps ~X% of pixels black, calibrated against a
   labeled sample set) instead of a single constant `65` for every image.
2. **Make `dilate_characters`/`erode_characters` conditional, not fixed.**
   Measure stroke width (e.g. via distance transform on the binary mask)
   before deciding whether to erode or dilate, and by how much — rather
   than always applying both with the same `ksize=2`.
3. **Tighten `remove_border`/`remove_small_noise`** to fully clear edge
   speckle — increase `thickness` slightly or add a connected-component
   filter that drops components below a minimum area, rather than relying
   only on morphological opening.
4. **Re-generate the preprocessed batch and manually verify** a larger
   sample (50-100 images, not 10) shows clean, separated characters before
   moving to Phase 1. This is the actual blocker right now — don't proceed
   past it on the current output.

### Phase 1 — Establish a labeled dataset
The old schema (`captcha_labels` table: `object_name`, `label`,
`is_solved`, `predicted_label`, `accuracy`) is a reasonable design to
resurrect as-is:

1. Rebuild (or restore from git history) a minimal labeling UI/CLI that
   pairs each MinIO object key with a ground-truth 6-character label.
2. Target at least a few hundred labeled samples before training — the old
   `DEFAULT_EPOCHS = 60` config assumes a real dataset, not 10 images.
3. Keep raw images as the training input (resized grayscale, per
   `_CaptchaDataset` in the old `train.py`), **not** the binary
   preprocessed output — feeding the model the fixed-threshold binary mask
   throws away grayscale information the conv backbone could otherwise use
   to disambiguate fused strokes. Preprocessing should inform *cropping/
   normalization* (e.g. red-line removal, background dot removal, resize),
   not necessarily hard binarization, if going into a CNN rather than
   classical OCR.

### Phase 2 — Baseline training run, not fine-tuning
There is no existing trained checkpoint anywhere in git history or MinIO
(the training pipeline was deleted before any model version was recorded,
based on `model_versions`/`captcha_model_store` never having stored
weights this repo can find). So "fine-tune" is actually **train from
scratch** at this point:

1. Restore `CaptchaCNN` + `train_captcha_model` from `03bd982` (or
   reimplement equivalently) as the starting architecture — it's a
   reasonable, already-reasoned-through design (per-position heads sized
   for the confirmed 6-character GST captcha format).
2. Run a baseline training pass on the Phase 1 dataset with the existing
   hyperparameters (`epochs=60, batch_size=32, lr=1e-3`) and log to MLflow
   as originally designed, so results are comparable across iterations.
3. Track **per-character accuracy** (already computed in the old loop) as
   the primary metric, plus **whole-captcha accuracy** (all 6 correct) as
   the metric that actually matters for unblocking the RPA flow.

### Phase 3 — Iterate
Once a baseline exists, real fine-tuning options in priority order:

1. **Data augmentation** matched to observed real-world variance (stroke
   thickness, slight rotation/skew, residual dot-pattern noise) rather than
   generic augmentation — the captchas have a specific, consistent visual
   style worth targeting directly.
2. **Active-learn the labeled set**: run the current model against
   unlabeled captchas, have a human correct low-confidence/wrong
   predictions (the `predicted_label`/`accuracy` columns in the old schema
   were clearly designed for exactly this loop), and retrain periodically
   via `training_schedule`.
3. Only after data-side improvements plateau, consider architecture changes
   (e.g. a CTC-based sequence model instead of fixed 6-head classification,
   if character count or segmentation ever turns out to be unreliable).

## Immediate next step
Fix Phase 0 preprocessing (adaptive threshold + conditional
dilate/erode + better edge-speckle cleanup) and re-run `app.py` against a
larger sample before deciding anything about the model itself.
