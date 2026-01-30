# Unified Predictions JSON Format Specification

> **Note:** This document is supplementary. The canonical schema is
> [`OCEANS3_JSON_SCHEMA.md`](../OCEANS3_JSON_SCHEMA.md).

## Overview
This document defines a standardized format for storing ML model predictions and expert verifications that works across different acoustic analysis tasks (whale detection, anomaly detection, etc.) while maintaining flexibility for different data granularities.

Both **model prediction verification** and **manual labeling** produce the same
output structure. Human decisions always go into `items[].verifications[].label_decisions[]`.

## Core Principles
1. **Store raw model outputs**, not thresholded predictions
2. **Use hierarchical labels** from the taxonomy
3. **Support multiple verification rounds** with full audit trail
4. **Avoid data duplication** - reference files, don't embed them
5. **Flexible granularity** - support both full-clip and windowed predictions
6. **Single output format** - no conversion needed between label and verify modes

---

## Format Structure

###  Root Level
```json
{
  "schema_version": "2.0",
  "created_at": "2026-01-16T23:00:00Z",
  "updated_at": "2026-01-16T23:30:00Z",
  "task_type": "whale_detection" | "anomaly_detection" | "classification",

  "model": { ... },              // optional — present for model predictions
  "data_sources": [ ... ],       // optional — hydrophone deployments
  "spectrogram_config": { ... }, // optional — how spectrograms were generated
  "pipeline": { ... },           // optional — inference pipeline version

  "items": [ ... ]
}
```

### Model Metadata
```json
"model": {
  "model_id": "sha256-a3f2b9c8d1e7",  // SHA256 hash of model weights (see below)
  "architecture": "resnet18",
  "checkpoint_path": "path/to/checkpoint.pt",
  "trained_at": "2026-01-01T00:00:00Z",
  "wandb_run_id": "abc123",
  "input_shape": [96, 96],  // expected input dimensions
  "output_classes": [
    "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"
  ]
}
```

#### Model ID: Deterministic Hash of Weights

The `model_id` is a **unique identifier** computed from the model's weights using SHA256 hashing. This provides:
- **Reproducibility**: Same weights always produce same ID
- **Verification**: Can verify predictions came from specific model version
- **Tracking**: Link predictions back to exact model weights used

**Implementation** (from `whale-call-analysis/src/utils/model_utils.py`):
```python
import hashlib
import io
import torch

def compute_model_hash(state_dict: dict, length: int = 12) -> str:
    """Compute SHA256 hash of model weights for unique identification.

    Args:
        state_dict: Model state dictionary containing weights
        length: Number of characters to include in hash (default: 12)

    Returns:
        String in format 'sha256-{first N chars of hash}'
    """
    # Serialize weights deterministically to bytes
    buffer = io.BytesIO()
    # Sort keys for deterministic ordering
    sorted_dict = {k: state_dict[k] for k in sorted(state_dict.keys())}
    torch.save(sorted_dict, buffer)
    buffer.seek(0)

    # Compute SHA256 hash
    hasher = hashlib.sha256()
    hasher.update(buffer.read())
    full_hash = hasher.hexdigest()

    return f"sha256-{full_hash[:length]}"
```

**Usage:**
```python
# When saving checkpoint during training
model_id = compute_model_hash(model.state_dict())
checkpoint = {
    'model_state': model.state_dict(),
    'model_id': model_id,
    'architecture': 'resnet18',
    'trained_at': datetime.now(timezone.utc).isoformat(),
    ...
}
torch.save(checkpoint, 'best.pt')

# When running inference
checkpoint = torch.load('best.pt')
model.load_state_dict(checkpoint['model_state'])

# Extract model info (automatically computes hash if not present)
model_info = extract_model_info(checkpoint)
predictions_json['model']['model_id'] = model_info['model_id']

# The extract_model_info function will:
# 1. Use checkpoint['model_id'] if present
# 2. Otherwise, compute hash from checkpoint['model_state']
# 3. Fall back to 'unknown' if no weights available
```

**Backwards Compatibility:**
The inference script automatically computes the hash for older checkpoints that don't have `model_id` stored. This ensures all predictions.json files have a valid model ID, even when using legacy model files.


