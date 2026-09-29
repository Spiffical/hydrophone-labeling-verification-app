// Box list and "tag for new boxes" toolbar in the spectrogram modal.
//
// The list is rendered here from modal-bbox-store instead of being part of the
// server-built modal-item-actions panel. That panel is rebuilt on many events,
// which used to reset the list's scroll position after every tag change, and
// its per-row dropdowns made clips with dozens of boxes slow. Rows are patched
// in place, and tag edits go through a clientside callback (applyCommand), so
// tagging never waits on the server.
(function () {
  'use strict';

  const TOOLBAR_ID = 'modal-bbox-toolbar';
  const PANEL_ID = 'modal-bbox-panel';
  const CHIP_LIMIT = 6; // more tag options than this use a compact <select>
  const EXPANDED_KEY = 'bboxList.expanded';

  // ---------------------------------------------------------------------------
  // Model helpers (pure; covered by tests/bbox_list.test.cjs)
  // ---------------------------------------------------------------------------

  function cleanTag(tag) {
    const text = tag === null || tag === undefined ? '' : String(tag).trim();
    return text || null;
  }

  function normalizeOptions(options) {
    const seen = new Set();
    const normalized = [];
    (Array.isArray(options) ? options : []).forEach(function (option) {
      const raw = option && typeof option === 'object' ? option.value : option;
      const value = cleanTag(raw);
      if (!value || seen.has(value)) {
        return;
      }
      seen.add(value);
      const label = option && typeof option === 'object' ? cleanTag(option.label) : null;
      normalized.push({ value: value, label: label || value });
    });
    return normalized;
  }

  function tagLabel(value, options) {
    const match = normalizeOptions(options).find(function (option) { return option.value === value; });
    return match ? match.label : value;
  }

  // Tags are call types, so they come in sets per species (config.tag_sets:
  // [{label, options}]). A box is tagged from the first set whose species
  // label is its label or an ancestor of it; a set without a label applies to
  // every box. Mirrors tag_options_for_label in app/services/bbox_tags.py.
  function labelParts(label) {
    return String(label || '').split('>').map(function (part) { return part.trim().toLowerCase(); }).filter(Boolean);
  }

  function normalizeTagSets(config) {
    const source = config && Array.isArray(config.tag_sets)
      ? config.tag_sets
      : [{ label: null, options: config && config.tag_options }];
    return source.map(function (set) {
      return { root: labelParts(set && set.label), options: normalizeOptions(set && set.options) };
    }).filter(function (set) { return set.options.length > 0; });
  }

  function labelMatches(parts, root) {
    if (!root.length) {
      return true;
    }
    const prefix = root.every(function (part, index) { return parts[index] === part; });
    // A bare species name ("Fin whale") still counts as that species.
    return prefix || parts.indexOf(root[root.length - 1]) >= 0;
  }

  function optionsForLabel(sets, label) {
    const parts = labelParts(label);
    const match = (Array.isArray(sets) ? sets : []).find(function (set) { return labelMatches(parts, set.root); });
    return match ? match.options : [];
  }

  function allOptions(sets) {
    return normalizeOptions([].concat.apply([], (Array.isArray(sets) ? sets : []).map(function (set) { return set.options; })));
  }

  // Used by bbox_clientside.js for the tag a new box may take.
  function tagOptionsFor(config, label) {
    return optionsForLabel(normalizeTagSets(config), label);
  }

  // `options` is one option list for every box, or a function giving the
  // options for a box's label.
  function optionsResolver(options) {
    if (typeof options === 'function') {
      return function (label) { return normalizeOptions(options(label)); };
    }
    const fixed = normalizeOptions(options);
    return function () { return fixed; };
  }

  // Boxes of a species without tags cannot be tagged, so they never count as
  // untagged; `taggable` counts the boxes that have or could have a tag.
  function summarize(boxes, options) {
    const resolve = optionsResolver(options);
    const list = Array.isArray(boxes) ? boxes : [];
    const counts = {};
    const opts = typeof options === 'function' ? [] : resolve(null).slice();
    let untagged = 0;
    let taggable = 0;
    list.forEach(function (box) {
      const boxOptions = resolve(box && box.label);
      boxOptions.forEach(function (option) {
        if (!opts.some(function (known) { return known.value === option.value; })) {
          opts.push(option);
        }
      });
      const tag = cleanTag(box && box.tag);
      if (tag) {
        counts[tag] = (counts[tag] || 0) + 1;
      } else if (boxOptions.length) {
        untagged += 1;
      }
      if (tag || boxOptions.length) {
        taggable += 1;
      }
    });
    const tags = opts.map(function (option) {
      return { value: option.value, label: option.label, count: counts[option.value] || 0 };
    });
    // Tags saved under an older option list still count.
    Object.keys(counts).forEach(function (value) {
      if (!opts.some(function (option) { return option.value === value; })) {
        tags.push({ value: value, label: value, count: counts[value] });
      }
    });
    return { total: list.length, untagged: untagged, taggable: taggable, tags: tags };
  }

  // Without `options` every box counts; with them, only boxes that could be tagged.
  function untaggedIndices(boxes, options) {
    const resolve = options === undefined ? null : optionsResolver(options);
    const indices = [];
    (Array.isArray(boxes) ? boxes : []).forEach(function (box, index) {
      if (!cleanTag(box && box.tag) && (!resolve || resolve(box && box.label).length)) {
        indices.push(index);
      }
    });
    return indices;
  }

  function applyTag(boxes, indices, tag) {
    const next = (Array.isArray(boxes) ? boxes : []).slice();
    const clean = cleanTag(tag);
    let changed = 0;
    (Array.isArray(indices) ? indices : []).forEach(function (raw) {
      const index = Number(raw);
      if (!Number.isInteger(index) || index < 0 || index >= next.length) {
        return;
      }
      const box = next[index];
      if (!box || typeof box !== 'object' || cleanTag(box.tag) === clean) {
        return;
      }
      const updated = Object.assign({}, box);
      // A reviewer's tag is a human tag on this box, even over a model tag.
      if (clean) {
        updated.tag = clean;
        updated.tag_source = 'human';
        updated.tag_scope = 'time_freq_box';
      } else {
        delete updated.tag;
        delete updated.tag_source;
        delete updated.tag_scope;
      }
      next[index] = updated;
      changed += 1;
    });
    return { boxes: next, changed: changed };
  }

  // changes: [[index, tag], ...], applied in order.
  function applyTagChanges(boxes, changes) {
    let next = Array.isArray(boxes) ? boxes : [];
    let changed = 0;
    (Array.isArray(changes) ? changes : []).forEach(function (change) {
      if (Array.isArray(change) && change.length === 2) {
        const result = applyTag(next, [change[0]], change[1]);
        next = result.boxes;
        changed += result.changed;
      }
    });
    return { boxes: next, changed: changed };
  }

  // '0' means "no tag for new boxes"; '1'-'9' pick the option at that position.
  // Returns undefined when the key is not a tag shortcut.
  function tagForKey(key, options) {
    if (!/^[0-9]$/.test(String(key))) {
      return undefined;
    }
    const digit = Number(key);
    if (digit === 0) {
      return null;
    }
    const opts = normalizeOptions(options);
    return digit <= opts.length ? opts[digit - 1].value : undefined;
  }

  function finite(value) {
    if (value === null || value === undefined || value === '') {
      return null;
    }
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function describeExtent(extent) {
    const source = extent && typeof extent === 'object' ? extent : {};
    const t0 = finite(source.time_start_sec);
    const t1 = finite(source.time_end_sec);
    const f0 = finite(source.freq_min_hz);
    const f1 = finite(source.freq_max_hz);
    let freq = 'All frequencies';
    if (f0 !== null && f1 !== null) {
      freq = Math.max(f0, f1) >= 1000
        ? (f0 / 1000).toFixed(1) + '–' + (f1 / 1000).toFixed(1) + ' kHz'
        : Math.round(f0) + '–' + Math.round(f1) + ' Hz';
    }
    return {
      time: t0 !== null && t1 !== null ? t0.toFixed(1) + '–' + t1.toFixed(1) + ' s' : 'Whole clip',
      freq: freq,
    };
  }

  function leafLabel(label) {
    const parts = String(label || '').split('>').map(function (part) { return part.trim(); }).filter(Boolean);
    return parts.length ? parts[parts.length - 1] : 'Unlabeled';
  }

  window.bboxListModel = {
    cleanTag: cleanTag,
    normalizeOptions: normalizeOptions,
    normalizeTagSets: normalizeTagSets,
    optionsForLabel: optionsForLabel,
    tagOptionsFor: tagOptionsFor,
    summarize: summarize,
    untaggedIndices: untaggedIndices,
    applyTag: applyTag,
    applyTagChanges: applyTagChanges,
    tagForKey: tagForKey,
    describeExtent: describeExtent,
  };

  // ---------------------------------------------------------------------------
  // Browser state and helpers
  // ---------------------------------------------------------------------------

  const view = {
    itemId: null,
    boxes: [],
    tagSets: [],
    allOptions: [],
    anyTaggable: false,
    bulk: true,
    editable: false,
    needsProfile: false,
    readOnlyReason: '',
    activeTag: null,
    open: false,
  };
  const ui = {
    itemId: null,
    boxCount: 0,
    selected: new Set(),
    // Tags shown before modal-bbox-store confirms them: index -> {tag, at}.
    pending: new Map(),
    // Same for the tag-for-new-boxes choice: {tag, at} or null.
    pendingActive: null,
    untaggedOnly: false,
    expanded: readExpanded(),
  };
  const PENDING_MS = 5000;
  let renderFrame = null;

  function readExpanded() {
    try {
      return window.localStorage.getItem(EXPANDED_KEY) === '1';
    } catch (_error) {
      return false;
    }
  }

  function writeExpanded(value) {
    try {
      window.localStorage.setItem(EXPANDED_KEY, value ? '1' : '0');
    } catch (_error) {
      // Private windows can block storage; the toggle still works for this page.
    }
  }

  function interactions() {
    return (window.dash_clientside || {}).bboxInteractions || {};
  }

  function setProps(id, props) {
    const dc = window.dash_clientside || {};
    if (typeof dc.set_props === 'function') {
      dc.set_props(id, props);
    }
  }

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      const value = attrs[key];
      if (value === null || value === undefined || value === false) {
        return;
      }
      if (key === 'className') {
        node.className = value;
      } else if (key === 'text') {
        node.textContent = value;
      } else if (key === 'style') {
        Object.keys(value).forEach(function (name) { node.style.setProperty(name, value[name]); });
      } else if (key === 'checked' || key === 'disabled' || key === 'indeterminate') {
        node[key] = Boolean(value);
      } else {
        node.setAttribute(key, value === true ? '' : String(value));
      }
    });
    (children || []).forEach(function (child) {
      if (child !== null && child !== undefined && child !== false) {
        node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
      }
    });
    return node;
  }

  function tagBoxes(indices, tag) {
    const clean = cleanTag(tag);
    const result = applyTag(view.boxes, indices, clean);
    if (!view.editable || !result.changed) {
      return;
    }
    // Show the new tag in this frame; the store update (and the slower
    // spectrogram redraw) follow through applyCommand.
    const now = Date.now();
    indices.forEach(function (index) { ui.pending.set(Number(index), { tag: clean, at: now }); });
    view.boxes = result.boxes;
    renderNow(null);
    // Send every unconfirmed tag, not only this click: Dash can coalesce
    // set_props calls made in quick succession into a single callback run.
    const changes = [];
    ui.pending.forEach(function (entry, index) { changes.push([index, entry.tag]); });
    setProps('modal-bbox-command-store', {
      data: { action: 'set_tags', item_id: view.itemId, changes: changes, nonce: now + Math.random() },
    });
  }

  // Keep optimistic tags until the store catches up, so a store update that
  // lands between two quick clicks does not briefly revert the second one.
  function withPendingTags(boxes) {
    let merged = boxes;
    const now = Date.now();
    ui.pending.forEach(function (entry, index) {
      const box = merged[index];
      if (!box || now - entry.at > PENDING_MS || cleanTag(box.tag) === entry.tag) {
        ui.pending.delete(index);
        return;
      }
      merged = applyTag(merged, [index], entry.tag).boxes;
    });
    return merged;
  }

  function setActiveTag(tag) {
    const clean = cleanTag(tag);
    if (!view.editable || clean === view.activeTag) {
      return;
    }
    view.activeTag = clean;
    ui.pendingActive = { tag: clean, at: Date.now() };
    refresh();
    setProps('modal-bbox-active-tag-store', { data: clean });
  }

  // Tag options for a box with this label (its species' set, or none).
  function boxOptions(label) {
    return optionsForLabel(view.tagSets, label);
  }

  // Options for the next boxes drawn: those of the label draw mode gives them.
  function newBoxOptions() {
    const draw = window.bboxDrawMode;
    return boxOptions(draw ? draw.label() : null);
  }

  function needsTag(box) {
    return !cleanTag(box && box.tag) && boxOptions(box && box.label).length > 0;
  }

  function canTag(box) {
    return Boolean(cleanTag(box && box.tag)) || boxOptions(box && box.label).length > 0;
  }

  function visibleIndices() {
    const indices = [];
    view.boxes.forEach(function (box, index) {
      if (!ui.untaggedOnly || needsTag(box)) {
        indices.push(index);
      }
    });
    return indices;
  }

  // Listed rows with a checkbox: boxes that have or could have a tag.
  function selectableIndices() {
    return visibleIndices().filter(function (index) { return canTag(view.boxes[index]); });
  }

  // ---------------------------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------------------------

  function tagButton(option, active, attrs) {
    return el('button', Object.assign({
      type: 'button',
      className: 'modal-bbox-tag' + (active ? ' is-active' : ''),
      'aria-pressed': active ? 'true' : 'false',
      text: option.label,
    }, attrs));
  }

  function drawButton(on, disabled, title) {
    return el('button', {
      type: 'button',
      className: 'modal-bbox-draw' + (on ? ' is-active' : ''),
      'data-action': 'toggle-draw',
      'aria-pressed': on ? 'true' : 'false',
      disabled: disabled,
      title: title,
    }, [
      el('i', { className: 'bi bi-bounding-box', 'aria-hidden': 'true' }),
      on ? 'Drawing' : 'Draw',
      el('kbd', { text: 'B' }),
    ]);
  }

  function renderDrawControls(root) {
    const draw = window.bboxDrawMode;
    if (!draw) {
      return;
    }
    // Without a reviewer name the controls stay, switched off, with a way to
    // add one. Each dashboard address keeps its own profile in the browser,
    // so a name given on one dashboard is not known on the next.
    if (!view.editable) {
      if (view.needsProfile) {
        root.appendChild(drawButton(false, true, 'Add your name and email to draw boxes'));
        root.appendChild(el('button', {
          type: 'button',
          className: 'modal-bbox-toolbar__profile',
          'data-action': 'open-profile',
        }, [
          el('i', { className: 'bi bi-person', 'aria-hidden': 'true' }),
          'Add your name to draw boxes',
        ]));
      }
      return;
    }
    const on = draw.isOn();
    const labels = draw.labels();
    const current = draw.label();
    root.appendChild(drawButton(
      on,
      !labels.length && !on,
      on
        ? 'Stop drawing (B or Esc)'
        : (labels.length ? 'Draw boxes: every drag adds one (B)' : 'Accept or add a label to draw boxes'),
    ));
    if (labels.length > 1) {
      const select = el('select', {
        className: 'modal-bbox-draw-label form-select form-select-sm',
        'data-action': 'draw-label',
        'aria-label': 'Label for new boxes',
      }, labels.map(function (label) {
        return el('option', { value: label, text: leafLabel(label) });
      }));
      select.value = current || labels[0];
      root.appendChild(select);
    } else if (labels.length === 1) {
      root.appendChild(el('span', { className: 'modal-bbox-draw-label-text', title: labels[0], text: leafLabel(labels[0]) }));
    }
    root.appendChild(el('span', { className: 'modal-bbox-toolbar__divider', 'aria-hidden': 'true' }));
  }

  function renderToolbar(root) {
    root.textContent = '';
    const summary = summarize(view.boxes, boxOptions);
    renderDrawControls(root);
    // Chips only for a species with tags, e.g. fin whale call types while a
    // fin whale label is the one being drawn.
    const options = newBoxOptions();
    if (view.editable && options.length) {
      const current = options.some(function (option) { return option.value === view.activeTag; }) ? view.activeTag : null;
      const chips = [{ value: null, label: 'No tag' }].concat(options).map(function (option, position) {
        const active = cleanTag(option.value) === current;
        const button = el('button', {
          type: 'button',
          role: 'radio',
          className: 'modal-bbox-tag modal-bbox-tag--toolbar' + (active ? ' is-active' : ''),
          'aria-checked': active ? 'true' : 'false',
          'data-action': 'active-tag',
          'data-tag': option.value || '',
          title: position <= 9 ? 'Shortcut: ' + position : null,
        }, [option.label]);
        if (position <= 9) {
          button.appendChild(el('kbd', { text: String(position) }));
        }
        return button;
      });
      root.appendChild(el('span', { className: 'modal-bbox-toolbar__label', text: 'Tag new boxes' }));
      root.appendChild(el('div', {
        className: 'modal-bbox-toolbar__chips',
        role: 'radiogroup',
        'aria-label': 'Tag for new boxes',
      }, chips));
    }
    if (summary.total) {
      const text = summary.total + (summary.total === 1 ? ' box' : ' boxes');
      root.appendChild(el('button', {
        type: 'button',
        className: 'modal-bbox-toolbar__summary',
        'data-action': 'jump',
        title: 'Show the box list',
      }, [
        text,
        !summary.taggable
          ? null
          : summary.untagged
            ? el('span', { className: 'modal-bbox-toolbar__untagged', text: ' · ' + summary.untagged + ' untagged' })
            : el('span', { className: 'modal-bbox-toolbar__done', text: ' · all tagged' }),
        el('i', { className: 'bi bi-arrow-down-short', 'aria-hidden': 'true' }),
      ]));
    }
    root.hidden = !root.childNodes.length;
  }

  // Selection is synced separately so ticking a checkbox never rebuilds its row.
  function rowSignature(box, multiLabel) {
    return JSON.stringify([
      cleanTag(box && box.tag),
      box && box.tag_source,
      box && box.label,
      box && box.annotation_extent,
      box && box.source,
      box && box.decision,
      view.editable,
      view.bulk && view.anyTaggable,
      multiLabel,
      boxOptions(box && box.label),
    ]);
  }

  function syncSelection(row, index) {
    const selected = ui.selected.has(index);
    row.classList.toggle('is-selected', selected);
    const checkbox = row.querySelector('.modal-bbox-row__select');
    if (checkbox) {
      checkbox.checked = selected;
    }
  }

  function focusedControl(list) {
    const active = document.activeElement;
    if (!active || !list.contains(active)) {
      return null;
    }
    const row = active.closest('.modal-bbox-row');
    return row ? {
      index: row.getAttribute('data-index'),
      action: active.getAttribute('data-action'),
      tag: active.getAttribute('data-tag'),
    } : null;
  }

  function restoreFocus(list, focus) {
    if (!focus || list.contains(document.activeElement)) {
      return;
    }
    const selector = '.modal-bbox-row[data-index="' + focus.index + '"] [data-action="' + focus.action + '"]'
      + (focus.tag !== null ? '[data-tag="' + String(focus.tag).replace(/"/g, '\\"') + '"]' : '');
    const target = list.querySelector(selector);
    if (target) {
      target.focus({ preventScroll: true });
    }
  }

  function buildRow(box, index, multiLabel) {
    const tag = cleanTag(box && box.tag);
    const options = boxOptions(box && box.label);
    const extent = describeExtent(box && box.annotation_extent);
    const number = index + 1;
    const color = typeof interactions().boxColor === 'function' ? interactions().boxColor(box) : null;
    const cells = [];
    const selectable = view.editable && view.bulk && view.anyTaggable;
    if (selectable && canTag(box)) {
      cells.push(el('input', {
        type: 'checkbox',
        className: 'modal-bbox-row__select form-check-input',
        'data-action': 'select',
        'data-index': index,
        checked: ui.selected.has(index),
        'aria-label': 'Select box ' + number,
      }));
    } else if (selectable) {
      // Keeps the column lined up with rows that can be selected for tagging.
      cells.push(el('span', { className: 'modal-bbox-row__select-spacer', 'aria-hidden': 'true' }));
    }
    cells.push(el('span', {
      className: 'modal-bbox-row__num',
      style: color ? { '--bbox-row-color': color } : null,
      title: box && box.source === 'model' ? 'Model box' : null,
      text: String(number),
    }));
    if (multiLabel) {
      cells.push(el('span', { className: 'modal-bbox-row__label', title: box && box.label, text: leafLabel(box && box.label) }));
    }
    cells.push(el('button', {
      type: 'button',
      className: 'modal-bbox-row__time',
      'data-action': 'goto',
      'data-index': index,
      title: [extent.time, extent.freq].filter(Boolean).join(' · ') + ' · show on the spectrogram',
      text: extent.time,
    }));
    cells.push(el('span', { className: 'modal-bbox-row__freq', text: extent.freq }));

    let tagCell = null;
    if (!view.editable) {
      if (tag || options.length) {
        tagCell = el('span', { className: 'modal-bbox-row__tags' }, [
          el('span', { className: 'modal-bbox-tag is-static' + (tag ? '' : ' is-empty'), text: tag ? tagLabel(tag, view.allOptions) : 'No tag' }),
        ]);
      }
    } else if (!options.length) {
      // A species without tags: a tag it carries anyway stays visible, and
      // clicking it removes it.
      if (tag) {
        tagCell = el('span', { className: 'modal-bbox-row__tags', role: 'group', 'aria-label': 'Tag for box ' + number }, [
          tagButton({ value: tag, label: tagLabel(tag, view.allOptions) }, true, {
            'data-action': 'tag',
            'data-index': index,
            'data-tag': tag,
            title: 'Remove tag',
          }),
        ]);
      }
    } else if (options.length > CHIP_LIMIT) {
      const select = el('select', {
        className: 'modal-bbox-row__select-tag form-select form-select-sm',
        'data-action': 'tag-select',
        'data-index': index,
        'aria-label': 'Tag for box ' + number,
      }, [el('option', { value: '', text: 'No tag' })].concat(options.map(function (option) {
        return el('option', { value: option.value, text: option.label });
      })));
      select.value = tag || '';
      tagCell = el('span', { className: 'modal-bbox-row__tags' }, [select]);
    } else {
      tagCell = el('span', {
        className: 'modal-bbox-row__tags',
        role: 'group',
        'aria-label': 'Tag for box ' + number,
      }, options.map(function (option) {
        return tagButton(option, option.value === tag, {
          'data-action': 'tag',
          'data-index': index,
          'data-tag': option.value,
          title: option.value === tag ? 'Remove tag' : 'Tag box ' + number + ' as ' + option.label,
        });
      }));
    }
    // Tags a model suggested are marked until a reviewer sets their own.
    if (tag && box && box.tag_source === 'model') {
      cells.push(el('i', {
        className: 'bi bi-robot modal-bbox-row__model-tag',
        title: 'Machine box tag',
        'aria-label': 'Machine box tag',
      }));
    }
    if (tagCell) {
      cells.push(tagCell);
    }
    if (view.editable) {
      cells.push(el('button', {
        type: 'button',
        className: 'modal-bbox-row__edit',
        'data-action': 'edit',
        'data-index': index,
        title: 'Edit box ' + number,
        'aria-label': 'Edit box ' + number,
      }, [el('i', { className: 'bi bi-pencil-square', 'aria-hidden': 'true' })]));
    }
    return el('div', {
      className: 'modal-bbox-row' + (tag || !options.length ? '' : ' is-untagged') + (ui.selected.has(index) ? ' is-selected' : '')
        + (multiLabel ? ' has-label' : '') + (selectable ? ' has-select' : '')
        + (view.editable ? '' : ' is-readonly'),
      role: 'listitem',
      'data-index': index,
    }, cells);
  }

  function patchRows(list, previousCount) {
    const scrollTop = list.scrollTop;
    const focus = focusedControl(list);
    const labels = new Set(view.boxes.map(function (box) { return String((box && box.label) || '').trim(); }));
    const multiLabel = labels.size > 1;
    const indices = visibleIndices();
    const existing = {};
    Array.from(list.children).forEach(function (child) {
      if (child.classList.contains('modal-bbox-row')) {
        existing[child.getAttribute('data-index')] = child;
      } else {
        child.remove();
      }
    });
    // Everything before `cursor` is already in its final order.
    let cursor = list.firstChild;
    indices.forEach(function (index) {
      const box = view.boxes[index];
      const signature = rowSignature(box, multiLabel);
      let row = existing[index];
      delete existing[index];
      if (row && row.getAttribute('data-sig') !== signature) {
        const fresh = buildRow(box, index, multiLabel);
        fresh.setAttribute('data-sig', signature);
        if (cursor === row) {
          cursor = fresh;
        }
        row.replaceWith(fresh);
        row = fresh;
      } else if (!row) {
        row = buildRow(box, index, multiLabel);
        row.setAttribute('data-sig', signature);
      }
      syncSelection(row, index);
      if (row === cursor) {
        cursor = cursor.nextSibling;
      } else {
        list.insertBefore(row, cursor);
      }
    });
    Object.keys(existing).forEach(function (key) { existing[key].remove(); });
    if (!indices.length) {
      list.appendChild(el('div', {
        className: 'modal-bbox-empty',
        text: view.boxes.length
          ? 'Every box has a tag.'
          : (view.editable ? 'No boxes yet. Press Draw (B), then drag on the spectrogram.' : 'No boxes.'),
      }));
    }
    list.scrollTop = scrollTop;
    restoreFocus(list, focus);
    // Bring a newly drawn box into view without moving the rest of the page.
    if (previousCount !== null && view.boxes.length === previousCount + 1) {
      const newest = list.querySelector('[data-index="' + (view.boxes.length - 1) + '"]');
      if (newest) {
        const below = newest.offsetTop + newest.offsetHeight - (list.scrollTop + list.clientHeight);
        if (below > 0) {
          list.scrollTop += below + 4;
        }
      }
    }
  }

  function renderHeader(header, summary) {
    header.textContent = '';
    const chips = summary.tags.filter(function (tag) { return tag.count > 0; }).map(function (tag) {
      return el('span', { className: 'modal-bbox-summary__item' }, [tag.label + ' ', el('b', { text: String(tag.count) })]);
    });
    // Only boxes of a species with tags can be untagged.
    if (summary.taggable || ui.untaggedOnly) {
      chips.push(el('button', {
        type: 'button',
        className: 'modal-bbox-summary__untagged' + (summary.untagged ? '' : ' is-zero') + (ui.untaggedOnly ? ' is-active' : ''),
        'data-action': 'filter-untagged',
        'aria-pressed': ui.untaggedOnly ? 'true' : 'false',
        title: ui.untaggedOnly ? 'Show all boxes' : 'Show only untagged boxes',
        disabled: !summary.untagged && !ui.untaggedOnly,
      }, ['Untagged ', el('b', { text: String(summary.untagged) })]));
    }
    header.appendChild(el('div', { className: 'modal-bbox-panel__title' }, [
      'Boxes', el('span', { className: 'modal-bbox-count', text: String(summary.total) }),
    ]));
    header.appendChild(el('div', { className: 'modal-bbox-summary', 'aria-live': 'polite' }, chips));
    header.appendChild(el('button', {
      type: 'button',
      className: 'modal-bbox-expand btn btn-sm btn-outline-secondary',
      'data-action': 'toggle-expand',
      'aria-expanded': ui.expanded ? 'true' : 'false',
    }, [
      el('i', { className: ui.expanded ? 'bi bi-arrows-collapse' : 'bi bi-arrows-expand', 'aria-hidden': 'true' }),
      ui.expanded ? ' Shrink list' : ' Enlarge list',
    ]));
  }

  function renderBulk(bulk) {
    bulk.textContent = '';
    const show = view.editable && view.bulk && view.anyTaggable;
    bulk.hidden = !show;
    if (!show) {
      return;
    }
    const visible = selectableIndices();
    const selectedVisible = visible.filter(function (index) { return ui.selected.has(index); }).length;
    const count = ui.selected.size;
    bulk.appendChild(el('label', { className: 'modal-bbox-bulk__all' }, [
      el('input', {
        type: 'checkbox',
        className: 'form-check-input',
        'data-action': 'select-all',
        checked: visible.length > 0 && selectedVisible === visible.length,
        indeterminate: selectedVisible > 0 && selectedVisible < visible.length,
        'aria-label': 'Select all listed boxes',
      }),
      ' All',
    ]));
    bulk.appendChild(el('button', {
      type: 'button',
      className: 'modal-bbox-bulk__link',
      'data-action': 'select-untagged',
      disabled: !untaggedIndices(view.boxes, boxOptions).length,
    }, ['Select untagged']));
    bulk.appendChild(el('span', { className: 'modal-bbox-bulk__count', text: count + ' selected' }));
    // Each tag goes only to selected boxes of a species that has it.
    const apply = normalizeOptions([].concat.apply([], view.boxes.map(function (box) {
      return boxOptions(box && box.label);
    }))).map(function (option) {
      return tagButton(option, false, { 'data-action': 'bulk-tag', 'data-tag': option.value, disabled: !count });
    });
    apply.push(tagButton({ value: '', label: 'No tag' }, false, {
      'data-action': 'bulk-tag',
      'data-tag': '',
      disabled: !count,
    }));
    bulk.appendChild(el('span', { className: 'modal-bbox-bulk__apply' }, [
      el('span', { className: 'modal-bbox-bulk__apply-label', text: 'Tag selected:' }),
    ].concat(apply)));
    if (count) {
      bulk.appendChild(el('button', {
        type: 'button',
        className: 'modal-bbox-bulk__link',
        'data-action': 'clear-selection',
      }, ['Clear']));
    }
  }

  function ensurePanelStructure(root) {
    if (root.getAttribute('data-bbox-ready') === '1') {
      return;
    }
    root.textContent = '';
    root.appendChild(el('div', { className: 'modal-bbox-panel__header' }));
    root.appendChild(el('div', { className: 'modal-bbox-bulk' }));
    root.appendChild(el('div', { className: 'modal-bbox-note' }));
    root.appendChild(el('div', { className: 'modal-bbox-list', role: 'list', 'aria-label': 'Boxes' }));
    root.setAttribute('data-bbox-ready', '1');
  }

  function renderPanel(root, previousCount) {
    ensurePanelStructure(root);
    const summary = summarize(view.boxes, boxOptions);
    renderHeader(root.querySelector('.modal-bbox-panel__header'), summary);
    renderBulk(root.querySelector('.modal-bbox-bulk'));
    const note = root.querySelector('.modal-bbox-note');
    note.textContent = view.readOnlyReason;
    note.hidden = !view.readOnlyReason;
    const list = root.querySelector('.modal-bbox-list');
    list.classList.toggle('is-expanded', ui.expanded);
    patchRows(list, previousCount);
  }

  function renderNow(previousCount) {
    const toolbar = document.getElementById(TOOLBAR_ID);
    const panel = document.getElementById(PANEL_ID);
    if (!toolbar || !panel) {
      return false;
    }
    bind(toolbar);
    bind(panel);
    view.anyTaggable = view.boxes.some(canTag);
    renderToolbar(toolbar);
    renderPanel(panel, previousCount);
    // The clip overview under the plot marks every box (modal_paging.js), and
    // the other spectrograms show them (modal_range_panels.js).
    if (window.modalPaging) {
      window.modalPaging.refresh();
    }
    if (window.modalRangePanels && typeof window.modalRangePanels.schedule === 'function') {
      window.modalRangePanels.schedule();
    }
    return true;
  }

  // Render now if the modal body is mounted; otherwise retry for a few frames,
  // since it mounts shortly after is_open flips.
  function refresh(previousCount) {
    const count = previousCount === undefined ? null : previousCount;
    if (renderFrame !== null) {
      window.cancelAnimationFrame(renderFrame);
      renderFrame = null;
    }
    if (renderNow(count)) {
      return;
    }
    let attempts = 0;
    const attempt = function () {
      renderFrame = null;
      if (!renderNow(count) && view.open && attempts < 30) {
        attempts += 1;
        renderFrame = window.requestAnimationFrame(attempt);
      }
    };
    renderFrame = window.requestAnimationFrame(attempt);
  }

  // ---------------------------------------------------------------------------
  // Events
  // ---------------------------------------------------------------------------

  function indexOf(target) {
    const index = Number(target.getAttribute('data-index'));
    return Number.isInteger(index) && index >= 0 && index < view.boxes.length ? index : null;
  }

  // Page a long clip to the box (modal_paging.js).
  function showBox(index) {
    const extent = view.boxes[index] && view.boxes[index].annotation_extent;
    const start = Number(extent && extent.time_start_sec);
    const end = Number(extent && extent.time_end_sec);
    const meta = figureMeta();
    if (window.modalPaging && meta && Number.isFinite(start) && Number.isFinite(end)) {
      const xToSeconds = Number(meta.x_to_seconds) || 1;
      window.modalPaging.show(start / xToSeconds, end / xToSeconds);
    }
  }

  function figureMeta() {
    const plot = document.querySelector('#modal-image-graph .js-plotly-plot');
    return (plot && plot.layout && plot.layout.meta) || null;
  }

  function onClick(event) {
    const target = event.target.closest('[data-action]');
    if (!target || target.disabled || !event.currentTarget.contains(target)) {
      return;
    }
    const action = target.getAttribute('data-action');
    const index = indexOf(target);
    if (action === 'tag' && index !== null) {
      const tag = cleanTag(target.getAttribute('data-tag'));
      // Clicking the current tag again removes it.
      tagBoxes([index], cleanTag(view.boxes[index] && view.boxes[index].tag) === tag ? null : tag);
    } else if (action === 'bulk-tag') {
      const tag = cleanTag(target.getAttribute('data-tag'));
      const selected = Array.from(ui.selected).sort(function (a, b) { return a - b; }).filter(function (candidate) {
        const box = view.boxes[candidate];
        return !tag || boxOptions(box && box.label).some(function (option) { return option.value === tag; });
      });
      ui.selected.clear();
      tagBoxes(selected, tag);
      refresh();
    } else if (action === 'active-tag') {
      setActiveTag(target.getAttribute('data-tag'));
    } else if (action === 'toggle-draw' && window.bboxDrawMode) {
      window.bboxDrawMode.toggle();
    } else if (action === 'edit' && index !== null) {
      openEditor(index);
    } else if (action === 'select-untagged') {
      untaggedIndices(view.boxes, boxOptions).forEach(function (candidate) { ui.selected.add(candidate); });
      refresh();
    } else if (action === 'clear-selection') {
      ui.selected.clear();
      refresh();
    } else if (action === 'filter-untagged') {
      ui.untaggedOnly = !ui.untaggedOnly;
      refresh();
    } else if (action === 'toggle-expand') {
      ui.expanded = !ui.expanded;
      writeExpanded(ui.expanded);
      refresh();
    } else if (action === 'goto' && index !== null) {
      showBox(index);
    } else if (action === 'jump') {
      const panel = document.getElementById(PANEL_ID);
      if (panel) {
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    } else if (action === 'open-profile') {
      const profile = document.getElementById('profile-btn');
      if (profile) {
        profile.click();
      }
    }
  }

  function onChange(event) {
    const target = event.target;
    const action = target.getAttribute('data-action');
    const index = indexOf(target);
    if (action === 'select' && index !== null) {
      if (target.checked) {
        ui.selected.add(index);
      } else {
        ui.selected.delete(index);
      }
      // Only the bulk bar changes; the row itself keeps its elements and focus.
      const panel = document.getElementById(PANEL_ID);
      const row = target.closest('.modal-bbox-row');
      if (row) {
        syncSelection(row, index);
      }
      if (panel) {
        renderBulk(panel.querySelector('.modal-bbox-bulk'));
      }
    } else if (action === 'select-all') {
      const visible = selectableIndices();
      visible.forEach(function (candidate) {
        if (target.checked) {
          ui.selected.add(candidate);
        } else {
          ui.selected.delete(candidate);
        }
      });
      refresh();
    } else if (action === 'tag-select' && index !== null) {
      tagBoxes([index], target.value);
    } else if (action === 'draw-label' && window.bboxDrawMode) {
      window.bboxDrawMode.setLabel(target.value);
    }
  }

  function openEditor(index) {
    if (!view.editable || index === null || index < 0 || index >= view.boxes.length) {
      return false;
    }
    setProps('modal-bbox-edit-request-store', {
      data: { item_id: view.itemId, index: index, nonce: Date.now() + Math.random() },
    });
    return true;
  }

  // Outline a box on the spectrogram while its row is hovered. Shapes are
  // named "bbox-<index>" by the figure builders.
  function highlightShape(index) {
    const graph = document.querySelector('#modal-image-graph .js-plotly-plot');
    const shapes = graph && graph.layout && Array.isArray(graph.layout.shapes) ? graph.layout.shapes : [];
    if (!graph) {
      return;
    }
    graph.querySelectorAll('.shapelayer path[data-index]').forEach(function (path) {
      const shape = shapes[Number(path.getAttribute('data-index'))];
      path.classList.toggle('modal-bbox-shape--hovered', index !== null && !!shape && shape.name === 'bbox-' + index);
    });
  }

  function onRowHover(event) {
    const row = event.target.closest('.modal-bbox-row');
    const related = event.relatedTarget && event.relatedTarget.closest
      ? event.relatedTarget.closest('.modal-bbox-row')
      : null;
    if (row === related) {
      return; // moving between elements inside the same row
    }
    if (event.type === 'mouseover') {
      highlightShape(row ? indexOf(row) : null);
    } else if (!related) {
      highlightShape(null);
    }
  }

  function bind(root) {
    if (root.getAttribute('data-bbox-bound') === '1') {
      return;
    }
    root.addEventListener('click', onClick);
    root.addEventListener('change', onChange);
    root.addEventListener('mouseover', onRowHover);
    root.addEventListener('mouseout', onRowHover);
    root.setAttribute('data-bbox-bound', '1');
  }

  // Used by modal_shortcuts.js (number keys, after its focus/dialog checks)
  // and bbox_hover_affordances.js (hovering or editing boxes on the plot).
  window.bboxPanel = {
    handleTagKey: function (key) {
      const options = newBoxOptions();
      if (!view.editable || !view.open || !options.length) {
        return false;
      }
      const tag = tagForKey(key, options);
      if (tag === undefined) {
        return false;
      }
      setActiveTag(tag);
      return true;
    },
    openEditor: openEditor,
    boxes: function () {
      return view.boxes;
    },
    canEdit: function () {
      return view.editable && view.open;
    },
    describeBox: function (index) {
      const box = view.boxes[index];
      if (!box || typeof box !== 'object') {
        return null;
      }
      const tag = cleanTag(box.tag);
      const extent = describeExtent(box.annotation_extent);
      const taggable = boxOptions(box.label).length > 0;
      return {
        title: 'Box ' + (index + 1),
        // A species without tags shows none.
        tag: tag ? tagLabel(tag, view.allOptions) : (taggable ? 'No tag' : null),
        untagged: !tag && taggable,
        detail: leafLabel(box.label) + ' · ' + extent.time + ' · ' + extent.freq,
      };
    },
    // For the clip overview under the plot (modal_paging.js).
    needsTag: needsTag,
    // A box drawn on another spectrogram: the label being drawn, and the tag
    // for new boxes if that species has it.
    addBox: function (extent) {
      const draw = window.bboxDrawMode;
      const label = draw && typeof draw.label === 'function' ? draw.label() : null;
      if (!view.editable || !view.open || !view.itemId || !label || !extent) {
        return false;
      }
      const box = { label: label, annotation_extent: extent, source: 'manual', decision: 'added' };
      const tag = boxOptions(label).some(function (option) { return option.value === view.activeTag; }) ? view.activeTag : null;
      if (tag) {
        box.tag = tag;
        box.tag_source = 'human';
        box.tag_scope = 'time_freq_box';
      }
      setProps('modal-bbox-command-store', {
        data: { action: 'add_box', item_id: view.itemId, box: box, nonce: Date.now() + Math.random() },
      });
      return true;
    },
    highlightRow: function (index) {
      const panel = document.getElementById(PANEL_ID);
      if (!panel) {
        return;
      }
      panel.querySelectorAll('.modal-bbox-row.is-hovered').forEach(function (row) {
        if (Number(row.getAttribute('data-index')) !== index) {
          row.classList.remove('is-hovered');
        }
      });
      const row = index === null ? null : panel.querySelector('.modal-bbox-row[data-index="' + index + '"]');
      if (row) {
        row.classList.add('is-hovered');
      }
    },
  };

  // Redraw the toolbar when draw mode or the drawable labels change.
  if (window.bboxDrawMode) {
    window.bboxDrawMode.subscribe(function () {
      const toolbar = document.getElementById(TOOLBAR_ID);
      if (toolbar) {
        renderToolbar(toolbar);
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Dash clientside callbacks
  // ---------------------------------------------------------------------------

  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    bboxList: {
      render: function (bboxStore, activeTag, mode, currentItemId, profile, isOpen, listConfig) {
        const config = listConfig && typeof listConfig === 'object' ? listConfig : {};
        const store = bboxStore && typeof bboxStore === 'object' ? bboxStore : {};
        const itemId = currentItemId || null;
        const boxes = store.item_id === itemId && Array.isArray(store.boxes) ? store.boxes : [];
        const complete = typeof interactions().profileIsComplete === 'function'
          ? interactions().profileIsComplete(profile)
          : false;
        view.tagSets = normalizeTagSets(config);
        view.allOptions = allOptions(view.tagSets);
        view.bulk = config.bulk_tagging !== false;
        view.open = Boolean(isOpen);
        view.editable = Boolean(itemId) && mode !== 'explore' && complete;
        view.needsProfile = Boolean(itemId) && mode !== 'explore' && !complete;
        view.readOnlyReason = !itemId || view.editable ? ''
          : (mode === 'explore' ? 'Explore mode: boxes are read-only.' : 'Add your name and email in Profile to edit boxes.');
        const remembered = cleanTag(activeTag);
        // Kept while drawing another species, for when a species with this tag is drawn again.
        let active = view.allOptions.some(function (option) { return option.value === remembered; }) ? remembered : null;
        // A render queued before the store took the reviewer's new choice must not undo it.
        if (ui.pendingActive) {
          if (ui.pendingActive.tag === active || Date.now() - ui.pendingActive.at > PENDING_MS) {
            ui.pendingActive = null;
          } else {
            active = ui.pendingActive.tag;
          }
        }
        view.activeTag = active;

        let previousCount = null;
        if (ui.itemId !== itemId) {
          ui.itemId = itemId;
          ui.selected.clear();
          ui.pending.clear();
          ui.untaggedOnly = false;
          const panel = document.getElementById(PANEL_ID);
          const list = panel && panel.querySelector('.modal-bbox-list');
          if (list) {
            list.textContent = '';
            list.scrollTop = 0;
          }
        } else {
          previousCount = ui.boxCount;
          if (boxes.length !== ui.boxCount) {
            // Deleting or adding boxes shifts indices, so drop index-based state.
            ui.selected.clear();
            ui.pending.clear();
          }
        }
        ui.boxCount = boxes.length;
        view.itemId = itemId;
        view.boxes = withPendingTags(boxes);
        refresh(previousCount);
        return (window.dash_clientside || {}).no_update;
      },

      applyCommand: function (command, bboxStore, figure, currentItemId, mode, profile) {
        const noUpdate = (window.dash_clientside || {}).no_update;
        const unchanged = [noUpdate, noUpdate, noUpdate];
        const complete = typeof interactions().profileIsComplete === 'function'
          && interactions().profileIsComplete(profile);
        const apply = interactions().applyBoxesToFigure;
        // A box drawn on another spectrogram in the modal (modal_range_panels.js).
        if (command && command.action === 'add_box') {
          if (
            mode === 'explore' || !complete || !currentItemId || command.item_id !== currentItemId ||
            !command.box || typeof command.box !== 'object'
          ) {
            return unchanged;
          }
          const current = bboxStore && typeof bboxStore === 'object' && bboxStore.item_id === currentItemId
            ? bboxStore
            : { item_id: currentItemId, boxes: [] };
          const boxes = (Array.isArray(current.boxes) ? current.boxes : []).concat([command.box]);
          return [
            Object.assign({}, current, { item_id: currentItemId, boxes: boxes }),
            figure && typeof apply === 'function' ? apply(figure, boxes) : noUpdate,
            { dirty: true, item_id: currentItemId },
          ];
        }
        // "Delete box" in the box editor.
        if (command && command.action === 'delete_box') {
          const index = Number(command.index);
          const current = bboxStore && typeof bboxStore === 'object' && bboxStore.item_id === currentItemId ? bboxStore : null;
          if (
            mode === 'explore' || !complete || !currentItemId || command.item_id !== currentItemId || !current ||
            !Array.isArray(current.boxes) || !Number.isInteger(index) || index < 0 || index >= current.boxes.length
          ) {
            return unchanged;
          }
          const boxes = current.boxes.filter(function (_box, position) { return position !== index; });
          return [
            Object.assign({}, current, { boxes: boxes }),
            figure && typeof apply === 'function' ? apply(figure, boxes) : noUpdate,
            { dirty: true, item_id: currentItemId },
          ];
        }
        // Re-place box handles for a new page length (modal_paging.js); the
        // boxes themselves do not change.
        if (command && command.action === 'redraw') {
          const current = bboxStore && bboxStore.item_id === currentItemId ? bboxStore.boxes : null;
          return current && figure && typeof apply === 'function' && command.item_id === currentItemId
            ? [noUpdate, apply(figure, current), noUpdate]
            : unchanged;
        }
        if (
          !command || command.action !== 'set_tags' || mode === 'explore' || !complete ||
          !currentItemId || command.item_id !== currentItemId
        ) {
          return unchanged;
        }
        const store = bboxStore && typeof bboxStore === 'object' ? bboxStore : {};
        if (store.item_id !== currentItemId) {
          return unchanged;
        }
        const result = applyTagChanges(store.boxes, command.changes);
        if (!result.changed) {
          return unchanged;
        }
        return [
          Object.assign({}, store, { boxes: result.boxes }),
          figure && typeof apply === 'function' ? apply(figure, result.boxes) : noUpdate,
          { dirty: true, item_id: currentItemId },
        ];
      },

      deleteFromEditor: function (clicks, index, currentItemId) {
        const noUpdate = (window.dash_clientside || {}).no_update;
        const boxIndex = Number(index);
        if (!clicks || !currentItemId || !Number.isInteger(boxIndex) || boxIndex < 0) {
          return noUpdate;
        }
        setProps('modal-bbox-command-store', {
          data: { action: 'delete_box', item_id: currentItemId, index: boxIndex, nonce: Date.now() + Math.random() },
        });
        return false;
      },

      // The box editor offers the tags of the species chosen in it; a tag the
      // box already has stays listed so it can be seen and cleared.
      editorTagOptions: function (label, value, listConfig) {
        const sets = normalizeTagSets(listConfig);
        const options = optionsForLabel(sets, label).map(function (option) {
          return { label: option.label, value: option.value };
        });
        const current = cleanTag(value);
        if (current && !options.some(function (option) { return option.value === current; })) {
          options.push({ label: tagLabel(current, allOptions(sets)), value: current });
        }
        return options;
      },
    },
  });
}());
