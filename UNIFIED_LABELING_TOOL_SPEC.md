# Unified Spectrogram Labeling & Verification Tool Specification

**Author**: AI Assistant  
**Date**: 2026-01-13  
**Purpose**: Comprehensive specification document for building a unified labeling/verification tool from existing components

---

## Executive Summary

This document specifies a unified web application that combines:
1. **Original Labeling** - Label spectrograms from scratch (from `selfsupervision_anomalies_onc/tools/labeling`)
2. **ML Verification** - Review and verify ML model predictions (from `hydrophonedashboard/scripts/verification_dashboard.py`)
3. **Whale Call Analysis** - Binary detection with sliding window inference (from `whale-call-analysis`)

The goal is a single, user-friendly Dash application that supports multiple use cases through a unified interface.

---

## Part 1: Source Repository Analysis

### 1.1 Labeling Tool (`selfsupervision_anomalies_onc/tools/labeling`)

**Purpose**: Manual labeling of spectrograms from MAT files with hierarchical taxonomy

**Key Files**:
| File | Purpose |
|------|---------|
| `main.py` | Dash app initialization, audio file serving |
| `layout.py` | Main UI layout with navigation, settings panel |
| `callbacks.py` | All Dash callbacks for pagination, labeling, image generation |
| `config.py` | Configuration loading from YAML and CLI args |
| `hierarchical_labels.py` | Complete taxonomy tree (5 top-level categories) |
| `components/hierarchical_selector.py` | Tree-based label picker with search |
| `components/audio_player.py` | Audio playback component |
| `utils/file_operations.py` | Label JSON loading/saving |
| `utils/image_processing.py` | MAT to image conversion with caching |
| `utils/audio_matching.py` | Match spectrograms to audio files |

**Data Format** (labels.json):
```json
{
  "filename.mat": [
    "Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale",
    "Anthropophony > Vessel"
  ]
}
```

**Features**:
- Grid display with configurable items per page
- Hierarchical label tree with search
- Audio playback with waveform
- Colormap toggle (Viridis / ONC default)
- Y-axis scale toggle (linear / log)
- Real-time label persistence

---

### 1.2 Verification Dashboard (`hydrophonedashboard/scripts/verification_dashboard.py`)

**Purpose**: Expert review of ML model predictions with approve/reject workflow

**Key Files**:
| File | Purpose |
|------|---------|
| `verification_dashboard.py` | Main 1200-line Dash app |
| `tools/labeling/hierarchical_labels.py` | Shared taxonomy (symlinked) |
| `tools/labeling/components/hierarchical_selector.py` | Reused selector component |
| `thresholds.json` | Per-class confidence thresholds |

**Data Format** (labels.json per hydrophone):
```json
{
  "HYDROPHONE_T0_T1.png": {
    "hydrophone": "ICLISTENHF1951",
    "predicted_labels": ["Anthropophony > Vessel"],
    "probabilities": {
      "Anthropophony > Vessel": 0.89,
      "Other > Ambient sound": 0.12
    },
    "t0": "20260108T120000.000Z",
    "t1": "20260108T120500.000Z",
    "verified_labels": null,
    "verified_by": null,
    "verified_at": null,
    "notes": ""
  }
}
```

**Features**:
- Date/hydrophone selection
- Filter by label class
- Threshold slider for filtering
- Verification status tracking (Pending/Verified)
- Confirm button (accept predictions as-is)
- Edit Labels button (modify predictions)
- Notes field
- Progress indicator (X of Y verified)

---

### 1.3 Whale Call Analysis Pipeline (`whale-call-analysis`)

**Purpose**: Binary fin whale detection with sliding window inference

**Key Files**:
| File | Purpose |
|------|---------|
| `scripts/download_sequential_audio.py` | Download audio, generate spectrograms |
| `scripts/run_inference.py` | Sliding window inference |
| `src/utils/prediction_tracker.py` | JSON output with versioning |

**Data Format** (predictions.json):
```json
{
  "model": {
    "model_id": "sha256-abc123",
    "architecture": "resnet18",
    "checkpoint_path": "/path/to/best.pt"
  },
  "data_source": {
    "device_code": "ICLISTENHF1353",
    "date_from": "2019-07-01T00:00:00Z",
    "date_to": "2019-07-01T01:00:00Z"
  },
  "predictions": [
    {
      "file_id": "..._seg001_win74",
      "confidence": 0.95,
      "window_start": 74,
      "mat_path": "mat_files/....mat",
      "spectrogram_path": "spectrograms/....png",
      "audio_path": "audio/....wav"
    }
  ],
  "segments": [
    {
      "segment_id": "..._seg001_37.1s",
      "max_confidence": 0.95,
      "spectrogram_path": "spectrograms/....png",
      "audio_path": "audio/....wav",
      "windows": [...]
    }
  ]
}
```

