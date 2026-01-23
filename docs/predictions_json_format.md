# Unified Predictions JSON Format Specification

## Overview
This document defines a standardized format for storing ML model predictions and expert verifications that works across different acoustic analysis tasks (whale detection, anomaly detection, etc.) while maintaining flexibility for different data granularities.

## Core Principles
1. **Store raw model outputs**, not thresholded predictions
2. **Use hierarchical labels** from the taxonomy
3. **Support multiple verification rounds** with full audit trail
4. **Avoid data duplication** - reference files, don't embed them
5. **Flexible granularity** - support both full-clip and windowed predictions

---

## Format Structure

###  Root Level
```json
{
  "version": "2.0",
  "created_at": "2026-01-16T23:00:00Z",
  "updated_at": "2026-01-16T23:30:00Z",
  "model": { ... },
  "data_source": { ... },
  "spectrogram_config": { ... },
  "task_type": "whale_detection" | "anomaly_detection" | "classification",
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
1. ✅ **Deterministic**: Same weights = same hash, even across machines
2. ✅ **Collision-resistant**: SHA256 makes accidental duplicates virtually impossible  
3. ✅ **Verifiable**: Can recompute hash to verify model authenticity
4. ✅ **Compact**: 12-character prefix sufficient for practical uniqueness
5. ✅ **Platform-independent**: Works across different PyTorch versions

**Example IDs:**
- `sha256-a3f2b9c8d1e7` (12 chars, ~281 trillion combinations)
- `sha256-5e2d1a9c7b4f3e8a` (16 chars for extra safety)


### Data Source
```json
"data_source": {
  "device_code": "ICLISTENHF1951",
  "location": "Barkley Canyon",
  "date_from": "2025-01-01T00:00:00Z",
  "date_to": "2025-01-01T01:00:00Z",
  "sample_rate": 64000
}
```

### Spectrogram Config
```json
"spectrogram_config": {
  "window_duration": 1.0,
  "overlap": 0.9,
  "frequency_limits": {"min": 5, "max": 100},
  "context_duration": 40.0,
  "segment_overlap": 0.5,
  "colormap": "viridis",
  "color_limits": {"min": -60, "max": 0},
  "temporal_padding_used": 2.0
}
```

---

## Item Structure

Each item represents a **display unit** (e.g., a 40-second clip shown in the app):

```json
{
  "item_id": "ICLISTENHF1951_20250101T000000.996Z_seg000",
  "mat_path": "mat_files/ICLISTENHF1951_20250101T000000.996Z_seg000.mat",
  "audio_path": "audio/ICLISTENHF1951_20250101T000000.996Z_seg000.wav",
  "spectrogram_path": "spectrograms/ICLISTENHF1951_20250101T000000.996Z_seg000.png",
  "audio_timestamp": "2025-01-01T00:00:00.996Z",
  "duration_sec": 40.0,
  
  "model_outputs": [ ... ],  // Raw model predictions (see below)
  "verifications": [ ... ]    // Expert reviews (see below)
}
```

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

Supports **multiple verification rounds** with full audit trail:

```json
"verifications": [
  {
    "verified_at": "2026-01-16T15:00:00Z",
    "verified_by": "alice@example.com",
    "threshold_used": 0.5,  // Threshold user applied
    "labels": [
      "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale",
      "Anthropophony > Vessel"
    ],
    "confidence": "high" | "medium" | "low" | null,
    "notes": "Clear fin whale 20Hz pulse visible",
    "verification_round": 1
  },
  {
    "verified_at": "2026-01-17T10:30:00Z",
    "verified_by": "bob@example.com",
    "threshold_used": 0.6,
    "labels": [
      "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"
    ],
    "confidence": "high",
    "notes": "Reviewed again, removed vessel label - was background noise",
    "verification_round": 2
  }
]
```

**Latest verification is the current ground truth** (last item in array).

---

## Complete Example

### Example 1: FWhale Detection with Sliding Windows
```json
{
  "version": "2.0",
  "created_at": "2026-01-16T22:00:00Z",
  "updated_at": "2026-01-16T23:30:00Z",
  "model": {
    "model_id": "finwhale_resnet18_v1.0",
    "architecture": "resnet18",
    "checkpoint_path": "trained-models/finwhale-cnn-resnet18/best.pt",
    "output_classes": ["Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"]
  },
  "data_source": {
    "device_code": "ICLISTENHF1353",
    "date_from": "2019-07-01T00:00:00Z",
    "date_to": "2019-07-01T01:00:00Z"
  },
  "spectrogram_config": {
    "window_duration": 1.0,
    "overlap": 0.9,
    "frequency_limits": {"min": 5, "max": 100},
    "context_duration": 40.0
  },
  "task_type": "whale_detection",
  "items": [
    {
      "item_id": "ICLISTENHF1353_20190701T000000.117Z_seg000",
      "mat_path": "mat_files/ICLISTENHF1353_20190701T000000.117Z_seg000.mat",
      "audio_path": "audio/ICLISTENHF1353_20190701T000000.117Z_seg000.wav",
      "audio_timestamp": "2019-07-01T00:00:00.117Z",
      "duration_sec": 40.0,
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
          "threshold_used": 0.3,
          "labels": ["Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"],
          "confidence": "high",
          "notes": "Window 4 shows clear 20Hz pulse",
          "verification_round": 1
        }
      ]
    }
  ]
}
```

### Example 2: Anomaly Detection (Multi-Class, No Windows)
```json
{
  "version": "2.0",
  "created_at": "2026-01-16T20:00:00Z",
  "model": {
    "model_id": "anomaly_detector_mae_v1",
    "architecture": "masked_autoencoder"
  },
  "task_type": "anomaly_detection",
  "items": [
    {
      "item_id": "ICLISTENHF1951_20240830T144006.000Z",
      "mat_path": "mat_files/ICLISTENHF1951_20240830T144006.000Z-spect_plotRes.mat",
      "model_outputs": [
        {"class_hierarchy": "Other > Unknown sound of interest", "score": 0.92},
        {"class_hierarchy": "Anthropophony > Vessel", "score": 0.15},
        {"class_hierarchy": "Instrumentation > Malfunction > Data gap", "score": 0.08}
      ],
      "verifications": [
        {
          "verified_at": "2026-01-16T16:00:00Z",
          "verified_by": "expert2@onc.ca",
          "threshold_used": 0.5,
          "labels": [
            "Other > Unknown sound of interest",
            "Instrumentation > Malfunction > Data gap"
          ],
          "notes": "Confirmed unusual sound, also data gap present",
          "verification_round": 1
        }
      ]
    }
  ]
}
```

---

## Benefits

1. ✅ **Threshold-agnostic**: Store raw scores, apply thresholds in the app
2. ✅ **Multi-class support**: Handle any number of predicted classes
3. ✅ **Hierarchical labels**: Always uses taxonomy
4. ✅ **Audit trail**: Full history of all verifications
5. ✅ **Flexible granularity**: Works for full-clip or windowed predictions
6. ✅ **No duplication**: References external files
7. ✅ **Standardized**: Same format for whale detection and anomaly detection

---

## Migration Notes

### From Current Whale Format
- Move `confidence` → `model_outputs[0].score`
- Move `expert_label` → `verifications[0].labels`
- Group window predictions under `model_outputs[0].windows`
- Remove `crop_metadata` (redundant with spectrogram_config)

### From Current Anomaly Format
- Convert filename-based dict → items array
- Wrap manual labels in `verifications` array
- If model predictions exist, add `model_outputs`

---

## Implementation

The app should:
1. **Load** raw scores from `model_outputs`
2. **Display** with adjustable threshold slider
3. **Allow** expert to select labels from hierarchy
4. **Save** to `verifications` array with timestamp/user
5. **Preserve** all previous verifications
