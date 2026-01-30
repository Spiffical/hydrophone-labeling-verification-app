# Oceans 3.0 Unified JSON Schema

Universal JSON format for storing model predictions, expert verifications,
and manual labels of Ocean Networks Canada (ONC) hydrophone data.

---

## Design principles

| Principle | How it is achieved |
|---|---|
| **No redundancy** | Device/location/sample-rate are looked up via `data_source_id`, not repeated per item. Manual labels are stored once in `items[].annotations`. |
| **Full provenance** | Model weights hash, training data reference, pipeline commit, audio source, spectrogram generation parameters, and calibration status are all explicit. |
| **Audit trail** | Every verification round is preserved with reviewer identity, affiliation, per-label decisions, confidence, and notes. |
| **Reproducibility** | Spectrogram config includes all FFT parameters needed to regenerate from audio. Audio source records whether data came from ONC API or local files. |
| **Threshold-agnostic** | Raw model scores (0-1) are stored; thresholds are applied at verification time and recorded per decision. |
| **Flat-friendly** | Can be exploded into `predictions.csv` and `verifications.csv` by joining items with root-level metadata. |

---

## Profiles (what files can look like)

We support two compatible profiles:

1) **predictions.json** (full schema)  
   - Includes `model_outputs` and optional `verifications`.  
   - Used for inference + expert review.

2) **labels.json** (manual labels only)  
   - Includes `items[].annotations` (labels + provenance).  
   - Omits `model`, `pipeline`, `spectrogram_config`, `model_outputs`, `verifications`.  
   - Designed for direct ingestion into O3.0 by mapping annotations to label decisions.
   - **Legacy mapping format** (`{ "file_id": ["Label"] }`) is deprecated but may be accepted for migration.

---

## Structure overview

### Full predictions profile
```
{
  "schema_version": "2.0",
  "created_at":  "ISO-8601",
  "updated_at":  "ISO-8601",
  "task_type":   "whale_detection | anomaly_detection | classification",

  "model":              { ... },   // who made the predictions
  "data_sources":       [ ... ],   // where the audio came from
  "spectrogram_config": { ... },   // how spectrograms were generated
  "pipeline":           { ... },   // inference pipeline version

  "items": [                       // one entry per spectrogram / clip
    {
      "item_id":          "...",
      "data_source_id":   "...",   // FK → data_sources[].data_source_id
      "audio_start_time": "ISO-8601",
      "audio_end_time":   "ISO-8601",
      "segment_index":    0,
      "model_outputs":    [ ... ], // raw scores per class
      "verifications":    [ ... ], // expert review rounds
      "paths":            { ... }  // relative file references
    }
  ]
}
```

### Labels-only profile (labels.json)

```
{
  "schema_version": "2.0",
  "created_at":  "ISO-8601",
  "updated_at":  "ISO-8601",
  "task_type":   "classification",

  "data_sources": [ ... ],         // optional (often a single entry)

  "items": [
    {
      "item_id": "...",
      "data_source_id": "...",     // optional if only one data source
      "annotations": { ... }       // manual labels + provenance
    }
  ]
}
```

### Why `data_source_id` instead of repeating fields

Each item references a `data_source` by ID. The data source carries device
code, location, coordinates, depth, sample rate, channel, calibration status,
and deployment info. This avoids repeating ~10 fields on every item and keeps
mixed-device batches in a single file.

---

## Field reference

### Root

**Required fields by profile**

- **predictions.json**: `schema_version`, `created_at`, `task_type`, `data_sources`, `items`
- **labels.json**: `schema_version`, `created_at`, `task_type`, `items`

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | yes | Always `"2.0"`. |
| `created_at` | date-time | yes | When this file was first written. |
| `updated_at` | date-time | no | Last modification (e.g., after adding verifications). |
| `task_type` | enum | yes | `whale_detection`, `anomaly_detection`, or `classification`. |

### `model`

