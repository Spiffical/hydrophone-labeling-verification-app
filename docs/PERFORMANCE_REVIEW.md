# App performance review — September 6, 2026

The largest remaining opportunities are reducing data passed through Dash callbacks and reducing how much UI each action rebuilds. Spectrogram computation already has useful optimizations: audio is downsampled for the requested frequency band, cached computations are shared between concurrent requests, card images have separate URLs, nearby items are prefetched, and several latency-sensitive actions run in the browser. Replacing these mechanisms wholesale would add risk without addressing the main sources of unnecessary work.

This review covered spectrogram loading/generation, thumbnail rendering, Plotly transport and overlays, modal lifecycle and controls, label editing and saving, pagination/filtering, dataset discovery, audio playback, and background work. Measurements used this Mac's existing environment (Python 3.14, Dash 4.3, Plotly 6.8), synthetic data and disposable copies of the repository's mock fixtures. They are local measurements, not production latency guarantees or a benchmark of the user's full dataset.

**Changes implemented**

| Area | Change | Experience preserved |
|---|---|---|
| Modal display controls | Extract small display metadata in the browser; Python no longer receives the whole figure just to populate sliders. Suppress unchanged metadata updates after box edits. | Axis units, ranges, auto contrast and manual limits remain available. |
| Box tags, box editor, label deletion | Send a small figure context to Python and return a Dash patch for shapes, annotations and handle traces. | Heatmap arrays, embedded images, unrelated traces and view revision remain in the browser. |
| Spectrogram contrast | Compute exact percentiles together, once per cached spectrogram, then reuse them for thumbnails, figures and range summaries. | The same 2nd/98th percentile calculation and existing fallback rules; no approximate statistics. |
| Thumbnails | Remove tight-bounding-box calculation from an already full-canvas image. | Same 108 × 108 pixel output. Linear/log, both colormaps and explicit limits matched the original pixels. |
| Label cards | Fingerprint the visible page and directly update only changed card columns. Rebuild the page for navigation, new data or display changes. | Neighboring cards retain their mounted controls; unchanged cards are not reconstructed or retransmitted. |
| Modal Save | Use the staged modal item when saving from the modal. | A pre-existing bug checked the older page item's pending-save flag and silently skipped box-only changes. The current draft now reaches persistence. |
| Unsaved-change navigation | Return correctly sized lists for verification-card wildcard outputs. | A pre-existing HTTP 500 on label-mode Stay/Discard was exposed during browser checks when no verification cards were mounted. |

There is deliberately no change to FFT window size, overlap, frequency bandwidth, matrix resolution, default float32 transport, zoom, audio quality or annotation coordinate precision. Cold loads now compute contrast statistics before returning the cached spectrogram; this moves work needed by the first display into the load rather than eliminating that initial calculation. Cached spectrogram matrices are treated as immutable, consistent with the existing cache's shared-object behavior.

**Measured impact**

The paired before/after CPU run used the original `HEAD` implementation and the updated implementation in the same Python process. Each measurement is the median of seven calls after a warm-up. The synthetic PSD contains 512 frequency bins × 3,000 time bins. Figure construction excludes serialization, network transfer and browser rendering.

| Operation | Before | After | Interpretation |
|---|---:|---:|---|
| Figure construction from cached PSD | 23.2 ms | 11.0 ms | About 53% less CPU time. |
| Thumbnail rendering from cached PSD | 105.9 ms | 50.1 ms | About 53% less CPU time, identical tested pixels. |
| Data needed to synchronize display ranges | 8.69 MB figure | About 0.6 KB metadata | Matrix transfer removed from this callback; excludes Dash's envelope. |
| Figure data needed for a one-box edit | 8.69 MB figure | About 2.0 KB context | The edit request no longer scales with matrix size. |
| Figure response for a one-box edit | 8.69 MB figure | About 3.1 KB patch | Other returned UI and item state add their own small payloads. |

