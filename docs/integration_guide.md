# Integration Guide

How to update your inference pipelines to work with the Unified Labeling & Verification App.

## Quick Start

Your inference pipeline needs to output a `predictions.json` file in the format specified in [`OCEANS3_JSON_SCHEMA.md`](../OCEANS3_JSON_SCHEMA.md).

Both model predictions and manual labels use the **same unified schema**. The
only difference is which optional root-level fields are present:

- **Predictions**: include `model`, `pipeline`, `spectrogram_config`, `items[].model_outputs`
- **Manual labels**: omit those; labels go into `items[].verifications[].label_decisions[]`

### 1. Use the Python Tracker (Recommended)

The easiest way is to use the provided `UnifiedPredictionTracker` class:

```python
from shared.unified_prediction_tracker import UnifiedPredictionTracker

# Initialize
tracker = UnifiedPredictionTracker(output_path='predictions.json')

# Set model metadata (use SHA256 hash of weights for reproducibility)
tracker.set_model_info(
    model_id='sha256-a3f2b9c8d1e7',  # Computed from model weights
    architecture='resnet18',
    output_classes=['Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale']
)

# Add data source(s) — items reference these by data_source_id
tracker.add_data_source(
    data_source_id='ICLISTENHF1951_BARK_2025',
    device_code='ICLISTENHF1951',
    location_name='Barkley Canyon',
    site_code='BARK',
    sample_rate=64000,
    date_from='2025-01-01T00:00:00Z',
    date_to='2025-01-01T01:00:00Z',
)

tracker.set_task_type('whale_detection')

# Optional: pipeline provenance
tracker.set_pipeline_info(
    pipeline_version='v1.0.0',
    pipeline_commit='abc1234',
    pipeline_repo='my-inference-pipeline',
)

# Add predictions (raw scores, NOT thresholded)
for segment in segments:
    tracker.add_item(
        item_id=segment.name,
        data_source_id='ICLISTENHF1951_BARK_2025',
        audio_start_time=segment.start_time.isoformat(),
        audio_end_time=segment.end_time.isoformat(),
        segment_index=segment.index,
        spectrogram_mat_path=f'spectrograms/{segment.name}.mat',
        spectrogram_png_path=f'spectrograms/{segment.name}.png',
        audio_path=f'audio/{segment.name}.wav',
        model_outputs=[{
            'class_hierarchy': 'Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale',
            'score': model.predict(segment)  # Raw 0-1 score
        }]
    )

tracker.save()
```

### 2. File Placement

Place your `predictions.json` at one of these locations (checked in order):

| Location | Applies To |
|----------|------------|
| `data_root/predictions.json` | All data in the directory |
| `data_root/YYYY-MM-DD/predictions.json` | All devices for that date |
| `data_root/YYYY-MM-DD/DEVICE/predictions.json` | Single device only |

The app uses the **first one found** and stops searching.

---

## Key Requirements

1. **Store raw scores (0-1)**, not thresholded binary labels. Users adjust thresholds in the UI.
2. **Use hierarchical labels** from the taxonomy (e.g., `Biophony > Marine mammal > ...`).
3. **Include a `model_id`**: Compute a SHA256 hash of your model weights for reproducibility.
4. **Use `data_sources` array** (optional): Each item can reference a data source by `data_source_id`.

### Computing Model ID

```python
import hashlib, io, torch

def compute_model_hash(state_dict: dict, length: int = 12) -> str:
    buffer = io.BytesIO()
    sorted_dict = {k: state_dict[k] for k in sorted(state_dict.keys())}
    torch.save(sorted_dict, buffer)
    buffer.seek(0)
    return f"sha256-{hashlib.sha256(buffer.read()).hexdigest()[:length]}"

model_id = compute_model_hash(model.state_dict())
```

---

## Minimal Output Example

```json
{
  "schema_version": "2.0",
  "created_at": "2025-01-01T00:00:00Z",
  "task_type": "whale_detection",
  "model": {
    "model_id": "sha256-a3f2b9c8d1e7",
    "architecture": "resnet18",
    "output_classes": ["Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"]
  },
  "data_sources": [
    {
      "data_source_id": "ICLISTENHF1951_BARK_2025",
      "device_code": "ICLISTENHF1951"
    }
  ],
  "items": [
    {
      "item_id": "seg_000",
      "data_source_id": "ICLISTENHF1951_BARK_2025",
      "audio_start_time": "2025-01-01T00:00:00Z",
      "audio_end_time": "2025-01-01T00:00:40Z",
      "model_outputs": [
        {
          "class_hierarchy": "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale",
          "score": 0.87
        }
      ],
      "verifications": [],
      "paths": {
        "spectrogram_mat_path": "spectrograms/seg_000.mat"
      }
    }
  ]
}
```

---

## How Verifications Work

Both the **Verify tab** (model prediction review) and the **Label tab** (manual
labeling) write human decisions into `items[].verifications[]`. Each entry is a
round with `label_decisions[]`:

```json
"verifications": [
  {
    "verified_at": "2025-01-01T12:00:00Z",
    "verified_by": "expert@onc.ca",
    "verification_round": 1,
    "verification_status": "verified",
    "label_decisions": [
      { "label": "Fin whale", "decision": "accepted", "threshold_used": 0.5 },
      { "label": "Vessel", "decision": "rejected", "threshold_used": 0.5 }
    ],
    "label_source": "expert",
    "notes": "Clear 20Hz pulse"
  }
]
```

For manual labels (no model), all decisions use `"decision": "added"` and
`"threshold_used": null`.

---

## Related Docs

- **Format Specification**: [`OCEANS3_JSON_SCHEMA.md`](../OCEANS3_JSON_SCHEMA.md)
- **Python Class**: [`shared/unified_prediction_tracker.py`](../shared/unified_prediction_tracker.py)
