#!/usr/bin/env python3
"""
Regenerate spectrograms from existing FLAC files with temporal padding.
"""
import sys
from pathlib import Path
import numpy as np
import scipy.io
import soundfile as sf
from datetime import datetime, timedelta, timezone
import json

# Add whale-call-analysis to path
sys.path.insert(0, '/home/sbialek/ONC/whale-call-analysis')
from onc_hydrophone_data.audio.spectrogram_generator import SpectrogramGenerator

# Configuration
FLAC_DIR = Path('/home/sbialek/ONC/labeling-verification-app/data/test_dataset/flac')
OUTPUT_DIR = Path('/home/sbialek/ONC/labeling-verification-app/data/test_dataset')
MAT_DIR = OUTPUT_DIR / 'mat_files'
AUDIO_DIR = OUTPUT_DIR / 'audio'
PNG_DIR = OUTPUT_DIR / 'spectrograms'

# Spectrogram parameters
CONTEXT_DURATION = 40.0  # seconds
TEMPORAL_PADDING = 2.0   # seconds
WINDOW_DURATION = 1.0
OVERLAP = 0.9
FREQ_MIN = 5
FREQ_MAX = 100

print("=" * 70)
print("REGENERATING SPECTROGRAMS WITH TEMPORAL PADDING")
print("=" * 70)
print(f"Source: {FLAC_DIR}")
print(f"Output: {OUTPUT_DIR}")
print(f"Context duration: {CONTEXT_DURATION}s")
print(f"Temporal padding: {TEMPORAL_PADDING}s (eliminates edge effects)")
print(f"Window: {WINDOW_DURATION}s, Overlap: {OVERLAP}")
print(f"Freq range: {FREQ_MIN}-{FREQ_MAX} Hz")
print()

# Initialize spectrogram generator
spec_gen = SpectrogramGenerator(
    win_dur=WINDOW_DURATION,
    overlap=OVERLAP,
    freq_lims=(FREQ_MIN, FREQ_MAX),
    log_freq=False,
    clim=(-60, 0),
    colormap='viridis'
)

# Process each FLAC file
flac_files = sorted(FLAC_DIR.glob('*.flac'))
print(f"Found {len(flac_files)} FLAC files to process\n")

total_segments = 0

for flac_idx, flac_path in enumerate(flac_files):
    print(f"[{flac_idx+1}/{len(flac_files)}] Processing {flac_path.name}...")
    
    # Load audio
    audio_data, sample_rate = sf.read(str(flac_path))
    audio_duration = len(audio_data) / sample_rate
    
    # Calculate number of segments
    n_segments = int(np.ceil(audio_duration / CONTEXT_DURATION))
    
    print(f"  Duration: {audio_duration:.1f}s @ {sample_rate}Hz → {n_segments} segments")
    
    for seg_idx in range(n_segments):
        start_sec = seg_idx * CONTEXT_DURATION
        end_sec = min(start_sec + CONTEXT_DURATION, audio_duration)
        
        # Add temporal padding
        padded_start_sec = max(0, start_sec - TEMPORAL_PADDING)
        padded_end_sec = min(audio_duration, end_sec + TEMPORAL_PADDING)
        
        # Extract padded segment
        padded_start_sample = int(padded_start_sec * sample_rate)
        padded_end_sample = int(padded_end_sec * sample_rate)
        padded_segment = audio_data[padded_start_sample:padded_end_sample]
        
        # Track actual padding
        actual_padding_before = start_sec - padded_start_sec
        actual_padding_after = padded_end_sec - end_sec
        
        # Generate spectrogram on padded audio
        freqs, times, Sxx, power_db = spec_gen.compute_spectrogram(padded_segment, sample_rate)
        
        # Trim spectrogram to target range
        target_start_time = actual_padding_before
        target_end_time = actual_padding_before + CONTEXT_DURATION
        
        target_mask = (times >= target_start_time) & (times <= target_end_time)
        time_indices = np.where(target_mask)[0]
        
        if len(time_indices) == 0:
            print(f"    Warning: No valid time indices for segment {seg_idx}")
            continue
        
        # Trim to target
        times_trimmed = times[time_indices] - actual_padding_before
        Sxx_trimmed = Sxx[:, time_indices]
        power_db_trimmed = power_db[:, time_indices]
        
        # Crop to frequency range
        freq_mask = (freqs >= FREQ_MIN) & (freqs <= FREQ_MAX)
        freq_indices = np.where(freq_mask)[0]
        
        if len(freq_indices) > 0:
            freqs_cropped = freqs[freq_indices]
            Sxx_cropped = Sxx_trimmed[freq_indices, :]
            power_db_cropped = power_db_trimmed[freq_indices, :]
        else:
            freqs_cropped = freqs
            Sxx_cropped = Sxx_trimmed
            power_db_cropped = power_db_trimmed
        
        # Create file ID
        file_id = f"{flac_path.stem}_seg{seg_idx:03d}"
        
        # Save MAT file
        mat_path = MAT_DIR / f"{file_id}.mat"
        scipy.io.savemat(str(mat_path), {
            'F': freqs_cropped,
            'T': times_trimmed,
            'P': Sxx_cropped,
            'PdB_norm': power_db_cropped,
            'freq_min': FREQ_MIN,
            'freq_max': FREQ_MAX,
            'sample_rate': sample_rate,
            'context_duration': CONTEXT_DURATION,
            'temporal_padding_used': TEMPORAL_PADDING,
        })
        
        # Save PNG
        png_path = PNG_DIR / f"{file_id}.png"
        spec_gen.plot_spectrogram(
            freqs_cropped, times_trimmed, power_db_cropped,
            title=f"Segment {seg_idx} (with padding)",
            save_path=png_path
        )
        
        # Save audio segment
        target_start_sample = int(start_sec * sample_rate)
        target_end_sample = int(end_sec * sample_rate)
        target_segment = audio_data[target_start_sample:target_end_sample]
        
        # Ensure exact length
        expected_samples = int(CONTEXT_DURATION * sample_rate)
        if len(target_segment) < expected_samples:
            target_segment = np.pad(target_segment, (0, expected_samples - len(target_segment)))
        elif len(target_segment) > expected_samples:
            target_segment = target_segment[:expected_samples]
        
        audio_path = AUDIO_DIR / f"{file_id}.wav"
        sf.write(str(audio_path), target_segment, sample_rate)
        
        total_segments += 1
    
    # Clean up matplotlib figures
    import matplotlib.pyplot as plt
    plt.close('all')

print()
print("=" * 70)
print(f"✅ COMPLETE: Generated {total_segments} segments from {len(flac_files)} files")
print(f"   MAT files: {MAT_DIR}")
print(f"   PNG files: {PNG_DIR}")
print(f"   Audio files: {AUDIO_DIR}")
print("=" * 70)
