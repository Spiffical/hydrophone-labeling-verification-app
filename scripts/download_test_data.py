#!/usr/bin/env python3
"""
Download Test Data for Labeling Verification App

Downloads a small sample of audio data and generates spectrograms
for testing the labeling verification interface.

Usage:
    python scripts/download_test_data.py --hours 1
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import numpy as np
import scipy.io
import soundfile as sf
from dotenv import load_dotenv

# Try to import from the whale-call-analysis package
WHALE_ANALYSIS_ROOT = Path(__file__).resolve().parents[2] / "whale-call-analysis"
if str(WHALE_ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(WHALE_ANALYSIS_ROOT))

try:
    from onc_hydrophone_data.data.hydrophone_downloader import HydrophoneDownloader
    from onc_hydrophone_data.audio.spectrogram_generator import SpectrogramGenerator
except ImportError:
    print("Error: Could not import onc_hydrophone_data package.")
    print("Please install it or run from the whale-call-analysis environment.")
    sys.exit(1)


def compute_segment_windows(
    audio_duration: float,
    context_duration: float,
    min_overlap: float = 0.5
) -> List[Tuple[float, float]]:
    """Compute segment windows that cleanly fit in audio file."""
    windows = []
    
    if context_duration >= audio_duration:
        return [(0.0, min(context_duration, audio_duration))]
    
    n_segments = int(np.ceil(audio_duration / context_duration))
    
    if n_segments > 1:
        total_segment_time = n_segments * context_duration
        total_overlap_needed = total_segment_time - audio_duration
        overlap_per_gap = total_overlap_needed / (n_segments - 1)
        overlap = max(overlap_per_gap, min_overlap)
        step = context_duration - overlap
        
        current = 0.0
        while current + context_duration <= audio_duration + 0.001:
            windows.append((current, current + context_duration))
            current += step
            if len(windows) > 100:
                break
    else:
        windows.append((0.0, context_duration))
    
    return windows


def extract_timestamp_from_filename(filename: str) -> Optional[datetime]:
    """Extract timestamp from ONC audio filename."""
    try:
        base = Path(filename).stem
        parts = base.split('_')
        if len(parts) >= 2:
            ts_str = parts[1].replace('Z', '')
            if '.' in ts_str:
                ts_str = ts_str.split('.')[0]
            dt = datetime.strptime(ts_str[:15], '%Y%m%dT%H%M%S')
            return dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Download test data for labeling verification app"
    )
    parser.add_argument('--device-code', type=str, default='ICLISTENHF1951',
                        help='ONC device code (default: ICLISTENHF1951)')
    parser.add_argument('--hours', type=float, default=1.0,
                        help='Hours of data to download (default: 1)')
    parser.add_argument('--start-date', type=str, default=None,
                        help='Start date (ISO format). Default: 2025-01-01T00:00:00Z')
    parser.add_argument('--context-duration', type=float, default=40.0,
                        help='Segment duration in seconds (default: 40)')
    parser.add_argument('--save-png', action='store_true',
                        help='Also save PNG spectrogram images')
    parser.add_argument('--save-audio', action='store_true',
                        help='Also save audio segment files')
    
    args = parser.parse_args()
    
    # Load environment
    env_paths = [
        Path(__file__).parent.parent / '.env',
        WHALE_ANALYSIS_ROOT / '.env',
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break
    
    onc_token = os.getenv('ONC_TOKEN')
    if not onc_token:
        print("Error: ONC_TOKEN not found in .env file")
        print("Please create a .env file with your ONC API token:")
        print("  ONC_TOKEN=your_token_here")
        sys.exit(1)
    
    # Parse dates
    if args.start_date:
        start_dt = datetime.fromisoformat(args.start_date.replace('Z', '+00:00'))
    else:
        start_dt = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    
    end_dt = start_dt + timedelta(hours=args.hours)
    
    print("=" * 60)
    print("DOWNLOADING TEST DATA FOR LABELING VERIFICATION APP")
    print("=" * 60)
    print(f"Device: {args.device_code}")
    print(f"Date range: {start_dt.isoformat()} to {end_dt.isoformat()}")
    print(f"Duration: {args.hours} hour(s)")
    print()
    
    # Setup output directories
    output_dir = Path(__file__).parent.parent / 'data' / 'test_dataset'
    mat_dir = output_dir / 'mat_files'
    mat_dir.mkdir(parents=True, exist_ok=True)
    
    png_dir = output_dir / 'spectrograms' if args.save_png else None
    audio_dir = output_dir / 'audio' if args.save_audio else None
    
    if png_dir:
        png_dir.mkdir(parents=True, exist_ok=True)
    if audio_dir:
        audio_dir.mkdir(parents=True, exist_ok=True)
    
    # Spectrogram parameters
    context_duration = args.context_duration
    window_duration = 1.0
    overlap = 0.9
    freq_min = 5
    freq_max = 100
    colormap = 'viridis'
    
    print(f"Spectrogram config:")
    print(f"  Context duration: {context_duration}s")
    print(f"  Window duration: {window_duration}s, Overlap: {overlap}")
    print(f"  Frequency range: {freq_min}-{freq_max} Hz")
    print()
    
    # Initialize spectrogram generator
    spec_gen = SpectrogramGenerator(
        win_dur=window_duration,
        overlap=overlap,
        freq_lims=(freq_min, freq_max),
        log_freq=False,
        clim=(-60, 0),
        colormap=colormap
    )
    
    # Initialize downloader
    downloader = HydrophoneDownloader(onc_token, str(output_dir))
    
    # Download audio files
    print("-" * 60)
    print("DOWNLOADING AUDIO FILES")
    print("-" * 60)
    
    try:
        start_str = start_dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        end_str = end_dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        
        downloader.download_flac_files(
            args.device_code,
            start_str,
            end_str
        )
        
        print("Audio download complete!")
    except Exception as e:
        print(f"Download error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Find downloaded audio files
    import glob
    audio_patterns = [
        str(output_dir / '**/*.flac'),
        str(output_dir / '**/*.wav'),
    ]
    audio_files = []
    for pattern in audio_patterns:
        audio_files.extend(glob.glob(pattern, recursive=True))
    
    audio_files = sorted(set(audio_files))
    print(f"Found {len(audio_files)} audio files to process")
    
    if not audio_files:
        print("No audio files found! Check your ONC token and date range.")
        sys.exit(1)
    
    # Process files
    print()
    print("-" * 60)
    print("GENERATING SPECTROGRAMS")
    print("-" * 60)
    
    processed_files = []
    failed_files = []
    
    for audio_idx, audio_path in enumerate(audio_files):
        audio_path = Path(audio_path)
        print(f"Processing {audio_idx + 1}/{len(audio_files)}: {audio_path.name}")
        
        try:
            # Load audio
            audio_data, sample_rate = sf.read(str(audio_path))
            audio_duration = len(audio_data) / sample_rate
            
            # Extract timestamp
            file_timestamp = extract_timestamp_from_filename(audio_path.name)
            if file_timestamp is None:
                file_timestamp = datetime.now(timezone.utc)
            
            # Compute segment windows
            windows = compute_segment_windows(audio_duration, context_duration)
            
            print(f"  Audio: {audio_duration:.1f}s @ {sample_rate}Hz, {len(windows)} segments")
            
            for seg_idx, (start_sec, end_sec) in enumerate(windows):
                # Extract segment
                start_sample = int(start_sec * sample_rate)
                end_sample = int(end_sec * sample_rate)
                segment = audio_data[start_sample:end_sample]
                
                # Ensure exact length
                expected_samples = int(context_duration * sample_rate)
                if len(segment) < expected_samples:
                    segment = np.pad(segment, (0, expected_samples - len(segment)))
                elif len(segment) > expected_samples:
                    segment = segment[:expected_samples]
                
                # Create file ID
                file_id = f"{audio_path.stem}_seg{seg_idx:03d}"
                seg_timestamp = file_timestamp + timedelta(seconds=start_sec)
                
                # Generate spectrogram
                freqs, times, Sxx, power_db = spec_gen.compute_spectrogram(segment, sample_rate)
                
                # Crop to frequency range
                freq_mask = (freqs >= freq_min) & (freqs <= freq_max)
                freq_indices = np.where(freq_mask)[0]
                if len(freq_indices) > 0:
                    f_start = freq_indices[0]
                    f_end = freq_indices[-1] + 1
                    freqs_cropped = freqs[f_start:f_end]
                    Sxx_cropped = Sxx[f_start:f_end, :]
                    power_db_cropped = power_db[f_start:f_end, :]
                else:
                    freqs_cropped = freqs
                    Sxx_cropped = Sxx
                    power_db_cropped = power_db
                
                # Save MAT file
                mat_path = mat_dir / f"{file_id}.mat"
                scipy.io.savemat(str(mat_path), {
                    'F': freqs_cropped,
                    'T': times,
                    'P': Sxx_cropped,
                    'PdB_norm': power_db_cropped,
                    'freq_min': freq_min,
                    'freq_max': freq_max,
                    'sample_rate': sample_rate,
                    'context_duration': context_duration,
                })
                
                # Save PNG if requested
                png_path = None
                if args.save_png and png_dir:
                    png_path = png_dir / f"{file_id}.png"
                    spec_gen.plot_spectrogram(
                        freqs_cropped, times, power_db_cropped,
                        title=f"{args.device_code}: {seg_timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                        save_path=png_path
                    )
                    import matplotlib.pyplot as plt
                    plt.close('all')
                
                # Save audio segment if requested
                seg_audio_path = None
                if args.save_audio and audio_dir:
                    seg_audio_path = audio_dir / f"{file_id}.wav"
                    sf.write(str(seg_audio_path), segment, sample_rate)
                
                processed_files.append({
                    "item_id": file_id,
                    "spectrogram_path": str(mat_path),
                    "audio_file": str(seg_audio_path) if seg_audio_path else None,
                    "source_audio": audio_path.name,
                    "segment_index": seg_idx,
                    "segment_start_sec": start_sec,
                    "segment_end_sec": end_sec,
                    "timestamp": seg_timestamp.isoformat(),
                })
                
        except Exception as e:
            failed_files.append({"file": str(audio_path), "error": str(e)})
            print(f"  Failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Save labels file for the labeling app
    labels_data = {
        "version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_source": {
            "device_code": args.device_code,
            "date_from": start_dt.isoformat(),
            "date_to": end_dt.isoformat(),
        },
        "items": []
    }
    
    for item in processed_files:
        labels_data["items"].append({
            "item_id": item["item_id"],
            "spectrogram_path": item["spectrogram_path"],
            "audio_file": item.get("audio_file"),
            "metadata": {
                "source_audio": item["source_audio"],
                "segment_index": item["segment_index"],
                "timestamp": item["timestamp"],
            },
            "annotations": {
                "labels": [],
                "annotated_by": None,
                "annotated_at": None,
            }
        })
    
    labels_path = output_dir / "labels.json"
    with open(labels_path, 'w') as f:
        json.dump(labels_data, f, indent=2)
    
    print()
    print("=" * 60)
    print("DOWNLOAD COMPLETE")
    print("=" * 60)
    print(f"Processed: {len(processed_files)} segments from {len(audio_files)} audio files")
    print(f"Failed: {len(failed_files)} files")
    print()
    print(f"Data saved to: {output_dir}")
    print(f"  MAT files: {mat_dir}")
    print(f"  Labels: {labels_path}")
    if png_dir:
        print(f"  PNG files: {png_dir}")
    if audio_dir:
        print(f"  Audio files: {audio_dir}")
    print()
    print("To use with labeling app, update config/label_config.yaml:")
    print(f"  folder: {mat_dir}")
    print(f"  output_file: {labels_path}")
    if audio_dir:
        print(f"  audio_folder: {audio_dir}")


if __name__ == "__main__":
    main()