The 25-card synthetic grid benchmark reduced card construction from about 4.8 ms to 0.16 ms for a one-card change. Its full grid serialized to approximately 105 KB versus approximately 3.2 KB for the changed card. Actual cards with audio, longer labels or many boxes cost more. This optimization still receives the label dataset from the browser; it does not solve that separate scaling problem.

During browser verification, applying a box edit retained the exact same heatmap array object and generated zero display-range synchronization requests. The tested edit request was approximately 6.9 KB and its total response approximately 11 KB, including the item/actions panel. A parent-level grid Patch still remounted neighboring cards under the installed Dash renderer, so the implementation instead targets individual column components with `set_props`.

A separate audio benchmark used a 60-second, 48 kHz mono PCM WAV, 1-second FFT window and 90% overlap. It cleared the in-memory spectrogram cache between cold samples, but the OS file cache and imports were warm:

| Requested band | Cold generation + statistics | Cached lookup | PSD memory |
|---|---:|---:|---:|
| 5–100 Hz | 53.4 ms | 0.051 ms | 0.23 MB |
| 5–20,000 Hz | 122.4 ms | 0.058 ms | 47.3 MB |

These audio measurements are current-state diagnostics, not before/after FFT speedups. The FFT algorithm was not changed. Longer recordings, compressed audio and different disks can behave very differently.

**Next improvements, in priority order**

| Priority | Finding and evidence | Recommended change and validation |
|---|---|---|
| 1 | Label and explore datasets live in browser stores. Modal opening, saves and several other callbacks accept these complete datasets as State, including stores belonging to inactive modes. `lifecycle_navigation_callbacks.py`, `editor_save_callbacks.py`, `bbox_sync_callbacks.py`. | Move label/explore datasets to a session-scoped server repository with ID lookup, following the existing verification cache pattern. Send item IDs, current drafts, revisions and visible-page summaries. Test concurrent sessions, reload, tab switching, unsaved navigation and cache eviction before adoption. |
| 1 | Changing colormap, frequency range or contrast still calls `create_item_spectrogram_figure` and returns the full heatmap. `modal/view_callbacks.py:update_modal_view`. | Patch display-only properties when source data is unchanged. Account explicitly for log-axis coordinates, image fallback and uint16 transport, where contrast changes can require re-encoding data. Preserve auto/manual limits, box coordinates and zoom behavior. |
| 1 | Replacing `modal-item-actions.children` recreates dynamic buttons/dropdowns. Browser traces show multiple resulting callbacks immediately returning HTTP 204, including profile guards, note/save handlers and editor handlers. Drawing a box also refreshes actions both from the box store and the synchronized item. | Keep the action panel mounted and update individual rows/disabled states. Consolidate redundant triggers and gate unchanged updates in the browser before requests are sent. Preserve server-side profile validation and unsaved-change safeguards. |
| 1 | Caches are limited by item count, not bytes. Default capacity is 75 spectrograms per matrix cache. The measured broad-band example is 47.3 MB per PSD; 75 such PSDs alone would approach 3.5 GB, before Plotly copies, audio and another matrix cache. | Introduce byte budgets and cache telemetry, then bound pending prefetch work. Prioritize the visible page and requested modal; cancel queued work for obsolete pages/settings. Keep same-key request deduplication and avoid evicting a foreground computation immediately. |
| 2 | Generated matrices/thumbnails are cached only in process memory, so restarts and evictions repeat work. MAT cache keys currently use paths rather than file modification signatures. `image_processing.py`. | Add an optional disk cache keyed by source identity/stat, FFT parameters and renderer version. Store exact numeric arrays and lossless thumbnails. Invalidate changed files; bound disk usage and write cache entries atomically. |
| 2 | Verification filtering scans the dataset under a shared lock each time a page is requested; future-page prefetch calls filtering again for each page. Leaf classes and summary counts are also repeatedly recomputed. `verify_modal_cache.py`, `render_callbacks.py:_collect_verify_future_page_items`. | Cache ordered visible IDs by dataset revision, thresholds, class selection and status. Slice once for current/future pages; maintain summary counters on item updates. Validate all manual-review, rejected-label and status-filter cases. |
| 2 | Slider drag readouts use server callbacks even though the calculation is local arithmetic. Audio controls also combine event listeners/observers with per-slider polling. `modal/view_callbacks.py`, `audio_controls.js`. | Move readout previews into clientside callbacks, keeping expensive figure changes on committed values. Coalesce animation-frame work and suspend polling for hidden/inactive controls. Test keyboard, touch, EQ and external value changes. |
| 2 | Label saves read and rewrite a JSON document containing accumulated verification history. `label_operations.py:save_labels`. Work grows with dataset/history size and writes are serialized. | Profile real saved files before changing storage. For large deployments, use a transactional indexed store with explicit JSON import/export. Preserve history, locking and successful-save acknowledgement; do not hide incomplete disk writes behind optimistic success. |
| 3 | Dataset discovery and loading perform repeated directory listings/globs and metadata reads. `data_loading.py`, `data_discovery.py`. | Build a reusable directory index for each load, then invalidate it on explicit reload or detected directory changes. Benchmark on actual network-mounted folders; local mock fixtures cannot establish the likely savings. |
| 3 | `orjson` is absent in the current environment, and full figure responses remain expensive to serialize. | Benchmark Dash's supported optional `orjson` path and transfer compression on representative payloads. Compression trades CPU for bandwidth; it may help a remote deployment more than localhost. Prefer removing unnecessary payloads first. |

