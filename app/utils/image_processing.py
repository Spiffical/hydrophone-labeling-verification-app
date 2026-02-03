import base64
from io import BytesIO
import logging
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import plotly.graph_objects as go
import scipy.io as sio
from cachetools import LRUCache, cached

from app.utils.colmap_hyd import colmap_hyd_py

logger = logging.getLogger(__name__)

spectrogram_cache = LRUCache(maxsize=400)
image_cache = LRUCache(maxsize=800)


def _resize_cache(cache: LRUCache, maxsize: int) -> None:
    cache.clear()
    if hasattr(cache, "_Cache__maxsize"):
        cache._Cache__maxsize = maxsize
        return
    if hasattr(cache, "_LRUCache__maxsize"):
        cache._LRUCache__maxsize = maxsize
        return
    try:
        cache.maxsize = maxsize
    except AttributeError:
        pass


def set_cache_sizes(maxsize: int) -> None:
    try:
        maxsize = int(maxsize)
    except (TypeError, ValueError):
        maxsize = 400
    maxsize = max(1, maxsize)
    _resize_cache(spectrogram_cache, maxsize)
    _resize_cache(image_cache, maxsize * 2)


def _load_mat(mat_path: str):
    try:
        mat_data = sio.loadmat(mat_path)
    except Exception as exc:
        logger.error("Error loading %s: %s", mat_path, exc)
        return None

    # Try new format first (from whale-call-analysis download script)
    if "PdB_norm" in mat_data or "P" in mat_data:
        psd = mat_data.get("PdB_norm", mat_data.get("P"))
        freq = mat_data.get("F", np.array([[0]]))
        time = mat_data.get("T", np.array([[0]]))
        
        # Handle different array shapes
        psd = np.squeeze(psd)
        freq = np.squeeze(freq)
        time = np.squeeze(time)
        
        # Handle NaN and inf values
        psd = np.nan_to_num(psd, nan=0.0, neginf=0.0, posinf=0.0)
        
        return {"psd": psd, "freq": freq, "time": time}

    # Try ONC SpectData format
    if "SpectData" in mat_data:
        data = mat_data["SpectData"]
        psd = data["PSD"][0, 0]
        freq = data["frequency"][0, 0].flatten()
        time = data["time"][0, 0].flatten()

        valid_mask = (psd != -np.inf)
        psd[~valid_mask] = 0
        psd = np.nan_to_num(psd, nan=0.0)

        return {"psd": psd, "freq": freq, "time": time}
    
    logger.warning("Unknown MAT format for %s, keys: %s", mat_path, list(mat_data.keys()))
    return None


@cached(spectrogram_cache)
def load_spectrogram_cached(mat_path: str):
    if not mat_path or not os.path.exists(mat_path):
        return None
    return _load_mat(mat_path)


def generate_image_cached(mat_path: str, colormap: str = "default", y_axis_scale: str = "linear"):
    cache_key = (mat_path, colormap, y_axis_scale)
    if cache_key in image_cache:
        return image_cache[cache_key]

    result = _generate_image(mat_path, colormap, y_axis_scale)
    image_cache[cache_key] = result
    return result


def _generate_image(mat_path: str, colormap: str = "default", y_axis_scale: str = "linear"):
    spectrogram = load_spectrogram_cached(mat_path)
    if spectrogram is None:
        return None

    fig, ax = plt.subplots(figsize=(1.5, 1.5), facecolor="none")
    if colormap == "hydrophone":
        cmap_array = colmap_hyd_py(36, 3)
        cmap = mcolors.ListedColormap(cmap_array)
    else:
        cmap = "viridis"

    psd = spectrogram["psd"]
    freq = spectrogram["freq"]
    time = spectrogram["time"]
    
    # Normalize time to start from 0 for proper display
    if len(time) > 0 and time[0] > 1000:
        # Julian days - convert to minutes relative to start
        time_plot = (time - time[0]) * 24 * 60
    else:
        # Seconds - normalize to start from 0
        time_plot = time - time[0] if len(time) > 0 else time
    
    # Detect if frequency needs scaling (already in Hz vs kHz)
    # If max freq > 1000, it's likely Hz; otherwise might already be kHz
    if len(freq) > 0 and freq[-1] > 500:
        # Frequency is in Hz - keep as is for display
        freq_plot = freq
    else:
        # Frequency might be in kHz - convert to Hz for consistency
        freq_plot = freq * 1000 if np.max(freq) < 1 else freq
    
    # Determine appropriate color limits based on data range
    psd_valid = psd[np.isfinite(psd)]
    if len(psd_valid) > 0:
        # Use percentile-based limits for better visualization
        vmin = np.percentile(psd_valid, 2)
        vmax = np.percentile(psd_valid, 98)
        # Ensure some contrast
        if vmax - vmin < 0.1:
            vmin = np.min(psd_valid)
            vmax = np.max(psd_valid)
    else:
        vmin, vmax = -60, 0  # Default dB range

    if y_axis_scale == "log":
        valid_freq_mask = freq_plot > 0
        if not np.any(valid_freq_mask):
            ax.imshow(psd,
                      extent=[time_plot[0], time_plot[-1], freq_plot[0], freq_plot[-1]],
                      aspect="auto", origin="lower", cmap=cmap, vmin=vmin, vmax=vmax)
        else:
            freq_for_plot = freq_plot[valid_freq_mask]
            psd_for_plot = psd[valid_freq_mask, :]
            min_freq = max(freq_for_plot[0], 0.1)
            max_freq = freq_for_plot[-1]
            ax.imshow(psd_for_plot,
                      extent=[time_plot[0], time_plot[-1], min_freq, max_freq],
                      aspect="auto", origin="lower", cmap=cmap, vmin=vmin, vmax=vmax)
            ax.set_yscale("log")
            ax.set_ylim(min_freq, max_freq)
    else:
        extent = [
            time_plot[0] if len(time_plot) > 0 else 0,
            time_plot[-1] if len(time_plot) > 0 else 1,
            freq_plot[0] if len(freq_plot) > 0 else 0,
            freq_plot[-1] if len(freq_plot) > 0 else 1
        ]
        ax.imshow(psd,
                  extent=extent,
                  aspect="auto", origin="lower", cmap=cmap, vmin=vmin, vmax=vmax)

    ax.axis("off")
    ax.set_position([0, 0, 1, 1])

    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0,
                facecolor="none", edgecolor="none", dpi=72)
    plt.close(fig)
    data = base64.b64encode(buf.getbuffer()).decode("utf8")
    return f"data:image/png;base64,{data}"