**Benefits:**
1. **Deterministic**: Same weights = same hash, even across machines
2. **Collision-resistant**: SHA256 makes accidental duplicates virtually impossible
3. **Verifiable**: Can recompute hash to verify model authenticity
4. **Compact**: 12-character prefix sufficient for practical uniqueness
5. **Platform-independent**: Works across different PyTorch versions

**Example IDs:**
- `sha256-a3f2b9c8d1e7` (12 chars, ~281 trillion combinations)
- `sha256-5e2d1a9c7b4f3e8a` (16 chars for extra safety)


### Data Sources
```json
"data_sources": [
  {
    "data_source_id": "ICLISTENHF1951_BARK_2025",
    "device_code": "ICLISTENHF1951",
    "location_name": "Barkley Canyon",
    "site_code": "BARK",
    "date_from": "2025-01-01T00:00:00Z",
    "date_to": "2025-01-01T01:00:00Z",
    "sample_rate": 64000
  }
]
```

### Spectrogram Config
```json
"spectrogram_config": {
  "window_duration_sec": 1.0,
  "overlap": 0.9,
  "frequency_limits": {"min": 5, "max": 100},
  "context_duration_sec": 40.0,
  "segment_overlap": 0.5,
  "colormap": "viridis",
  "color_limits": {"min": -60, "max": 0},
  "source": {
    "type": "computed" | "onc_download",
    "generator": "SpectrogramGenerator",
    "backend": "scipy" | "torch" | null
  }
}
```

---

## Item Structure

Each item represents a **display unit** (e.g., a 40-second clip shown in the app):

```json
{
  "item_id": "ICLISTENHF1951_20250101T000000.996Z_seg000",
  "data_source_id": "ICLISTENHF1951_BARK_2025",
  "audio_start_time": "2025-01-01T00:00:00.996Z",
  "audio_end_time": "2025-01-01T00:00:40.996Z",
  "segment_index": 0,

  "model_outputs": [ ... ],  // Raw model predictions (empty [] for manual labels)
  "verifications": [ ... ],  // Human review rounds (label or verify)
  "paths": {
    "spectrogram_mat_path": "spectrograms/seg000.mat",
    "spectrogram_png_path": "spectrograms/seg000.png",
    "audio_path": "audio/seg000.wav"
  }
}
```

**Deprecated (still accepted for backwards compatibility):**
- `mat_path` → use `paths.spectrogram_mat_path`
- `spectrogram_path` → use `paths.spectrogram_png_path`
- `audio_path` at item root → use `paths.audio_path`
- `audio_timestamp` → use `audio_start_time`

---

## Model Outputs

### For Single-Class Binary Detection (e.g., Fin Whale Detector)
```json
"model_outputs": [
  {
    "class_hierarchy": "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale",
    "score": 0.87,  // Raw model output (0-1), NOT thresholded
    "metadata": {
      "num_windows": 5,
      "num_positive_windows": 3,  // At some default threshold
      "window_scores": [0.92, 0.88, 0.12, 0.95, 0.05]
    }
  }
]
```

### For Multi-Class Detection (e.g., Anomaly Types)
```json
"model_outputs": [
  {
    "class_hierarchy": "Anthropophony > Vessel",
    "score": 0.45
  },
  {
    "class_hierarchy": "Instrumentation > Self-noise > Acoustic self-noise",
    "score": 0.31
  },
  {
    "class_hierarchy": "Other > Ambient sound",
    "score": 0.89
  }
]
```

### For Sliding Window Predictions
When a 40s clip is analyzed with multiple sliding windows:

```json
"model_outputs": [
  {
    "class_hierarchy": "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale",
    "score": 0.92,  // Max/mean/aggregated score
    "aggregation_method": "max",
    "windows": [
      {
        "window_id": 0,
        "time_start_sec": 0.0,
        "time_end_sec": 9.6,
        "score": 0.02,
        "window_indices": [0, 96]  // Spectrogram column indices
      },
      {
        "window_id": 1,
        "time_start_sec": 7.4,
        "time_end_sec": 17.0,
        "score": 0.08,
        "window_indices": [74, 170]
      },
      {
        "window_id": 2,
        "time_start_sec": 14.8,
        "time_end_sec": 24.4,
        "score": 0.92,
        "window_indices": [148, 244]
      }
    ]
  }
]
```

---

## Verifications

Supports **multiple verification rounds** with full audit trail.
Used for **both** model prediction verification **and** manual labeling.

### Model prediction verification (Verify tab)