**Features**:
- Auto-detected crop_size from checkpoint
- Sliding window with even distribution
- Segment-level aggregation (max confidence per 40s segment)
- Full traceability (source audio → segment → windows)

---

## Part 2: Unified Application Design

### 2.1 User Modes

The unified app should support three primary modes, selectable via tabs or dropdown:

| Mode | Use Case | Primary Data Source |
|------|----------|---------------------|
| **Label** | Manual annotation from scratch | MAT files + optional audio |
| **Verify** | Review ML predictions | Inference predictions.json |
| **Explore** | Browse existing labeled data | Completed labels.json |

### 2.2 Unified Data Schema

All modes should use a standard internal format:

```json
{
  "version": "2.0",
  "created_at": "ISO8601",
  "source": {
    "type": "manual" | "ml_prediction" | "imported",
    "model": {...} | null,
    "data_source": {...}
  },
  "items": [
    {
      "item_id": "unique_identifier",
      "spectrogram_path": "path/to/image.png",
      "mat_path": "path/to/data.mat",
      "audio_path": "path/to/audio.wav",
      "timestamps": {
        "start": "ISO8601",
        "end": "ISO8601"
      },
      "device_code": "ICLISTENHF1353",
      
      "predictions": {
        "labels": ["Biophony > Marine mammal > Fin whale"],
        "confidence": {"Biophony > Marine mammal > Fin whale": 0.95},
        "model_id": "sha256-abc123"
      } | null,
      
      "annotations": {
        "labels": ["Biophony > Marine mammal > Fin whale"],
        "annotated_by": "scientist1",
        "annotated_at": "ISO8601",
        "verified": true,
        "notes": ""
      } | null,
      
      "metadata": {
        "original_shape": [96, 391],
        "crop_size": [96, 96],
        "windows": [{...}]  // For sliding window inference
      }
    }
  ],
  "summary": {
    "total_items": 100,
    "annotated": 45,
    "verified": 30
  }
}
```

### 2.3 UI Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SPECTROGRAM LABELING TOOL                            │
│  [Label Mode ▼]  [Device: ICLISTENHF1353 ▼]  [Date: 2026-01-13]            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  FILTERS & CONTROLS                                                   │   │
│  │  [Confidence: 0.5 ─────●─────── 1.0]  [Status: All ▼]  [Class: All ▼]│   │
│  │  Progress: ████████░░░░ 45/100 verified                              │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐               │
│  │ [Image] │ │ [Image] │ │ [Image] │ │ [Image] │ │ [Image] │               │
│  │ ─────── │ │ ─────── │ │ ─────── │ │ ─────── │ │ ─────── │               │
│  │ 95% 🐋  │ │ 12% 🔊  │ │ 78% 🐋  │ │ 3% 🔊   │ │ 89% 🐋  │               │
│  │[✓][✎][♫]│ │[✓][✎][♫]│ │[✓][✎][♫]│ │[✓][✎][♫]│ │[✓][✎][♫]│               │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘               │
│                                                                              │
│  [◀ Previous]  Page 1 of 20  [Next ▶]                                       │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  SETTINGS (collapsible)                                                      │
│  [×] ONC Colormap  [×] Log Y-Axis  [×] Show Probabilities                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.4 Hierarchical Labels (Reuse Existing)

The taxonomy from `hierarchical_labels.py` should be reused unchanged:

```python
HIERARCHICAL_LABELS = {
    "Anthropophony": {...},
    "Biophony": {
        "Marine mammal": {
            "Cetacean": {
                "Baleen whale": {
                    "Fin whale": {},
                    "Blue whale": {},
                    ...
                },
                ...
            }
        }
    },
    "Geophony": {...},
    "Instrumentation": {...},
    "Other": {...}
}
```

**Key functions to reuse**:
- `get_all_paths()` - Get all valid label paths
- `path_to_string()` - Convert path tuple to "A > B > C" format
- `get_label_display_name()` - Get leaf name for display

---

## Part 3: Technical Architecture

### 3.1 Directory Structure

