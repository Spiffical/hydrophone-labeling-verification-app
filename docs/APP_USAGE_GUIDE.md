# Application Usage & Data Organization Guide

This guide explains how to organize your data for the Labeling & Verification App and how to use the flexible data loading features.

## 📂 Data Not Found? Start Here!

The application supports two primary data organization structures. Choosing the right one ensures your data loads correctly.

### 1. Hierarchical Structure (Recommended)
Best for large datasets organized by Date and Device.

**Structure:**
```text
/path/to/data_root/
├── predictions.json           # (Optional) Root-level predictions (applies to all)
├── 2024-01-01/                # Date Folder (YYYY-MM-DD)
│   ├── predictions.json       # (Optional) Date-level predictions
│   ├── DEVICENAME/            # Device Name
│   │   ├── spectrograms/      # Spectrograms (.mat, .png)
│   │   ├── audio/             # Audio files (.wav, .flac)
│   │   ├── predictions.json   # (Optional) Device-level predictions
│   │   └── labels.json        # (Optional) User annotations
```

**Predictions Priority:** Root > Date > Device. The first one found is used.

**How to Load:**
1. Click **Data Configuration** (Folder Icon) in the top-right header.
2. Browse to and select the `data_root` folder (the parent of the date folders).
3. The app will detect "Hierarchical" structure.
4. Click **Load Data**.
5. Use the **Date** and **Hydrophone** dropdowns in the header to filter data.
   - Select **"All Dates"** to see everything across time.
   - Select **"All Devices"** to see data from all hydrophones.

### 2. Device-Only Structure
Useful if you have data for multiple devices but not separated by date folders.

**Structure:**
```text
/path/to/data_root/
├── DEVICE_1/
│   ├── onc_spectrograms/*.mat
│   └── predictions.json
├── DEVICE_2/
│   ├── onc_spectrograms/*.mat
│   └── ...
```

**How to Load:**
1. Browse to `data_root`.
2. App detects "Device Folders".
3. Load Data.
4. Use **Hydrophone** dropdown to filter. "Date" dropdown will be disabled.

### 3. Flat Structure (Single Folder)
Best for small datasets or testing individual folders.

**Structure:**
```text
/path/to/my_folder/
├── file1.mat
├── file1.wav
├── file2.mat
├── file2.wav
└── labels.json  (Optional)
```

**How to Load:**
1. Click **Data Configuration** (Folder Icon).
2. Browse to and select your folder containing the files.
3. The app will detect "Flat Spectrograms".
4. Click **Load Data**.
5. The Date/Device dropdowns will be disabled or show "(Direct)".

---

## 🛠 Flexible Data Loading Features

The **Data Configuration Modal** allows you to override specific paths if your data doesn't perfectly match the standard structures.

### Custom Path Overrides
If your folder structure is non-standard (e.g., spectrograms are in a different folder than audio), you can manually set the paths:

1. Open **Data Configuration**.
2. Select your base **Data Directory**.
3. Use the **Browse** buttons next to:
   - **Spectrogram Folder**: Location of `.mat` / `.png` files.
   - **Audio Folder**: Location of `.wav` / `.flac` files.
   - **Predictions File**: Location of `predictions.json`.
4. The status badges (Success/Warning) will update in real-time to show if files are found.

### "All" Option for Bulk Review
When using the **Hierarchical** structure:
- **All Dates**: Loads data from *every* date folder found in the root directory.
- **All Devices**: Loads data from *every* device folder for the selected date(s).

> **Performance Note:** Loading "All" on a very large dataset (thousands of files) might take a moment. The app aggregates all findings into a single view.

### Labels & Persistence
- **Auto-Save**: Labels are automatically saved to `labels.json` in the source directory.
- **Custom Location**: You can override where labels are saved in the **Label Mode** sidebar under "Output Labels".
- **Format**: Labels are stored in a standard JSON format compatible with the shared data pipeline.

---

## ⚙️ Power User: Configuration File

The app uses `config/default.yaml` by default. You can customize:

```yaml
data:
  spectrogram_folder_names:  # Folders to search for spectrograms (in order)
    - spectrograms
    - onc_spectrograms
    - mat_files
  audio_folder_names:  # Folders to search for audio
    - audio
```

- **Null paths**: If `folder`, `audio_folder`, etc. are `null`, the app prompts you to select via the UI.
- **Supported formats**: `.mat`, `.npy`, `.png` for spectrograms; `.wav`, `.flac`, `.mp3` for audio.

---

## 🔍 Troubleshooting

| Issue | Solution |
|-------|----------|
| **"No data loaded"** | Check that you selected the *path containing* your files (Flat) or the *root* containing date folders (Hierarchical). |
| **"Audio not found"** | Ensure audio filenames match spectrogram filenames (e.g., `file1.mat` -> `file1.wav`) or use the timestamp convention. |
| **"Predictions not found"** | Place `predictions.json` at root, date, or device level. The app checks in that order. |
| **Spectrograms are blank** | Ensure your `.mat` files contain the expected variables (`decimator_x`, `decimator_y` or `spectrogram`). |