```json
"verifications": [
  {
    "verified_at": "2026-01-16T15:00:00Z",
    "verified_by": "alice@example.com",
    "verification_round": 1,
    "verification_status": "verified",
    "label_decisions": [
      {
        "label": "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale",
        "decision": "accepted",
        "threshold_used": 0.5
      },
      {
        "label": "Anthropophony > Vessel",
        "decision": "rejected",
        "threshold_used": 0.5
      }
    ],
    "confidence": "high",
    "notes": "Clear fin whale 20Hz pulse visible",
    "label_source": "expert"
  },
  {
    "verified_at": "2026-01-17T10:30:00Z",
    "verified_by": "bob@example.com",
    "verification_round": 2,
    "verification_status": "verified",
    "label_decisions": [
      {
        "label": "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale",
        "decision": "accepted",
        "threshold_used": 0.6
      },
      {
        "label": "Anthropophony > Vessel",
        "decision": "rejected",
        "threshold_used": 0.6
      }
    ],
    "confidence": "high",
    "notes": "Reviewed again, confirmed vessel label removal",
    "label_source": "expert"
  }
]
```

### Manual labeling (Label tab)

Manual labels use the same structure. All labels have `decision: "added"` and
`threshold_used: null` since there is no model:

```json
"verifications": [
  {
    "verified_at": "2026-01-16T15:00:00Z",
    "verified_by": "alice@example.com",
    "verification_round": 1,
    "verification_status": "verified",
    "label_decisions": [
      {
        "label": "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale",
        "decision": "added",
        "threshold_used": null
      }
    ],
    "label_source": "expert",
    "notes": ""
  }
]
```

**Latest verification is the current ground truth** (last item in array).

---

## Complete Example

### Example 1: Whale Detection with Sliding Windows
```json
{
  "schema_version": "2.0",
  "created_at": "2026-01-16T22:00:00Z",
  "updated_at": "2026-01-16T23:30:00Z",
  "task_type": "whale_detection",
  "model": {
    "model_id": "sha256-a3f2b9c8d1e7",
    "architecture": "resnet18",
    "checkpoint_path": "trained-models/finwhale-cnn-resnet18/best.pt",
    "output_classes": ["Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"]
  },
  "data_sources": [
    {
      "data_source_id": "ICLISTENHF1353_CLAYO_2019",
      "device_code": "ICLISTENHF1353",
      "date_from": "2019-07-01T00:00:00Z",
      "date_to": "2019-07-01T01:00:00Z"
    }
  ],
  "spectrogram_config": {
    "window_duration_sec": 1.0,
    "overlap": 0.9,
    "frequency_limits": {"min": 5, "max": 100},
    "context_duration_sec": 40.0
  },
  "items": [
    {
      "item_id": "ICLISTENHF1353_20190701T000000.117Z_seg000",
      "data_source_id": "ICLISTENHF1353_CLAYO_2019",
      "audio_start_time": "2019-07-01T00:00:00.117Z",
      "audio_end_time": "2019-07-01T00:00:40.117Z",
      "segment_index": 0,
      "model_outputs": [
        {
          "class_hierarchy": "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale",
          "score": 0.375,
          "aggregation_method": "max",
          "windows": [
            {"window_id": 0, "time_start_sec": 0.0, "score": 0.015, "window_indices": [0, 96]},
            {"window_id": 1, "time_start_sec": 7.4, "score": 0.021, "window_indices": [74, 170]},
            {"window_id": 2, "time_start_sec": 14.8, "score": 0.004, "window_indices": [148, 244]},
            {"window_id": 3, "time_start_sec": 22.1, "score": 0.0002, "window_indices": [221, 317]},
            {"window_id": 4, "time_start_sec": 29.5, "score": 0.375, "window_indices": [295, 391]}
          ]
        }
      ],
      "verifications": [
        {
          "verified_at": "2026-01-16T15:30:00Z",
          "verified_by": "expert1@onc.ca",
          "verification_round": 1,
          "verification_status": "verified",
          "label_decisions": [
            {
              "label": "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale",
              "decision": "accepted",
              "threshold_used": 0.3
            }
          ],
          "confidence": "high",
          "notes": "Window 4 shows clear 20Hz pulse",
          "label_source": "expert"
        }
      ],
      "paths": {
        "spectrogram_mat_path": "spectrograms/ICLISTENHF1353_20190701T000000.117Z_seg000.mat",
        "spectrogram_png_path": "spectrograms/ICLISTENHF1353_20190701T000000.117Z_seg000.png",
        "audio_path": "audio/ICLISTENHF1353_20190701T000000.117Z_seg000.wav"
      }
    }
  ]
}
```

