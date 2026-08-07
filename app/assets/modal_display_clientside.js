(function () {
  const matrixCache = new Map();
  const renderState = {
    sequence: 0,
    activeObjectUrl: null,
  };
  const rasterPreviewState = {
    generation: 0,
    active: false,
    pending: null,
  };

  function noUpdate() {
    return (window.dash_clientside || {}).no_update;
  }

  function numeric(value) {
    if (value === null || value === undefined || value === '') {
      return null;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function triggeredId() {
    const context = (window.dash_clientside || {}).callback_context;
    return context && context.triggered_id;
  }

  function startViewRefresh(_colormap, _yAxisScale) {
    const trigger = triggeredId();
    if (trigger !== 'modal-colormap-toggle' && trigger !== 'modal-y-axis-toggle') {
      return noUpdate();
    }
    cancelRasterPreviews();
    renderState.sequence += 1;
    return true;
  }

  function modeValue(mode, labelValue, verifyValue, exploreValue) {
    if (mode === 'verify') return verifyValue;
    if (mode === 'explore') return exploreValue;
    return labelValue;
  }

  function cloneFigure(figure) {
    const data = Array.isArray(figure.data) ? figure.data.slice() : [];
    if (data.length) {
      data[0] = Object.assign({}, data[0]);
    }
    return Object.assign({}, figure, {
      data,
      layout: Object.assign({}, figure.layout || {}, {
        meta: Object.assign({}, (figure.layout || {}).meta || {}),
        xaxis: Object.assign({}, (figure.layout || {}).xaxis || {}),
        yaxis: Object.assign({}, (figure.layout || {}).yaxis || {}),
        images: Array.isArray((figure.layout || {}).images)
          ? figure.layout.images.map((entry) => Object.assign({}, entry))
          : [],
      }),
    });
  }

  function resolveFrequencyWindow(meta, yAxisScale, requestedMin, requestedMax) {
    const dataMax = numeric(meta.data_y_max_hz) || 1.0;
    const dataMin = yAxisScale === 'log'
      ? (numeric(meta.positive_y_min_hz) || 0.001)
      : (numeric(meta.data_y_min_hz) || 0.0);
    let lower = numeric(requestedMin);
    let upper = numeric(requestedMax);
    lower = Math.max(dataMin, Math.min(dataMax, lower === null ? dataMin : lower));
    upper = Math.max(dataMin, Math.min(dataMax, upper === null ? dataMax : upper));
    if (upper <= lower) {
      lower = dataMin;
      upper = dataMax;
    }
    if (upper <= lower) {
      upper = yAxisScale === 'log' ? lower * 10.0 : lower + 1.0;
    }
    return [lower, upper];
  }

  function resolveContrast(meta, requestedMin, requestedMax) {
    const autoMin = numeric(meta.auto_color_min) || 0.0;
    const autoMax = numeric(meta.auto_color_max) || (autoMin + 1.0);
    let lower = numeric(requestedMin);
    let upper = numeric(requestedMax);
    lower = lower === null ? autoMin : lower;
    upper = upper === null ? autoMax : upper;
    if (upper <= lower) {
      lower = autoMin;
      upper = autoMax;
    }
    if (upper <= lower) {
      upper = lower + 1.0;
    }
    return [lower, upper];
  }

  function applyFrequencyWindow(figure, yAxisScale, lowerHz, upperHz) {
    const meta = figure.layout.meta;
    const yToHz = numeric(meta.y_to_hz) || 1.0;
    const lowerPlot = lowerHz / yToHz;
    const upperPlot = upperHz / yToHz;
    figure.layout.yaxis.type = yAxisScale === 'log' ? 'log' : 'linear';
    figure.layout.yaxis.range = yAxisScale === 'log'
      ? [Math.log10(lowerPlot), Math.log10(upperPlot)]
      : [lowerPlot, upperPlot];
    meta.display_y_min_hz = lowerHz;
    meta.display_y_max_hz = upperHz;
    meta.y_min = lowerPlot;
    meta.y_max = upperPlot;
    meta.local_display_update_sequence = renderState.sequence;
  }

  function loadMatrix(url) {
    if (!url) {
      return Promise.reject(new Error('No modal spectrogram data URL is available.'));
    }
    if (matrixCache.has(url)) {
      return matrixCache.get(url);
    }
    const promise = fetch(url, { credentials: 'same-origin', cache: 'force-cache' })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Modal data request failed with HTTP ${response.status}.`);
        }
        const rows = Number(response.headers.get('X-Spectrogram-Rows'));
        const columns = Number(response.headers.get('X-Spectrogram-Columns'));
        return response.arrayBuffer().then((buffer) => {
          if (!rows || !columns || buffer.byteLength !== rows * columns * 4) {
            throw new Error('Modal spectrogram data response has an invalid shape.');
          }
          return { rows, columns, values: new Float32Array(buffer) };
        });
      })
      .catch((error) => {
        matrixCache.delete(url);
        throw error;
      });
    matrixCache.set(url, promise);
    while (matrixCache.size > 3) {
      const oldestKey = matrixCache.keys().next().value;
      if (oldestKey !== url) matrixCache.delete(oldestKey);
      else break;
    }
    return promise;
  }

  function renderMatrix(matrix, palette, paletteMode, zmin, zmax) {
    const canvas = document.createElement('canvas');
    canvas.width = matrix.columns;
    canvas.height = matrix.rows;
    const context = canvas.getContext('2d', { alpha: true });
    const image = context.createImageData(matrix.columns, matrix.rows);
    const output = image.data;
    const colors = Array.isArray(palette) && palette.length ? palette : [[0, 0, 0], [255, 255, 255]];
    const span = Math.max(1e-9, zmax - zmin);
    const lastColor = colors.length - 1;

    for (let targetRow = 0; targetRow < matrix.rows; targetRow += 1) {
      const sourceRow = matrix.rows - targetRow - 1;
      let sourceIndex = sourceRow * matrix.columns;
      let targetIndex = targetRow * matrix.columns * 4;
      for (let column = 0; column < matrix.columns; column += 1) {
        const value = matrix.values[sourceIndex];
        if (!Number.isFinite(value)) {
          output[targetIndex + 3] = 0;
        } else {
          const normalized = Math.max(0.0, Math.min(1.0, (value - zmin) / span));
          if (paletteMode === 'listed') {
            const color = colors[Math.min(lastColor, Math.floor(normalized * colors.length))];
            output[targetIndex] = color[0];
            output[targetIndex + 1] = color[1];
            output[targetIndex + 2] = color[2];
          } else {
            const palettePosition = normalized * lastColor;
            const lowerIndex = Math.floor(palettePosition);
            const upperIndex = Math.min(lastColor, lowerIndex + 1);
            const fraction = palettePosition - lowerIndex;
            const lowerColor = colors[lowerIndex];
            const upperColor = colors[upperIndex];
            output[targetIndex] = Math.round(lowerColor[0] + ((upperColor[0] - lowerColor[0]) * fraction));
            output[targetIndex + 1] = Math.round(lowerColor[1] + ((upperColor[1] - lowerColor[1]) * fraction));
            output[targetIndex + 2] = Math.round(lowerColor[2] + ((upperColor[2] - lowerColor[2]) * fraction));
          }
          output[targetIndex + 3] = 255;
        }
        sourceIndex += 1;
        targetIndex += 4;
      }
    }
    context.putImageData(image, 0, 0);
    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error('Could not encode the modal spectrogram image.'));
          return;
        }
        resolve(URL.createObjectURL(blob));
      }, 'image/png');
    });
  }

  function activateRasterObjectUrl(objectUrl) {
    const previousUrl = renderState.activeObjectUrl;
    renderState.activeObjectUrl = objectUrl;
    if (previousUrl) {
      window.setTimeout(() => URL.revokeObjectURL(previousUrl), 5000);
    }
  }

  function cancelRasterPreviews() {
    rasterPreviewState.generation += 1;
    rasterPreviewState.pending = null;
  }

  function applyRasterPreviewToPlot(objectUrl, zmin, zmax, localSequence) {
    const graph = document.querySelector('#modal-image-graph .js-plotly-plot');
    if (!graph || !window.Plotly || !graph.layout || !Array.isArray(graph.layout.images)) {
      URL.revokeObjectURL(objectUrl);
      return;
    }
    activateRasterObjectUrl(objectUrl);
    if (graph.layout.meta) {
      graph.layout.meta.display_color_min = zmin;
      graph.layout.meta.display_color_max = zmax;
      graph.layout.meta.local_display_update_sequence = localSequence;
    }
    if (graph.data && graph.data.length) {
      graph.data[0].zmin = zmin;
      graph.data[0].zmax = zmax;
    }
    window.Plotly.relayout(graph, { 'images[0].source': objectUrl });
    window.Plotly.restyle(graph, { zmin: [zmin], zmax: [zmax] }, [0]);
  }

  function drainRasterPreviewQueue() {
    if (rasterPreviewState.active || !rasterPreviewState.pending) return;
    const job = rasterPreviewState.pending;
    rasterPreviewState.pending = null;
    rasterPreviewState.active = true;
    loadMatrix(job.dataUrl)
      .then((matrix) => renderMatrix(
        matrix,
        job.palette,
        job.paletteMode,
        job.zmin,
        job.zmax,
      ))
      .then((objectUrl) => {
        if (job.generation !== rasterPreviewState.generation) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        applyRasterPreviewToPlot(
          objectUrl,
          job.zmin,
          job.zmax,
          job.localSequence,
        );
      })
      .catch((error) => {
        if (job.generation === rasterPreviewState.generation) {
          console.warn('[modal-display] browser preview recolor failed', error);
        }
      })
      .finally(() => {
        rasterPreviewState.active = false;
        drainRasterPreviewQueue();
      });
  }

  function queueRasterPreview(meta, zmin, zmax) {
    rasterPreviewState.pending = {
      generation: rasterPreviewState.generation,
      localSequence: ++renderState.sequence,
      dataUrl: meta.modal_data_url,
      palette: meta.raster_palette,
      paletteMode: meta.raster_palette_mode,
      zmin,
      zmax,
    };
    drainRasterPreviewQueue();
  }

  function updateTraceContrast(figure, zmin, zmax) {
    if (!figure.data.length) return;
    figure.data[0].zmin = zmin;
    figure.data[0].zmax = zmax;
    if (Array.isArray(figure.data[0].z) && figure.data[0].z.length === 1) {
      figure.data[0].z = [[zmin, zmax]];
    }
    figure.layout.meta.display_color_min = zmin;
    figure.layout.meta.display_color_max = zmax;
    figure.layout.meta.local_display_update_sequence = renderState.sequence;
  }

  function recolorRaster(figure, zmin, zmax, sequence) {
    const meta = figure.layout.meta;
    return loadMatrix(meta.modal_data_url)
      .then((matrix) => {
        if (sequence !== renderState.sequence) return noUpdate();
        return renderMatrix(
          matrix,
          meta.raster_palette,
          meta.raster_palette_mode,
          zmin,
          zmax,
        );
      })
      .then((objectUrl) => {
        if (objectUrl === noUpdate()) return objectUrl;
        if (sequence !== renderState.sequence) {
          URL.revokeObjectURL(objectUrl);
          return noUpdate();
        }
        activateRasterObjectUrl(objectUrl);
        if (figure.layout.images.length) {
          figure.layout.images[0].source = objectUrl;
        }
        updateTraceContrast(figure, zmin, zmax);
        return figure;
      })
      .catch((error) => {
        if (sequence === renderState.sequence) {
          console.warn('[modal-display] browser recolor failed', error);
        }
        return noUpdate();
      });
  }

  function updateCommitted(
    _colormap,
    yAxisScale,
    modalYMin,
    modalYMax,
    modalColorMin,
    modalColorMax,
    labelYMin,
    labelYMax,
    verifyYMin,
    verifyYMax,
    exploreYMin,
    exploreYMax,
    labelColorMin,
    labelColorMax,
    verifyColorMin,
    verifyColorMax,
    exploreColorMin,
    exploreColorMax,
    mode,
    figure
  ) {
    if (!figure || !figure.layout || !figure.layout.meta) return noUpdate();
    const trigger = triggeredId();
    if (trigger === 'modal-colormap-toggle' || trigger === 'modal-y-axis-toggle') {
      return noUpdate();
    }

    const meta = figure.layout.meta;
    const isRaster = meta.transport_mode === 'full_resolution_lossless_png';
    const currentScale = figure.layout.yaxis && figure.layout.yaxis.type === 'log' ? 'log' : 'linear';
    if (currentScale !== yAxisScale) return noUpdate();
    if (!isRaster && !['float32', 'float64'].includes(meta.transport_mode)) return noUpdate();
    const sequence = ++renderState.sequence;
    if (isRaster) cancelRasterPreviews();

    const metaPageYMin = numeric(meta.page_display_y_min_hz);
    const metaPageYMax = numeric(meta.page_display_y_max_hz);
    const inheritedYMin = metaPageYMin === null
      ? modeValue(mode, labelYMin, verifyYMin, exploreYMin)
      : metaPageYMin;
    const inheritedYMax = metaPageYMax === null
      ? modeValue(mode, labelYMax, verifyYMax, exploreYMax)
      : metaPageYMax;
    const requestedYMin = numeric(modalYMin) === null ? inheritedYMin : modalYMin;
    const requestedYMax = numeric(modalYMax) === null ? inheritedYMax : modalYMax;

    const useInheritedContrast = numeric(modalColorMin) === null && numeric(modalColorMax) === null;
    const metaPageColorMin = numeric(meta.page_display_color_min);
    const metaPageColorMax = numeric(meta.page_display_color_max);
    const requestedColorMin = useInheritedContrast
      ? (metaPageColorMin === null
        ? modeValue(mode, labelColorMin, verifyColorMin, exploreColorMin)
        : metaPageColorMin)
      : modalColorMin;
    const requestedColorMax = useInheritedContrast
      ? (metaPageColorMax === null
        ? modeValue(mode, labelColorMax, verifyColorMax, exploreColorMax)
        : metaPageColorMax)
      : modalColorMax;

    const frequency = resolveFrequencyWindow(meta, yAxisScale, requestedYMin, requestedYMax);
    const contrast = resolveContrast(meta, requestedColorMin, requestedColorMax);
    const updated = cloneFigure(figure);
    applyFrequencyWindow(updated, yAxisScale, frequency[0], frequency[1]);

    const contrastChanged = (
      Math.abs((numeric(meta.display_color_min) || 0) - contrast[0]) > 1e-6 ||
      Math.abs((numeric(meta.display_color_max) || 0) - contrast[1]) > 1e-6
    );
    const isContrastCommit = (
      trigger === 'modal-colorbar-min-input' || trigger === 'modal-colorbar-max-input'
    );
    if (!contrastChanged && !(isRaster && isContrastCommit)) return updated;

    if (!isRaster) {
      updateTraceContrast(updated, contrast[0], contrast[1]);
      return updated;
    }
    return new Promise((resolve) => window.setTimeout(resolve, 35))
      .then(() => {
        if (sequence !== renderState.sequence) return noUpdate();
        return recolorRaster(updated, contrast[0], contrast[1], sequence);
      });
  }

  function previewRanges(yDragValue, colorDragValue, yAxisScale, figure) {
    if (!figure || !figure.layout || !figure.layout.meta) return noUpdate();
    const trigger = triggeredId();
    if (trigger !== 'modal-yaxis-slider' && trigger !== 'modal-colorbar-slider') {
      return noUpdate();
    }
    const meta = figure.layout.meta;
    const isRaster = meta.transport_mode === 'full_resolution_lossless_png';
    const currentScale = figure.layout.yaxis && figure.layout.yaxis.type === 'log' ? 'log' : 'linear';
    if (currentScale !== yAxisScale) return noUpdate();
    if (!isRaster && !['float32', 'float64'].includes(meta.transport_mode)) return noUpdate();

    const updated = cloneFigure(figure);
    if (trigger === 'modal-yaxis-slider' && Array.isArray(yDragValue) && yDragValue.length === 2) {
      renderState.sequence += 1;
      const frequency = resolveFrequencyWindow(
        meta,
        yAxisScale,
        10 ** Number(yDragValue[0]),
        10 ** Number(yDragValue[1]),
      );
      applyFrequencyWindow(updated, yAxisScale, frequency[0], frequency[1]);
      return updated;
    }
    if (!Array.isArray(colorDragValue) || colorDragValue.length !== 2) return noUpdate();
    const contrast = resolveContrast(meta, colorDragValue[0], colorDragValue[1]);
    if (!isRaster) {
      renderState.sequence += 1;
      updateTraceContrast(updated, contrast[0], contrast[1]);
      return updated;
    }
    queueRasterPreview(meta, contrast[0], contrast[1]);
    return noUpdate();
  }

  function commitRasterPreview(colorValue, colormap, yAxisScale, figure) {
    if (!figure || !figure.layout || !figure.layout.meta) return noUpdate();
    if (!Array.isArray(colorValue) || colorValue.length !== 2) return noUpdate();
    const meta = figure.layout.meta;
    if (meta.transport_mode !== 'full_resolution_lossless_png') return noUpdate();
    const currentScale = figure.layout.yaxis && figure.layout.yaxis.type === 'log' ? 'log' : 'linear';
    if (currentScale !== yAxisScale) return noUpdate();
    if (meta.display_colormap && colormap && meta.display_colormap !== colormap) return noUpdate();

    cancelRasterPreviews();
    const contrast = resolveContrast(meta, colorValue[0], colorValue[1]);
    const displayedMin = numeric(meta.display_color_min);
    const displayedMax = numeric(meta.display_color_max);
    if (
      displayedMin !== null && displayedMax !== null
      && Math.abs(displayedMin - contrast[0]) <= 0.051
      && Math.abs(displayedMax - contrast[1]) <= 0.051
    ) {
      return noUpdate();
    }
    queueRasterPreview(meta, contrast[0], contrast[1]);
    return noUpdate();
  }

  function extractDisplayMeta(figure) {
    const source = figure && figure.layout && figure.layout.meta;
    if (!source) return noUpdate();
    const keys = [
      'positive_y_min_hz', 'data_y_min_hz', 'data_y_max_hz',
      'display_y_min_hz', 'display_y_max_hz',
      'data_color_min', 'data_color_max', 'auto_color_min', 'auto_color_max',
      'display_color_min', 'display_color_max',
      'transport_mode', 'display_colormap',
      'uses_page_y_range', 'uses_page_color_range', 'modal_item_id',
      'page_display_y_min_hz', 'page_display_y_max_hz',
      'page_display_color_min', 'page_display_color_max',
      'local_display_update_sequence',
    ];
    const result = {};
    keys.forEach((key) => {
      if (source[key] !== undefined) result[key] = source[key];
    });
    result.display_y_axis_scale = (
      figure.layout.yaxis && figure.layout.yaxis.type === 'log' ? 'log' : 'linear'
    );
    return result;
  }

  window.hydrophoneModalDisplay = {
    preload: loadMatrix,
    cancelPending: function () {
      cancelRasterPreviews();
      renderState.sequence += 1;
    },
  };
  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    modalDisplay: {
      startViewRefresh,
      updateCommitted,
      previewRanges,
      commitRasterPreview,
      extractDisplayMeta,
    },
  });
})();