def create_spectrogram_figure(spectrogram_data, colormap_value, y_axis_scale="linear"):
    if spectrogram_data is None:
        return go.Figure()

    psd = spectrogram_data["psd"]
    freq = spectrogram_data["freq"]
    time = spectrogram_data["time"]

    # Normalize time to start from 0 for better visualization
    # This shows the spectrogram window duration rather than position in source file
    if len(time) > 0 and time[0] > 1000:
        # Julian days - convert to minutes relative to start
        time_plot = (time - time[0]) * 24 * 60
        x_label = "Time (minutes)"
    else:
        # Seconds - normalize to start from 0
        time_plot = time - time[0] if len(time) > 0 else time
        x_label = "Time (seconds)"

    # Intelligent frequency unit detection and scaling
    if len(freq) > 0:
        max_f = np.max(freq)
        if max_f > 1000:
            # Data is in Hz and has a high range -> convert to kHz for better readability
            freq_plot = freq / 1000
            y_unit = "kHz"
        elif max_f > 2:
            # Data is likely already in the correct range (e.g., 0-100 Hz or 0-100 kHz)
            # For low-frequency baleen whale data (5-100), we show it as Hz
            # If it were high frequency already in kHz, 100 kHz is also a common range.
            # We'll use Hz as the unit if max_f is between 2 and 1000, 
            # assuming baleen whale context or that the values represent the actual Hz.
            freq_plot = freq
            y_unit = "Hz" if max_f < 1000 else "kHz"
        else:
            # Very small values -> likely already in kHz
            freq_plot = freq
            y_unit = "kHz"
    else:
        freq_plot = freq
        y_unit = "Hz"

    # Determine appropriate color limits
    psd_valid = psd[np.isfinite(psd)]
    if len(psd_valid) > 0:
        zmin = np.percentile(psd_valid, 2)
        zmax = np.percentile(psd_valid, 98)
    else:
        zmin, zmax = -60, 0

    if colormap_value == "hydrophone":
        cmap_array = colmap_hyd_py(36, 3)
        colorscale = [[i / (len(cmap_array) - 1),
                       f"rgb({int(r*255)},{int(g*255)},{int(b*255)})"]
                      for i, (r, g, b) in enumerate(cmap_array)]
    else:
        colorscale = "Viridis"

    if y_axis_scale == "log":
        y_axis_type = "log"
        y_axis_title = f"Frequency ({y_unit}) - Log Scale"
        # Ensure values for log scale are positive
        freq_plot = np.maximum(freq_plot, 0.001 if y_unit == "kHz" else 0.1)
    else:
        y_axis_type = "linear"
        y_axis_title = f"Frequency ({y_unit})"

    fig = go.Figure()
    fig.add_trace(go.Heatmap(
        z=psd,
        x=time_plot,
        y=freq_plot,
        colorscale=colorscale,
        zmin=zmin,
        zmax=zmax,
        colorbar=dict(title="dB/Hz")
    ))

    # Add invisible playback position marker (will be controlled via JavaScript)
    fig.add_shape(
        type="line",
        x0=0, x1=0,
        y0=0, y1=1,
        yref="paper",
        line=dict(
            color="rgba(255, 0, 0, 0)",
            width=2,
            dash="solid"
        ),
        name="playback-marker"
    )
    
    fig.update_layout(
        xaxis=dict(title=x_label, showgrid=True, tickformat=".2f"),
        yaxis=dict(title=y_axis_title, showgrid=True, type=y_axis_type),
        margin=dict(l=40, r=20, t=20, b=40),
        height=500,
        template="plotly_white",
        uirevision='constant'
    )

    return fig