### Example 2: Anomaly Detection (Multi-Class, No Windows)
```json
{
  "schema_version": "2.0",
  "created_at": "2026-01-16T20:00:00Z",
  "task_type": "anomaly_detection",
  "model": {
    "model_id": "sha256-b4c7d2e1f5a9",
    "architecture": "masked_autoencoder"
  },
  "items": [
    {
      "item_id": "ICLISTENHF1951_20240830T144006.000Z",
      "model_outputs": [
        {"class_hierarchy": "Other > Unknown sound of interest", "score": 0.92},
        {"class_hierarchy": "Anthropophony > Vessel", "score": 0.15},
        {"class_hierarchy": "Instrumentation > Malfunction > Data gap", "score": 0.08}
      ],
      "verifications": [
        {
          "verified_at": "2026-01-16T16:00:00Z",
          "verified_by": "expert2@onc.ca",
          "verification_round": 1,
          "verification_status": "verified",
          "label_decisions": [
            {"label": "Other > Unknown sound of interest", "decision": "accepted", "threshold_used": 0.5},
            {"label": "Instrumentation > Malfunction > Data gap", "decision": "added", "threshold_used": 0.5}
          ],
          "notes": "Confirmed unusual sound, also data gap present",
          "label_source": "expert"
        }
      ],
      "paths": {
        "spectrogram_mat_path": "spectrograms/ICLISTENHF1951_20240830T144006.000Z.mat"
      }
    }
  ]
}
```

### Example 3: Manual Labeling (No Model)
```json
{
  "schema_version": "2.0",
  "created_at": "2026-01-29T21:12:33Z",
  "updated_at": "2026-01-29T21:12:33Z",
  "task_type": "classification",
  "items": [
    {
      "item_id": "ICLISTENHF1951_20241231T235516.996Z_seg001",
      "verifications": [
        {
          "verified_at": "2026-01-29T21:10:00Z",
          "verified_by": "sbialek",
          "verification_round": 1,
          "verification_status": "verified",
          "label_decisions": [
            {"label": "Instrumentation", "decision": "added", "threshold_used": null}
          ],
          "label_source": "expert",
          "notes": ""
        }
      ]
    }
  ]
}
```

---

## Benefits

1. **Threshold-agnostic**: Store raw scores, apply thresholds in the app
2. **Multi-class support**: Handle any number of predicted classes
3. **Hierarchical labels**: Always uses taxonomy
4. **Audit trail**: Full history of all verifications
5. **Flexible granularity**: Works for full-clip or windowed predictions
6. **No duplication**: References external files
7. **Standardized**: Same format for whale detection, anomaly detection, and manual labeling
8. **Single output format**: No conversion needed for O3.0 ingestion

---

## Migration Notes

### From Current Whale Format
- Move `confidence` → `model_outputs[0].score`
- Move `expert_label` → `verifications[0].label_decisions[]`
- Group window predictions under `model_outputs[0].windows`
- Remove `crop_metadata` (redundant with spectrogram_config)
- Rename `mat_path` → `paths.spectrogram_mat_path`
- Rename `spectrogram_path` → `paths.spectrogram_png_path`
- Use `schema_version` instead of `version`
- Use `data_sources` array instead of singular `data_source`

### From Current Anomaly Format
- Convert filename-based dict → items array
- Wrap manual labels in `verifications` array with `label_decisions[]`
- If model predictions exist, add `model_outputs`

### From Annotations Format (labels.json)
- `annotations.labels` → `verifications[].label_decisions[].label` with `decision="added"`, `threshold_used=null`
- `annotations.annotated_by` → `verifications[].verified_by`
- `annotations.annotated_at` → `verifications[].verified_at`
- `annotations.notes` → `verifications[].notes`

---

## Implementation

The app should:
1. **Load** raw scores from `model_outputs`
2. **Display** with adjustable threshold slider
3. **Allow** expert to select labels from hierarchy
4. **Save** to `verifications` array with `label_decisions[]`, timestamp, and user
5. **Preserve** all previous verifications (append-only)
