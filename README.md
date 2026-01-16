# Acoustic Review Suite: Unified Spectrogram Labeling Tool

A professional, high-performance web application built with Plotly Dash for the scientific analysis, labeling, and verification of hydrophone data. This tool is specifically designed to handle large-scale acoustic datasets, particularly for marine mammal research (e.g., fin whale calls).

![Spectrogram Interface](assets/screenshot_demo.png) *(Placeholder for actual screenshot)*

## ✨ Key Features

*   **Unified Research Workflow**: Seamlessly switch between **Labeling**, **Verification**, and **Exploration** modes.
*   **Interactive Spectrogram Analysis**: High-resolution Plotly zoom modals with live controls for colormap and frequency scale (Hz/kHz, Linear/Log).
*   **Integrated Audio-Visual Review**: Synchronized audio playback (`.wav`/`.flac`) with custom controllers on both thumbnail and detail views.
*   **Intelligent Data Rendering**: Automatic support for multiple MAT formats, Julian date conversion, and adaptive percentile-based color scaling.
*   **Modern Scientific UI**: Clean, GitHub-inspired dark/light theme optimized for precision research sessions.

## 🚀 Quick Start

### 1. Installation

Ensure you have Python 3.9+ and a virtual environment set up:

```bash
# Clone the repository
git clone https://github.com/Spiffical/labeling-verification-app.git
cd labeling-verification-app

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Edit `config/default.yaml` to point to your data directories:

```yaml
data:
  label:
    folder: /path/to/your/mat_files
    audio_folder: /path/to/your/audio_files
    output_file: /path/to/your/labels.json
```

### 3. Running the App

```bash
python run.py --config config/default.yaml
```

The app will be available at `http://127.0.0.1:8050` by default.

## 🛠 Project Structure

*   `app/`: Core application logic.
    *   `callbacks/`: Dash callback functions.
    *   `components/`: Reusable UI components (Audio players, Modals, Cards).
    *   `utils/`: Data processing, image rendering, and file I/O utilities.
*   `assets/`: Custom CSS and clientside JavaScript.
*   `config/`: YAML configuration files.
*   `scripts/`: Utility scripts for data management and testing.
*   `taxonomy/`: Hierarchical label definitions.

## 🧪 Testing

Run the test suite to ensure everything is working correctly:

```bash
pytest
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