```
spectrogram-labeling-tool/
├── app/
│   ├── __init__.py
│   ├── main.py                # Entry point
│   ├── config.py              # Configuration management
│   ├── layouts/
│   │   ├── __init__.py
│   │   ├── main_layout.py     # Top-level layout
│   │   ├── label_mode.py      # Manual labeling UI
│   │   ├── verify_mode.py     # ML verification UI
│   │   └── explore_mode.py    # Browse/export UI
│   ├── components/
│   │   ├── __init__.py
│   │   ├── hierarchical_selector.py  # Label tree picker
│   │   ├── spectrogram_card.py       # Card with image/controls
│   │   ├── audio_player.py           # Waveform + playback
│   │   ├── confidence_slider.py      # Threshold filter
│   │   └── progress_bar.py           # Annotation progress
│   ├── callbacks/
│   │   ├── __init__.py
│   │   ├── navigation.py      # Pagination
│   │   ├── labeling.py        # Add/remove labels
│   │   ├── verification.py    # Confirm/edit flow
│   │   └── settings.py        # Display options
│   └── utils/
│       ├── __init__.py
│       ├── data_loading.py    # Load various formats
│       ├── image_processing.py # MAT → image
│       ├── audio_matching.py  # Find audio files
│       ├── file_io.py         # JSON read/write
│       └── format_converters.py # Convert between formats
├── assets/
│   ├── styles.css
│   └── audio_controls.js
├── taxonomy/
│   └── hierarchical_labels.py
├── config/
│   └── default.yaml
├── requirements.txt
├── README.md
└── run.py
```

### 3.2 Format Converters

The app should support importing from multiple sources:

```python
# format_converters.py

def convert_whale_predictions_to_unified(predictions_json: dict) -> dict:
    """Convert whale-call-analysis predictions.json to unified format"""
    items = []
    for seg in predictions_json.get("segments", []):
        items.append({
            "item_id": seg["segment_id"],
            "spectrogram_path": seg["spectrogram_path"],
            "audio_path": seg.get("audio_path"),
            "timestamps": {
                "start": seg.get("audio_timestamp"),
                "end": None
            },
            "device_code": predictions_json["data_source"]["device_code"],
            "predictions": {
                "labels": ["Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale"] 
                          if seg["max_confidence"] > 0.5 else [],
                "confidence": {"Fin whale": seg["max_confidence"]},
                "model_id": predictions_json["model"]["model_id"]
            },
            "annotations": None,
            "metadata": {
                "windows": seg["windows"],
                "num_positive": seg["num_positive"]
            }
        })
    return {"version": "2.0", "items": items, ...}

def convert_hydrophonedashboard_to_unified(labels_json: dict, date: str, hydrophone: str) -> dict:
    """Convert hydrophonedashboard labels.json to unified format"""
    ...

def convert_legacy_labeling_to_unified(labels_json: dict, mat_folder: str) -> dict:
    """Convert old labeling tool format to unified format"""
    ...
```

### 3.3 Required Dependencies

```
# requirements.txt
dash>=2.14.0
dash-bootstrap-components>=1.5.0
plotly>=5.18.0
numpy>=1.24.0
scipy>=1.10.0
opencv-python>=4.8.0
matplotlib>=3.7.0
pyyaml>=6.0
cachetools>=5.3.0
soundfile>=0.12.0
python-dotenv>=1.0.0
```

---

## Part 4: Key Features to Implement

### 4.1 Core Features (MVP)

1. **Multi-format data loading**
   - Load from MAT folder (labeling mode)
   - Load from predictions.json (whale-call-analysis)
   - Load from labels.json (hydrophonedashboard)

2. **Hierarchical label selector**
   - Reuse existing component
   - Search functionality
   - Select at any level

3. **Spectrogram grid display**
   - Configurable items per page
   - Lazy loading / caching
   - Thumbnail + full view modal

4. **Audio playback**
   - Match audio files to spectrograms
   - Waveform display
   - Play/pause controls

5. **Annotation persistence**
   - Auto-save on change
   - Track who/when
   - Export to various formats

### 4.2 Verification Features

1. **Confidence threshold slider**
   - Filter items by prediction confidence
   - Show count above/below threshold

2. **Quick actions**
   - "Confirm All Visible" batch action
   - "Skip" to mark as reviewed without labeling

3. **Progress tracking**
   - Show verified / total
   - Filter by verification status

### 4.3 Advanced Features (Post-MVP)