| Field | Type | Required | Description |
|---|---|---|---|
| `model_id` | string | yes | SHA-256 hash of model weights, e.g. `"sha256-a3f2b9c8d1e7"`. See [Model ID computation](#model-id-computation). |
| `model_version` | string | no | Human-readable version tag. |
| `architecture` | string | no | e.g. `"resnet18"`, `"masked_autoencoder"`. |
| `checkpoint_path` | string | no | Path to checkpoint file used for inference. |
| `checkpoint_url` | string (uri) | no | URL to download the trained model weights (e.g. cloud storage, model registry). |
| `trained_at` | date-time | no | When training completed. |
| `wandb_run_id` | string | no | Weights & Biases experiment ID. |
| `training_dataset_id` | string | no | Identifier for the training dataset. |
| `training_dataset_version` | string | no | Version of the training dataset. |
| `training_dataset_url` | string (uri) | no | URL to access or download the training dataset. |
| `training_data_time_range` | string | no | ISO-8601 interval, e.g. `"2019-01-01T00:00:00Z/2020-01-01T00:00:00Z"`. |
| `input_shape` | array of int | no | Expected input dimensions, e.g. `[96, 96]`. |
| `output_classes` | array of string | no | Taxonomy paths the model can predict. |

### `data_sources[]`

Each entry describes one hydrophone deployment. Items reference these via `data_source_id`.

| Field | Type | Required | Description |
|---|---|---|---|
| `data_source_id` | string | yes | Unique key within this file. |
| `device_code` | string | yes | ONC device code, e.g. `"ICLISTENHF1353"`. |
| `deployment_id` | string | no | ONC deployment identifier. |
| `location_name` | string | no | Human-readable location. |
| `site_code` | string | no | ONC site code, e.g. `"CLAYO"`. |
| `latitude` | number | no | Decimal degrees. |
| `longitude` | number | no | Decimal degrees. |
| `depth_m` | number | no | Deployment depth in metres. |
| `channel` | string | no | Hydrophone channel, e.g. `"H"`. |
| `sample_rate` | number | no | Sampling rate in Hz. |
| `is_calibrated` | boolean | no | `true` if data is calibrated to absolute SPL (dB re 1 uPa). `false` means dB re full scale. From ONC MAT metadata `isCalibrated`. |
| `calibration_reference` | string | no | e.g. `"dB re 1 uPa RMS"` or `"dB re full scale"`. |
| `date_from` | date-time | no | Start of audio time range. |
| `date_to` | date-time | no | End of audio time range. |

### `spectrogram_config`

Parameters needed to reproduce the spectrograms. Present even for ONC-downloaded spectrograms (to document what ONC generated).

| Field | Type | Required | Description |
|---|---|---|---|
| `nfft` | integer | no | FFT length in samples. |
| `window_function` | string | no | e.g. `"hann"`, `"hamming"`. ONC uses Hanning with 50% overlap. |
| `window_duration_sec` | number | no | FFT window duration in seconds. |
| `hop_length` | integer | no | Hop length in samples (alternative to `overlap`). |
| `overlap` | number | no | Fractional overlap (0-1), e.g. `0.9`. |
| `frequency_limits` | `{min, max}` | no | Frequency range in Hz. |
| `color_limits` | `{min, max}` | no | dB range for colour mapping. |
| `colormap` | string | no | e.g. `"viridis"`. |
| `y_axis_scale` | enum | no | `"linear"` or `"log"`. |
| `context_duration_sec` | number | no | Total clip duration in seconds (e.g. 40). |
| `segment_overlap` | number | no | Overlap between consecutive segments (0-1). |
| `crop_size` | integer | no | Pixel dimension if cropped for model input. |
| `source` | object | no | See below. |

#### `spectrogram_config.source`

Describes where the spectrogram images/matrices came from.

| Field | Type | Description |
|---|---|---|
| `type` | enum | `"computed"` (generated locally from audio) or `"onc_download"` (fetched from ONC servers). |
| `generator` | string | Software that created the spectrogram, e.g. `"SpectrogramGenerator"`, `"ONC Data API"`. |
| `backend` | string or null | Computation backend, e.g. `"scipy"`, `"torch"`, `null`. |
| `onc_data_product_code` | string | ONC data product code, e.g. `"SPSD"` (spectral data), `"SPGR"` (spectrogram PNG). Only for `onc_download`. |
| `onc_data_product_options` | object | ONC API request parameters (resolution, etc.). Only for `onc_download`. |

#### `spectrogram_config.audio_source`

Describes how the source audio was obtained. Only relevant when `source.type` is `"computed"`.

| Field | Type | Description |
|---|---|---|
| `type` | enum | `"onc_download"` or `"local"`. |
| `onc_data_product_code` | string | e.g. `"AD"` (audio data). Only for `onc_download`. |
| `format` | string | e.g. `"wav"`, `"flac"`. |

### `pipeline`

| Field | Type | Required | Description |
|---|---|---|---|
| `pipeline_version` | string | no | Semantic version of the inference pipeline. |
| `pipeline_commit` | string | no | Git commit hash. |
| `pipeline_repo` | string | no | Repository URL or name. |

### `items[]`

Each item is one display unit (one spectrogram / audio clip).

| Field | Type | Required | Description |
|---|---|---|---|
| `item_id` | string | yes | Unique within this file. Convention: `{device_code}_{ISO-timestamp}_seg{NNN}`. |
| `data_source_id` | string | yes* | FK to `data_sources[].data_source_id`. Optional in labels.json when only one data source exists. |
| `audio_start_time` | date-time | yes | Absolute start time of this clip. |
| `audio_end_time` | date-time | yes | Absolute end time of this clip. |
| `segment_index` | integer | no | Zero-based index when a longer recording is split into segments. |
| `model_outputs` | array | yes | See below. |
| `verifications` | array | no | See below. Defaults to `[]`. |
| `paths` | object | no | See below. |


> **Note:** `data_source_id` is required whenever multiple `data_sources` are present or when using the predictions profile.

> **Device, location, sample rate** are looked up from `data_sources` via `data_source_id`. No separate fields needed.

#### `items[].model_outputs[]`

Raw model scores. One entry per class the model evaluated.

| Field | Type | Required | Description |
|---|---|---|---|
| `class_hierarchy` | string | yes | Taxonomy path, e.g. `"Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"`. |
| `class_id` | string | no | Short stable identifier, e.g. `"anthro_vessel"`. |
| `score` | number (0-1) | yes | Raw model confidence. Not thresholded. |

#### `items[].annotations` (labels.json)

Manual labels and provenance.

| Field | Type | Required | Description |
|---|---|---|---|
| `labels` | array of string | yes | Taxonomy paths. |
| `annotated_by` | string | no | Reviewer identifier. |
| `annotated_at` | date-time | no | When labels were saved. |
| `verified` | boolean | no | Optional manual verification flag. |
| `notes` | string | no | Free-text comments. |

#### `items[].verifications[]`

Each entry is one verification round. The last entry is the current ground truth. Append-only: never delete previous rounds.

| Field | Type | Required | Description |
|---|---|---|---|
| `verified_at` | date-time | yes | When this review was completed. |
| `verified_by` | string | yes | Reviewer identifier (email or username). |
| `reviewer_affiliation` | string | no | e.g. `"ONC"`, `"UVic"`. |
| `verification_round` | integer | yes | 1-based round number. |
| `verification_status` | enum | no | `"verified"`, `"rejected"`, or `"uncertain"`. |
| `label_decisions` | array | yes | Per-label decisions. **This is the single source of truth for what was accepted/rejected/added.** See below. |
| `confidence` | enum or null | no | `"high"`, `"medium"`, `"low"`, or `null`. |
| `notes` | string | no | Free-text reviewer comments. |
| `label_source` | enum | no | `"expert"`, `"auto"`, or `"consensus"`. |
| `taxonomy_version` | string | no | Version of the taxonomy used during review. |

#### `items[].verifications[].label_decisions[]`

| Field | Type | Required | Description |
|---|---|---|---|
| `label` | string | yes | Taxonomy path. |
| `decision` | enum | yes | `"accepted"` (model-suggested, confirmed), `"rejected"` (model-suggested, removed), or `"added"` (not suggested by model, added by reviewer). |
| `threshold_used` | number | yes | Score threshold the reviewer applied when making this decision. |

#### `items[].paths`

Relative paths from the directory containing this JSON file.

| Field | Type | Description |
|---|---|---|
| `spectrogram_mat_path` | string | MAT file with spectral data. |
| `spectrogram_png_path` | string | Pre-rendered spectrogram image. |
| `audio_path` | string | Segmented audio clip for this item. |

---

## Model ID computation

The `model_id` is a deterministic SHA-256 hash of the model weights, ensuring
the same weights always produce the same ID regardless of machine or time.

```python
import hashlib, io, torch

def compute_model_hash(state_dict: dict, length: int = 12) -> str:
    buffer = io.BytesIO()
    sorted_dict = {k: state_dict[k] for k in sorted(state_dict.keys())}
    torch.save(sorted_dict, buffer)
    buffer.seek(0)
    return f"sha256-{hashlib.sha256(buffer.read()).hexdigest()[:length]}"
```

Example: `"sha256-a3f2b9c8d1e7"` (12 hex chars, ~281 trillion combinations).

---

## CSV flattening

- **predictions.csv** = explode `items[].model_outputs[]`, join with root-level
  `model.*`, `pipeline.*`, and the matching `data_sources[]` entry.
- **verifications.csv** = explode `items[].verifications[].label_decisions[]`,
  join with root-level metadata and the matching `data_sources[]` entry.

---

## Labels-only example (labels.json)

```json
{
  "schema_version": "2.0",
  "created_at": "2026-01-29T21:12:33Z",
  "updated_at": "2026-01-29T21:12:33Z",
  "task_type": "classification",
  "items": [
    {
      "item_id": "ICLISTENHF1951_20241231T235516.996Z_seg001",
      "annotations": {
        "labels": ["Instrumentation"],
        "annotated_by": "sbialek",
        "annotated_at": "2026-01-29T21:10:00Z",
        "notes": ""
      }
    }
  ]
}
```

**O3 ingestion mapping (labels.json → verifications):**
- `annotations.labels` → `label_decisions[].label` with `decision="added"` and `threshold_used=null`
- `annotated_at` → `verified_at`
- `annotated_by` → `verified_by`
- `notes` → `notes`

---

## Complete example (predictions.json)

```json
{
  "schema_version": "2.0",
  "created_at": "2026-01-27T18:20:00Z",
  "updated_at": "2026-01-27T20:10:00Z",
  "task_type": "anomaly_detection",

  "model": {
    "model_id": "sha256-a3f2b9c8d1e7",
    "model_version": "anomaly-mae-v1.2.0",
    "architecture": "masked_autoencoder",
    "checkpoint_path": "trained-models/anomaly-mae/best.pt",
    "trained_at": "2026-01-20T02:10:00Z",
    "training_dataset_id": "wd1.0_ov0.9",
    "training_dataset_version": "1.0",
    "training_data_time_range": "2019-01-01T00:00:00Z/2020-01-01T00:00:00Z",
    "wandb_run_id": "o3-anomaly-2026-01-20",
    "input_shape": [96, 96],
    "output_classes": [
      "Anthropophony > Vessel",
      "Instrumentation > Malfunction > Data gap",
      "Other > Unknown sound of interest"
    ]
  },

  "data_sources": [
    {
      "data_source_id": "ICLISTENHF1353_CLAYO_2019",
      "device_code": "ICLISTENHF1353",
      "deployment_id": "ICLISTENHF1353-2019",
      "location_name": "Clayoquot Slope",
      "site_code": "CLAYO",
      "latitude": 48.894,
      "longitude": -126.228,
      "depth_m": 125.0,
      "channel": "H",
      "sample_rate": 64000,
      "is_calibrated": true,
      "calibration_reference": "dB re 1 uPa RMS",
      "date_from": "2019-06-30T00:04:58Z",
      "date_to": "2019-06-30T01:04:58Z"
    },
    {
      "data_source_id": "ICLISTENHF1951_BARK_2019",
      "device_code": "ICLISTENHF1951",
      "deployment_id": "ICLISTENHF1951-2019",
      "location_name": "Barkley Canyon",
      "site_code": "BARK",
      "latitude": 48.32,
      "longitude": -126.06,
      "depth_m": 400.0,
      "channel": "H",
      "sample_rate": 64000,
      "is_calibrated": true,
      "calibration_reference": "dB re 1 uPa RMS",
      "date_from": "2019-06-30T01:04:58Z",
      "date_to": "2019-06-30T02:04:58Z"
    }
  ],

  "spectrogram_config": {
    "nfft": 64000,
    "window_function": "hann",
    "window_duration_sec": 1.0,
    "overlap": 0.9,
    "frequency_limits": { "min": 5, "max": 100 },
    "color_limits": { "min": -60, "max": 0 },
    "colormap": "viridis",
    "y_axis_scale": "linear",
    "context_duration_sec": 40.0,
    "segment_overlap": 0.5,
    "crop_size": 96,
    "source": {
      "type": "computed",
      "generator": "SpectrogramGenerator",
      "backend": "scipy"
    },
    "audio_source": {
      "type": "onc_download",
      "onc_data_product_code": "AD",
      "format": "wav"
    }
  },

  "pipeline": {
    "pipeline_version": "v0.7.2",
    "pipeline_commit": "9c1a6d2",
    "pipeline_repo": "labeling-verification-app"
  },

  "items": [
    {
      "item_id": "ICLISTENHF1353_20190630T000458.000Z_seg000",
      "data_source_id": "ICLISTENHF1353_CLAYO_2019",
      "audio_start_time": "2019-06-30T00:04:58Z",
      "audio_end_time": "2019-06-30T00:05:38Z",
      "segment_index": 0,
      "model_outputs": [
        { "class_hierarchy": "Anthropophony > Vessel", "class_id": "anthro_vessel", "score": 0.12 },
        { "class_hierarchy": "Instrumentation > Malfunction > Data gap", "class_id": "instr_data_gap", "score": 0.67 },
        { "class_hierarchy": "Other > Unknown sound of interest", "class_id": "other_unknown", "score": 0.91 }
      ],
      "verifications": [
        {
          "verified_at": "2026-01-27T20:05:00Z",
          "verified_by": "expert1@onc.ca",
          "reviewer_affiliation": "ONC",
          "verification_round": 1,
          "verification_status": "verified",
          "label_decisions": [
            { "label": "Anthropophony > Vessel", "decision": "rejected", "threshold_used": 0.5 },
            { "label": "Instrumentation > Malfunction > Data gap", "decision": "accepted", "threshold_used": 0.5 },
            { "label": "Other > Unknown sound of interest", "decision": "accepted", "threshold_used": 0.5 }
          ],
          "confidence": "high",
          "notes": "Clear data gap and unusual tonal feature.",
          "label_source": "expert",
          "taxonomy_version": "o3-taxonomy-2026-01"
        }
      ],
      "paths": {
        "spectrogram_mat_path": "2019-06-30/ICLISTENHF1353/spectrograms/seg000.mat",
        "spectrogram_png_path": "2019-06-30/ICLISTENHF1353/spectrograms/seg000.png",
        "audio_path": "2019-06-30/ICLISTENHF1353/audio/seg000.wav"
      }
    },
    {
      "item_id": "ICLISTENHF1951_20190630T010458.000Z_seg000",
      "data_source_id": "ICLISTENHF1951_BARK_2019",
      "audio_start_time": "2019-06-30T01:04:58Z",
      "audio_end_time": "2019-06-30T01:05:38Z",
      "segment_index": 0,
      "model_outputs": [
        { "class_hierarchy": "Anthropophony > Vessel", "class_id": "anthro_vessel", "score": 0.44 },
        { "class_hierarchy": "Instrumentation > Malfunction > Data gap", "class_id": "instr_data_gap", "score": 0.02 },
        { "class_hierarchy": "Other > Unknown sound of interest", "class_id": "other_unknown", "score": 0.11 }
      ],
      "verifications": [],
      "paths": {
        "spectrogram_mat_path": "2019-06-30/ICLISTENHF1951/spectrograms/seg000.mat",
        "spectrogram_png_path": "2019-06-30/ICLISTENHF1951/spectrograms/seg000.png",
        "audio_path": "2019-06-30/ICLISTENHF1951/audio/seg000.wav"
      }
    }
  ]
}
```

---

## JSON Schema (draft 2020-12)

**Note:** This schema block describes the full predictions profile.  
For labels.json, accept a subset that includes `schema_version`, `created_at`,
`task_type`, `items[]`, and `items[].annotations`, while allowing omission of
`model`, `pipeline`, `spectrogram_config`, `model_outputs`, and `verifications`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://oceannetworks.ca/schemas/o3_predictions_v2.json",
  "title": "O3 Predictions Schema v2.0",
  "type": "object",
  "required": ["schema_version", "created_at", "task_type", "data_sources", "items"],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "type": "string", "const": "2.0" },
    "created_at": { "type": "string", "format": "date-time" },
    "updated_at": { "type": "string", "format": "date-time" },
    "task_type": {
      "type": "string",
      "enum": ["whale_detection", "anomaly_detection", "classification"]
    },
    "model": {
      "type": "object",
      "required": ["model_id"],
      "additionalProperties": false,
      "properties": {
        "model_id": { "type": "string" },
        "model_version": { "type": "string" },
        "architecture": { "type": "string" },
        "checkpoint_path": { "type": "string" },
        "checkpoint_url": { "type": "string", "format": "uri" },
        "trained_at": { "type": "string", "format": "date-time" },
        "wandb_run_id": { "type": "string" },
        "training_dataset_id": { "type": "string" },
        "training_dataset_version": { "type": "string" },
        "training_dataset_url": { "type": "string", "format": "uri" },
        "training_data_time_range": { "type": "string" },
        "input_shape": {
          "type": "array",
          "items": { "type": "integer" }
        },
        "output_classes": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },
    "data_sources": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/data_source" }
    },
    "spectrogram_config": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "nfft": { "type": "integer" },
        "window_function": { "type": "string" },
        "window_duration_sec": { "type": "number" },
        "hop_length": { "type": "integer" },
        "overlap": { "type": "number", "minimum": 0, "maximum": 1 },
        "frequency_limits": {
          "type": "object",
          "properties": {
            "min": { "type": "number" },
            "max": { "type": "number" }
          },
          "required": ["min", "max"],
          "additionalProperties": false
        },
        "color_limits": {
          "type": "object",
          "properties": {
            "min": { "type": "number" },
            "max": { "type": "number" }
          },
          "additionalProperties": false
        },
        "colormap": { "type": "string" },
        "y_axis_scale": { "type": "string", "enum": ["linear", "log"] },
        "context_duration_sec": { "type": "number" },
        "segment_overlap": { "type": "number" },
        "crop_size": { "type": "integer" },
        "source": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "type": { "type": "string", "enum": ["computed", "onc_download"] },
            "generator": { "type": "string" },
            "backend": { "type": ["string", "null"] },
            "onc_data_product_code": { "type": "string" },
            "onc_data_product_options": { "type": "object" }
          }
        },
        "audio_source": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "type": { "type": "string", "enum": ["onc_download", "local"] },
            "onc_data_product_code": { "type": "string" },
            "format": { "type": "string" }
          }
        }
      }
    },
    "pipeline": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "pipeline_version": { "type": "string" },
        "pipeline_commit": { "type": "string" },
        "pipeline_repo": { "type": "string" }
      }
    },
    "items": {
      "type": "array",
      "items": { "$ref": "#/$defs/item" }
    }
  },
  "$defs": {
    "data_source": {
      "type": "object",
      "required": ["data_source_id", "device_code"],
      "additionalProperties": false,
      "properties": {
        "data_source_id": { "type": "string" },
        "device_code": { "type": "string" },
        "deployment_id": { "type": "string" },
        "location_name": { "type": "string" },
        "site_code": { "type": "string" },
        "latitude": { "type": "number" },
        "longitude": { "type": "number" },
        "depth_m": { "type": "number" },
        "channel": { "type": "string" },
        "sample_rate": { "type": "number" },
        "is_calibrated": { "type": "boolean" },
        "calibration_reference": { "type": "string" },
        "date_from": { "type": "string", "format": "date-time" },
        "date_to": { "type": "string", "format": "date-time" }
      }
    },
    "item": {
      "type": "object",
      "required": ["item_id", "data_source_id", "audio_start_time", "audio_end_time", "model_outputs"],
      "additionalProperties": false,
      "properties": {
        "item_id": { "type": "string" },
        "data_source_id": { "type": "string" },
        "audio_start_time": { "type": "string", "format": "date-time" },
        "audio_end_time": { "type": "string", "format": "date-time" },
        "segment_index": { "type": "integer", "minimum": 0 },
        "model_outputs": {
          "type": "array",
          "items": { "$ref": "#/$defs/model_output" }
        },
        "verifications": {
          "type": "array",
          "items": { "$ref": "#/$defs/verification" }
        },
        "paths": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "spectrogram_mat_path": { "type": "string" },
            "spectrogram_png_path": { "type": "string" },
            "audio_path": { "type": "string" }
          }
        }
      }
    },
    "model_output": {
      "type": "object",
      "required": ["class_hierarchy", "score"],
      "additionalProperties": false,
      "properties": {
        "class_hierarchy": { "type": "string" },
        "class_id": { "type": "string" },
        "score": { "type": "number", "minimum": 0, "maximum": 1 }
      }
    },
    "verification": {
      "type": "object",
      "required": ["verified_at", "verified_by", "verification_round", "label_decisions"],
      "additionalProperties": false,
      "properties": {
        "verified_at": { "type": "string", "format": "date-time" },
        "verified_by": { "type": "string" },
        "reviewer_affiliation": { "type": "string" },
        "verification_round": { "type": "integer", "minimum": 1 },
        "verification_status": {
          "type": "string",
          "enum": ["verified", "rejected", "uncertain"]
        },
        "label_decisions": {
          "type": "array",
          "items": { "$ref": "#/$defs/label_decision" }
        },
        "confidence": {
          "type": ["string", "null"],
          "enum": ["high", "medium", "low", null]
        },
        "notes": { "type": "string" },
        "label_source": {
          "type": "string",
          "enum": ["expert", "auto", "consensus"]
        },
        "taxonomy_version": { "type": "string" }
      }
    },
    "label_decision": {
      "type": "object",
      "required": ["label", "decision", "threshold_used"],
      "additionalProperties": false,
      "properties": {
        "label": { "type": "string" },
        "decision": {
          "type": "string",
          "enum": ["accepted", "rejected", "added"]
        },
        "threshold_used": { "type": "number", "minimum": 0, "maximum": 1 }
      }
    }
  }
}
```
