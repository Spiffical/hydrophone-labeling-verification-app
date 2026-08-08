(function () {
  const modalImagePrefetchCache = new Map();
  const modalImageReadyCache = new Map();
  const modalRenderState = {
    generation: 0,
  };

  function noUpdate() {
    return (window.dash_clientside || {}).no_update;
  }

  function noUpdates(count) {
    return Array.from({ length: count }, noUpdate);
  }

  function context() {
    return (window.dash_clientside || {}).callback_context || null;
  }

  function triggeredId(callbackContext) {
    if (!callbackContext) {
      return null;
    }
    if (callbackContext.triggered_id !== undefined && callbackContext.triggered_id !== null) {
      return callbackContext.triggered_id;
    }
    const triggered = callbackContext.triggered && callbackContext.triggered[0];
    const propId = triggered && triggered.prop_id;
    if (!propId) {
      return null;
    }
    const rawId = propId.slice(0, propId.lastIndexOf('.'));
    if (rawId.charAt(0) !== '{') {
      return rawId;
    }
    try {
      return JSON.parse(rawId);
    } catch (_error) {
      return null;
    }
  }

  function triggeredValue(callbackContext) {
    const triggered = callbackContext && callbackContext.triggered && callbackContext.triggered[0];
    return triggered ? triggered.value : null;
  }

  function isDirtyForItem(unsavedStore, currentItemId) {
    if (!unsavedStore || unsavedStore.dirty !== true) {
      return false;
    }
    const dirtyItemId = String(unsavedStore.item_id || '').trim();
    const current = String(currentItemId || '').trim();
    return !current || !dirtyItemId || dirtyItemId === current;
  }

  function beginRender() {
    modalRenderState.generation += 1;
    return modalRenderState.generation;
  }

  function imageReady(source) {
    if (typeof source !== 'string' || !source) {
      return Promise.resolve();
    }
    if (modalImageReadyCache.has(source)) {
      return modalImageReadyCache.get(source);
    }
    const promise = new Promise((resolve, reject) => {
      const image = new Image();
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        if (typeof image.decode === 'function') {
          image.decode().catch(function () {}).finally(resolve);
        } else {
          resolve();
        }
      };
      image.onload = finish;
      image.onerror = function () {
        if (settled) return;
        settled = true;
        reject(new Error(`Could not load modal spectrogram band: ${source}`));
      };
      image.src = source;
      if (image.complete && image.naturalWidth > 0) finish();
    }).catch((error) => {
      modalImageReadyCache.delete(source);
      throw error;
    });
    modalImageReadyCache.set(source, promise);
    while (modalImageReadyCache.size > 48) {
      const oldestSource = modalImageReadyCache.keys().next().value;
      if (oldestSource !== source) modalImageReadyCache.delete(oldestSource);
      else break;
    }
    return promise;
  }

  function figureImageSources(figure) {
    const images = figure && figure.layout && figure.layout.images;
    if (!Array.isArray(images)) return [];
    return images
      .map((entry) => entry && entry.source)
      .filter((source) => typeof source === 'string' && source);
  }

  function waitForPlotlyCommit(itemId, expectedSources, generation) {
    const deadline = Date.now() + 120000;
    return new Promise((resolve, reject) => {
      const check = () => {
        const graph = document.querySelector('#modal-image-graph .js-plotly-plot');
        const meta = graph && graph.layout && graph.layout.meta;
        const graphItemId = String((meta && meta.modal_item_id) || '');
        if (generation !== modalRenderState.generation && graphItemId !== itemId) {
          resolve(false);
          return;
        }
        const graphSources = graph && graph.layout && Array.isArray(graph.layout.images)
          ? graph.layout.images.map((entry) => entry && entry.source)
          : [];
        const exactSourcesMatch = expectedSources.length === graphSources.length
          && expectedSources.every((source, index) => graphSources[index] === source);
        const clientRasterCommitted = expectedSources.length === graphSources.length
          && graphSources.length > 0
          && graphSources.every((source) => typeof source === 'string' && source.startsWith('blob:'));
        const sourcesMatch = exactSourcesMatch || clientRasterCommitted;
        if (graph && graphItemId === itemId && sourcesMatch) {
          requestAnimationFrame(() => requestAnimationFrame(() => resolve(true)));
          return;
        }
        if (Date.now() >= deadline) {
          reject(new Error(`Timed out waiting for Plotly to commit modal item ${itemId}.`));
          return;
        }
        requestAnimationFrame(check);
      };
      check();
    });
  }

  function canonicalAxisRanges(graph) {
    const layout = graph && graph.layout;
    const meta = layout && layout.meta;
    if (!meta) return null;
    const xMin = Number(meta.x_min);
    const xMax = Number(meta.x_max);
    const yToHz = Number(meta.y_to_hz) || 1;
    const yMinHz = Number(meta.display_y_min_hz);
    const yMaxHz = Number(meta.display_y_max_hz);
    if (
      !Number.isFinite(xMin) || !Number.isFinite(xMax) || xMax <= xMin
      || !Number.isFinite(yMinHz) || !Number.isFinite(yMaxHz) || yMaxHz <= yMinHz
    ) {
      return null;
    }
    const yMin = yMinHz / yToHz;
    const yMax = yMaxHz / yToHz;
    const logarithmic = layout.yaxis && layout.yaxis.type === 'log';
    if (logarithmic && (yMin <= 0 || yMax <= 0)) return null;
    return {
      x: [xMin, xMax],
      y: logarithmic ? [Math.log10(yMin), Math.log10(yMax)] : [yMin, yMax],
    };
  }

  function installAxisResetGuard() {
    const graph = document.querySelector('#modal-image-graph .js-plotly-plot');
    if (!graph || typeof graph.on !== 'function' || graph._hydrophoneAxisResetGuard) return;
    graph._hydrophoneAxisResetGuard = true;
    graph.on('plotly_relayout', function (updates) {
      if (
        !updates
        || (updates['xaxis.autorange'] !== true && updates['yaxis.autorange'] !== true)
      ) {
        return;
      }
      const ranges = canonicalAxisRanges(graph);
      if (!ranges || !window.Plotly || typeof window.Plotly.relayout !== 'function') return;
      graph._hydrophoneAxisResetPending = true;
      restoreFullRaster(graph);
      window.requestAnimationFrame(function () {
        window.requestAnimationFrame(function () {
          Promise.resolve(window.Plotly.relayout(graph, {
            'xaxis.autorange': false,
            'xaxis.range': ranges.x,
            'yaxis.autorange': false,
            'yaxis.range': ranges.y,
          })).finally(function () {
            window.requestAnimationFrame(function () {
              graph._hydrophoneAxisResetPending = false;
            });
          });
        });
      });
    });
  }

  function axisRangesAreCanonical(graph) {
    const canonical = canonicalAxisRanges(graph);
    const xRange = graph && graph.layout && graph.layout.xaxis && graph.layout.xaxis.range;
    const yRange = graph && graph.layout && graph.layout.yaxis && graph.layout.yaxis.range;
    const close = function (left, right) {
      return Array.isArray(left) && Array.isArray(right) && left.length === 2 && right.length === 2
        && Math.abs(Number(left[0]) - Number(right[0])) <= 1e-6
        && Math.abs(Number(left[1]) - Number(right[1])) <= 1e-6;
    };
    return canonical && close(xRange, canonical.x) && close(yRange, canonical.y);
  }

  function clearZoomRasterWork(state) {
    state.generation += 1;
    if (state.timer) window.clearTimeout(state.timer);
    state.timer = null;
    if (state.controller) state.controller.abort();
    state.controller = null;
  }

  function sourceIndexWindow(lower, upper, fullLower, fullUpper, count) {
    if (!Number.isFinite(count) || count < 2 || fullUpper <= fullLower) return null;
    const clippedLower = Math.max(fullLower, Math.min(fullUpper, Math.min(lower, upper)));
    const clippedUpper = Math.max(fullLower, Math.min(fullUpper, Math.max(lower, upper)));
    if (clippedUpper <= clippedLower) return null;
    const scale = (count - 1) / (fullUpper - fullLower);
    let start = Math.max(0, Math.floor((clippedLower - fullLower) * scale));
    let end = Math.min(count, Math.ceil((clippedUpper - fullLower) * scale) + 1);
    const margin = Math.max(1, Math.ceil((end - start) * 0.08));
    start = Math.max(0, start - margin);
    end = Math.min(count, end + margin);
    return {
      start,
      end,
      lower: fullLower + ((start / (count - 1)) * (fullUpper - fullLower)),
      upper: fullLower + (((end - 1) / (count - 1)) * (fullUpper - fullLower)),
    };
  }

  function visibleRasterCrop(graph) {
    const layout = graph && graph.layout;
    const meta = layout && layout.meta;
    const shape = meta && meta.source_matrix_shape;
    if (
      !meta || !Array.isArray(shape) || shape.length !== 2
      || !meta.modal_image_url || (layout.yaxis && layout.yaxis.type === 'log')
    ) {
      return null;
    }
    const xRange = layout.xaxis && layout.xaxis.range;
    const yRange = layout.yaxis && layout.yaxis.range;
    if (!Array.isArray(xRange) || !Array.isArray(yRange)) return null;
    const xMin = Number(meta.x_min);
    const xMax = Number(meta.x_max);
    const yToHz = Number(meta.y_to_hz) || 1;
    const yMin = Number(meta.data_y_min_hz) / yToHz;
    const yMax = Number(meta.data_y_max_hz) / yToHz;
    const xVisible = Math.abs(Number(xRange[1]) - Number(xRange[0]));
    const yVisible = Math.abs(Number(yRange[1]) - Number(yRange[0]));
    if (
      !Number.isFinite(xVisible) || !Number.isFinite(yVisible)
      || xMax <= xMin || yMax <= yMin
      || (xVisible >= (xMax - xMin) * 0.92 && yVisible >= (yMax - yMin) * 0.92)
    ) {
      return null;
    }
    const columns = sourceIndexWindow(
      Number(xRange[0]), Number(xRange[1]), xMin, xMax, Number(shape[1])
    );
    const rows = sourceIndexWindow(
      Number(yRange[0]), Number(yRange[1]), yMin, yMax, Number(shape[0])
    );
    if (!rows || !columns) return null;
    const pixelRatio = Math.max(1, Math.min(2, Number(window.devicePixelRatio) || 1));
    const xPixels = graph._fullLayout && graph._fullLayout.xaxis
      ? graph._fullLayout.xaxis._length : graph.clientWidth;
    const yPixels = graph._fullLayout && graph._fullLayout.yaxis
      ? graph._fullLayout.yaxis._length : graph.clientHeight;
    return {
      rowStart: rows.start,
      rowEnd: rows.end,
      columnStart: columns.start,
      columnEnd: columns.end,
      x: columns.lower,
      y: rows.upper,
      sizex: columns.upper - columns.lower,
      sizey: rows.upper - rows.lower,
      width: Math.min(2560, Math.max(64, Math.ceil((xPixels * pixelRatio) / 64) * 64)),
      height: Math.min(1200, Math.max(64, Math.ceil((yPixels * pixelRatio) / 64) * 64)),
    };
  }

  function zoomRasterUrl(meta, crop) {
    const target = new URL(meta.modal_image_url, window.location.href);
    target.searchParams.set('tile_r0', String(crop.rowStart));
    target.searchParams.set('tile_r1', String(crop.rowEnd));
    target.searchParams.set('tile_c0', String(crop.columnStart));
    target.searchParams.set('tile_c1', String(crop.columnEnd));
    target.searchParams.set('mw', String(crop.width));
    target.searchParams.set('mh', String(crop.height));
    const colorMin = Number(meta.display_color_min);
    const colorMax = Number(meta.display_color_max);
    if (Number.isFinite(colorMin)) target.searchParams.set('tile_zmin', String(colorMin));
    if (Number.isFinite(colorMax)) target.searchParams.set('tile_zmax', String(colorMax));
    return `${target.pathname}${target.search}`;
  }

  function applyZoomRaster(graph, source, crop) {
    if (!window.Plotly || typeof window.Plotly.relayout !== 'function') return;
    window.Plotly.relayout(graph, {
      'images[0].source': source,
      'images[0].x': crop.x,
      'images[0].y': crop.y,
      'images[0].sizex': crop.sizex,
      'images[0].sizey': crop.sizey,
    });
  }

  function isCachedZoomRaster(state, source) {
    if (!state || !source) return false;
    for (const entry of state.cache.values()) {
      if (entry && entry.source === source) return true;
    }
    return false;
  }

  function restoreFullRaster(graph) {
    const state = graph && graph._hydrophoneZoomRasterState;
    if (!state || !state.fullImage) return;
    clearZoomRasterWork(state);
    applyZoomRaster(graph, state.fullImage.source, state.fullImage);
  }

  function refineZoomRaster(graph) {
    const state = graph && graph._hydrophoneZoomRasterState;
    const meta = graph && graph.layout && graph.layout.meta;
    if (!state || !meta || state.itemId !== String(meta.modal_item_id || '')) return;
    const crop = visibleRasterCrop(graph);
    if (!crop) {
      if (axisRangesAreCanonical(graph)) restoreFullRaster(graph);
      return;
    }
    const url = zoomRasterUrl(meta, crop);
    const cached = state.cache.get(url);
    if (cached) {
      applyZoomRaster(graph, cached.source, crop);
      return;
    }
    clearZoomRasterWork(state);
    const generation = state.generation;
    const browserRenderer = window.hydrophoneModalDisplay
      && window.hydrophoneModalDisplay.renderViewport;
    let sourcePromise;
    if (typeof browserRenderer === 'function') {
      sourcePromise = browserRenderer(meta, crop);
    } else {
      state.controller = new AbortController();
      sourcePromise = fetch(url, {
        credentials: 'same-origin',
        cache: 'force-cache',
        signal: state.controller.signal,
      })
        .then((response) => {
          if (!response.ok) throw new Error(`Zoom raster request failed with HTTP ${response.status}.`);
          return response.blob();
        })
        .then((blob) => URL.createObjectURL(blob));
    }
    sourcePromise
      .then((source) => {
        if (generation !== state.generation) {
          if (source) URL.revokeObjectURL(source);
          return null;
        }
        return imageReady(source).then(() => source);
      })
      .then((source) => {
        if (!source) return;
        if (generation !== state.generation || state.itemId !== String(meta.modal_item_id || '')) {
          URL.revokeObjectURL(source);
          return;
        }
        state.cache.set(url, { source });
        while (state.cache.size > 12) {
          const oldestKey = state.cache.keys().next().value;
          const oldest = state.cache.get(oldestKey);
          state.cache.delete(oldestKey);
          if (oldest && oldest.source) URL.revokeObjectURL(oldest.source);
        }
        applyZoomRaster(graph, source, crop);
      })
      .catch((error) => {
        if (error && error.name !== 'AbortError') {
          console.warn('[modal-zoom] detail raster request failed', error);
        }
      })
      .finally(() => {
        if (generation === state.generation) state.controller = null;
      });
  }

  function scheduleZoomRasterRefinement(graph) {
    const state = graph && graph._hydrophoneZoomRasterState;
    if (!state) return;
    clearZoomRasterWork(state);
    state.timer = window.setTimeout(function () {
      state.timer = null;
      refineZoomRaster(graph);
    }, 140);
  }

  function installZoomRasterRefinement() {
    const graph = document.querySelector('#modal-image-graph .js-plotly-plot');
    const meta = graph && graph.layout && graph.layout.meta;
    const image = graph && graph.layout && Array.isArray(graph.layout.images)
      ? graph.layout.images[0] : null;
    if (!graph || !meta || !image || !meta.modal_image_url) return;
    const itemId = String(meta.modal_item_id || '');
    let state = graph._hydrophoneZoomRasterState;
    if (!state) {
      state = { itemId: '', generation: 0, timer: null, controller: null, cache: new Map() };
      graph._hydrophoneZoomRasterState = state;
    }
    if (state.itemId !== itemId) {
      clearZoomRasterWork(state);
      state.cache.forEach((entry) => {
        if (entry && entry.source) URL.revokeObjectURL(entry.source);
      });
      state.cache.clear();
      state.itemId = itemId;
      state.fullImage = {
        source: image.source,
        x: image.x,
        y: image.y,
        sizex: image.sizex,
        sizey: image.sizey,
      };
    }
    if (graph._hydrophoneZoomRasterListener) return;
    graph._hydrophoneZoomRasterListener = true;
    graph.on('plotly_relayout', function (updates) {
      if (!updates) return;
      if (graph._hydrophoneAxisResetPending) return;
      if (updates['xaxis.autorange'] === true || updates['yaxis.autorange'] === true) {
        restoreFullRaster(graph);
        return;
      }
      const rangeChanged = Object.keys(updates).some(function (key) {
        return key.indexOf('xaxis.range') === 0 || key.indexOf('yaxis.range') === 0;
      });
      const imageSourceChanged = Object.keys(updates).some(function (key) {
        return key === 'images[0].source';
      });
      if (imageSourceChanged) {
        const current = graph.layout.images && graph.layout.images[0];
        if (current && !isCachedZoomRaster(state, current.source)) {
          const canonical = canonicalAxisRanges(graph);
          if (!canonical) return;
          state.fullImage = {
            source: current.source,
            x: canonical.x[0],
            y: canonical.y[1],
            sizex: canonical.x[1] - canonical.x[0],
            sizey: canonical.y[1] - canonical.y[0],
          };
          if (!axisRangesAreCanonical(graph)) scheduleZoomRasterRefinement(graph);
        }
      }
      if (rangeChanged) scheduleZoomRasterRefinement(graph);
    });
  }

  function measureViewport(_ticks, current) {
    const container = document.getElementById('modal-image-graph');
    const rect = container ? container.getBoundingClientRect() : null;
    const fallbackWidth = Math.max(320, Math.min(1140, window.innerWidth - 64));
    const cssWidth = rect && rect.width >= 280 ? rect.width : fallbackWidth;
    const cssHeight = rect && rect.height >= 240 ? rect.height : 500;
    const pixelRatio = Math.max(1, Math.min(2, Number(window.devicePixelRatio) || 1));
    const pixelWidth = Math.min(2560, Math.ceil((cssWidth * pixelRatio) / 64) * 64);
    const pixelHeight = Math.min(1200, Math.ceil((cssHeight * pixelRatio) / 64) * 64);
    if (
      current
      && current.pixel_width === pixelWidth
      && current.pixel_height === pixelHeight
      && current.pixel_ratio === pixelRatio
    ) {
      return noUpdate();
    }
    return {
      css_width: Math.round(cssWidth),
      css_height: Math.round(cssHeight),
      pixel_width: pixelWidth,
      pixel_height: pixelHeight,
      pixel_ratio: pixelRatio,
    };
  }

  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    modalLifecycle: Object.assign({}, (window.dash_clientside || {}).modalLifecycle, {
      openImmediately: function (_imageClicks, unsavedStore, currentItemId) {
        const callbackContext = context();
        const id = triggeredId(callbackContext);
        if (
          !id ||
          typeof id !== 'object' ||
          id.type !== 'spectrogram-image' ||
          Number(triggeredValue(callbackContext) || 0) <= 0
        ) {
          return noUpdates(4);
        }
        const itemId = String(id.item_id || '').trim();
        if (!itemId || isDirtyForItem(unsavedStore, currentItemId)) {
          return noUpdates(4);
        }
        beginRender();
        return [true, true, false, { item_id: itemId, ts: Date.now() }];
      },

      closeImmediately: function (
        _footerClicks,
        _headerClicks,
        unsavedStore,
        currentItemId
      ) {
        const callbackContext = context();
        const id = triggeredId(callbackContext);
        if (
          (id !== 'close-modal' && id !== 'close-modal-header') ||
          Number(triggeredValue(callbackContext) || 0) <= 0
        ) {
          return noUpdates(10);
        }
        if (isDirtyForItem(unsavedStore, currentItemId)) {
          return [
            noUpdate(),
            noUpdate(),
            noUpdate(),
            noUpdate(),
            noUpdate(),
            noUpdate(),
            noUpdate(),
            true,
            { kind: 'close' },
            false,
          ];
        }
        return [
          false,
          null,
          null,
          { item_id: null, boxes: [] },
          null,
          null,
          { dirty: false, item_id: null },
          false,
          null,
          false,
        ];
      },

      applyForcedAction: function (payload) {
        const action = payload && payload.action;
        if (!action || (action.kind !== 'open' && action.kind !== 'close')) {
          return noUpdates(3);
        }
        if (action.kind === 'open') {
          beginRender();
          return [true, true, false];
        }
        return [false, false, true];
      },

      finishLoading: function (figure) {
        const meta = figure && figure.layout && figure.layout.meta;
        if (!meta) return noUpdates(2);
        const itemId = String(meta.modal_item_id || '');
        if (!itemId) return noUpdates(2);
        const generation = modalRenderState.generation;
        const sources = figureImageSources(figure);
        return Promise.all(sources.map(imageReady))
          .then(() => waitForPlotlyCommit(itemId, sources, generation))
          .then((committed) => {
            const graph = document.querySelector('#modal-image-graph .js-plotly-plot');
            const currentItemId = String(
              (graph && graph.layout && graph.layout.meta && graph.layout.meta.modal_item_id) || ''
            );
            if (!committed || currentItemId !== itemId) {
              return noUpdates(2);
            }
            installAxisResetGuard();
            installZoomRasterRefinement();
            return [false, true];
          })
          .catch((error) => {
            if (generation !== modalRenderState.generation) return noUpdates(2);
            console.warn('[modal-lifecycle] spectrogram readiness check failed', error);
            return [false, true];
          });
      },

      measureViewport,

      prefetchImages: function (figure) {
        const meta = figure && figure.layout && figure.layout.meta;
        if (meta && meta.local_display_update_sequence) {
          return noUpdate();
        }
        if (window.hydrophoneModalDisplay) {
          window.hydrophoneModalDisplay.cancelPending();
        }
        const urls = meta && Array.isArray(meta.prefetch_image_urls)
          ? meta.prefetch_image_urls
          : [];
        const preloadImages = function () {
          urls.forEach(function (url) {
            if (typeof url !== 'string' || !url || modalImagePrefetchCache.has(url)) {
              return;
            }
            const image = new Image();
            image.decoding = 'async';
            image.src = url;
            modalImagePrefetchCache.set(url, image);
          });
          while (modalImagePrefetchCache.size > 24) {
            const oldestUrl = modalImagePrefetchCache.keys().next().value;
            modalImagePrefetchCache.delete(oldestUrl);
          }
        };
        const dataPreload = meta && meta.modal_data_url && window.hydrophoneModalDisplay
          ? window.hydrophoneModalDisplay.preload(meta.modal_data_url)
          : null;
        if (dataPreload && typeof dataPreload.finally === 'function') {
          dataPreload.catch(function () {}).finally(preloadImages);
        } else {
          preloadImages();
        }
        return { count: urls.length, ts: Date.now() };
      },
    }),
  });
  window.hydrophoneModalLifecycle = Object.assign({}, window.hydrophoneModalLifecycle, {
    beginRender,
  });
})();