1. **Keyboard shortcuts**
   - Arrow keys for navigation
   - Number keys for quick labels
   - Enter to confirm

2. **Bulk operations**
   - Select multiple items
   - Apply same label to all

3. **Export options**
   - Export to training format
   - Export to CSV
   - Generate statistics

4. **User management**
   - Username input or SSO
   - Track per-user annotations

---

## Part 5: Implementation Notes

### 5.1 Reusable Components (Copy From Source)

These files can be copied with minimal changes:

| Component | Source Location | Changes Needed |
|-----------|-----------------|----------------|
| `hierarchical_labels.py` | `selfsupervision_anomalies_onc/tools/labeling/` | None |
| `hierarchical_selector.py` | Same location + `hydrophonedashboard/tools/labeling/components/` | Merge best of both |
| `audio_player.py` | `selfsupervision_anomalies_onc/tools/labeling/components/` | None |
| `styles.css` | Same location under `assets/` | None |
| `audio_controls.js` | Same location under `assets/` | None |
| `image_processing.py` | `selfsupervision_anomalies_onc/tools/labeling/utils/` | None |

### 5.2 Key Callbacks Pattern

```python
@app.callback(
    Output({"type": "selected-labels-store", "filename": MATCH}, "data"),
    Output({"type": "selected-labels-display", "filename": MATCH}, "children"),
    Input({"type": "label-checkbox", "filename": MATCH, "path": ALL}, "checked"),
    State({"type": "selected-labels-store", "filename": MATCH}, "data"),
    prevent_initial_call=True
)
def update_labels(checkbox_values, current_labels):
    # Pattern matching for dynamic components
    ...
```

### 5.3 Image Caching Strategy

```python
from cachetools import LRUCache

IMAGE_CACHE = LRUCache(maxsize=100)

def generate_image_cached(mat_path, colormap, log_scale):
    cache_key = (mat_path, colormap, log_scale)
    if cache_key in IMAGE_CACHE:
        return IMAGE_CACHE[cache_key]
    
    image_data = generate_spectrogram_image(mat_path, colormap, log_scale)
    IMAGE_CACHE[cache_key] = image_data
    return image_data
```

---

## Part 6: Getting Started

### 6.1 Steps for New LLM

1. **Create project structure** (see Section 3.1)

2. **Copy reusable components** (see Section 5.1)

3. **Implement data loading**
   - Start with simplest format (MAT folder)
   - Add converters for other formats

4. **Build main layout**
   - Mode selector tabs
   - Filter controls
   - Grid container

5. **Implement spectrogram card component**
   - Image display
   - Label badges
   - Action buttons

6. **Add hierarchical selector**
   - Copy existing implementation
   - Wire up callbacks

7. **Add audio playback**
   - Audio file matching
   - Player component

8. **Implement persistence**
   - Load on startup
   - Save on every change

9. **Add verification features**
   - Confidence slider
   - Confirm/edit workflow
   - Progress tracking

10. **Polish UI**
    - Responsive design
    - Keyboard shortcuts
    - Error handling

### 6.2 Test Data

Use the following for testing:

```bash
# Generate test data with whale-call-analysis
python scripts/download_sequential_audio.py \
    --device-code ICLISTENHF1353 \
    --start-date 2019-07-01T00:00:00Z \
    --end-date 2019-07-01T01:00:00Z \
    --output-dir test_data/ \
    --save-png \
    --save-audio

python scripts/run_inference.py \
    --mat-dir test_data/mat_files \
    --checkpoint path/to/model.pt \
    --output-json test_data/predictions.json \
    --dataset-metadata test_data/dataset_metadata.json \
    --sliding-window
```

---

## Appendix A: Complete Hierarchical Taxonomy

See `hierarchical_labels.py` for full taxonomy. Key paths for whale detection:

```
Biophony > Marine mammal > Cetacean > Baleen whale > Fin whale
Biophony > Marine mammal > Cetacean > Baleen whale > Blue whale
Biophony > Marine mammal > Cetacean > Baleen whale > Humpback whale
Biophony > Marine mammal > Cetacean > Toothed whale > Killer whale > ...
```

---

## Appendix B: Links to Source Repositories

- **Labeling Tool**: `selfsupervision_anomalies_onc/tools/labeling/`
- **Verification Dashboard**: `hydrophonedashboard/scripts/verification_dashboard.py`
- **Whale Call Analysis**: `whale-call-analysis/scripts/`

---

*End of Specification Document*