The app already uses lazy card images, card audio with `preload='none'`, conditional/range audio responses, immediate clientside modal opening/closing, and local box drawing/edit initiation. Preserve those advantages. Modal audio preloads the selected clip; change that only if measurements show it competes materially with spectrogram delivery. Do not switch audio to a lossy format or downsample displayed spectrograms merely to improve a benchmark.

Do not add multiple web-server worker processes without first addressing shared state. The verification dataset cache, generated matrix caches, locks and prefetch executors are process-local. Requests routed to different workers can miss the relevant verification dataset or duplicate expensive generation. A shared repository/cache or deliberate session routing must precede that deployment change.

**Verification and reproduction**

Run the Python regression suite and the standalone clientside test:

```bash
.venv/bin/python -m pytest -q
node --test tests/modal_performance.test.cjs
.venv/bin/python scripts/benchmark_performance.py --repeats 7
```

The added tests cover overlay patch equivalence (including deletion and unrelated traces/images), absence of full-figure server inputs, targeted card updates, exact cached contrast and saving the current modal draft. The JavaScript test ensures metadata extraction never reads matrix/image payloads and suppresses slider refreshes after box edits. Browser checks use copied fixtures so user labels remain untouched.

Validation: 116 Python tests passed; four opt-in live HTTP tests were skipped. The standalone JavaScript test passed. Browser checks verified modal opening, drawing a box, applying coordinate edits and tags, label deletion, changing log scale and frequency limits, saving a box-only draft, preserving neighboring card elements during note updates, and discarding edits while navigating to the next item. The final navigation check produced no browser console errors. Additional Flask test-client requests cover Stay/Discard with no verification cards mounted.

For the next profiling pass, record click-to-visible and click-to-settled time separately, callback request/response bytes, cache hit/miss counts, pending prefetch jobs and peak resident memory. Use representative real recordings and datasets at several sizes; compare cold starts, warmed navigation, repeated edits and rapid page/settings changes. Investigate p95 latency and stale responses, not only average generation time.

The approach follows Dash's documented [partial property updates](https://dash.plotly.com/partial-properties), [clientside callbacks](https://dash.plotly.com/clientside-callbacks) and [performance guidance](https://dash.plotly.com/performance). The findings and timings above come from this codebase and local measurements.
