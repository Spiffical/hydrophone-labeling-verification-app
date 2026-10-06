const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

// Just enough DOM for the pager and overview to render.
class FakeElement {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.childNodes = [];
    this.attributes = {};
    this.style = {};
    this.className = '';
    this.hidden = false;
    this.value = '';
  }
  set textContent(value) { this.childNodes = value ? [String(value)] : []; }
  get textContent() { return this.childNodes.map(c => (typeof c === 'string' ? c : c.textContent)).join(''); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return name in this.attributes ? this.attributes[name] : null; }
  appendChild(child) { this.childNodes.push(child); return child; }
  getBoundingClientRect() { return { left: 0, top: 0, width: 790, height: 16 }; }
  querySelector() { return null; }
}

function load({ xMax = 1394, stored = null } = {}) {
  const relayouts = [];
  const handlers = {};
  const gd = {
    layout: { meta: { modal_item_id: 'clip-a', x_min: 0, x_max: xMax, x_to_seconds: 1, page_seconds: 300, page_seconds_options: [300, 120] } },
    _fullLayout: { xaxis: { range: [0, 300] } },
    on(name, handler) { handlers[name] = handler; },
    querySelector: () => new FakeElement('rect'),
  };
  const elements = { 'modal-page-bar': new FakeElement('div'), 'modal-page-overview': new FakeElement('div') };
  const window = {
    localStorage: { getItem: () => stored, setItem: (key, value) => { stored = value; } },
    addEventListener() {},
    Plotly: {
      relayout(target, update) {
        relayouts.push({ update: JSON.parse(JSON.stringify(update)), gui: target._fullLayout._guiEditing === true });
        if (update['xaxis.range']) target._fullLayout.xaxis.range = update['xaxis.range'].slice();
        if (handlers.plotly_relayout) handlers.plotly_relayout(update);
        return Promise.resolve();
      },
    },
    dash_clientside: { set_props() {} },
  };
  const documentListeners = {};
  const document = {
    documentElement: {},
    getElementById: id => elements[id] || null,
    querySelector: selector => (selector.includes('js-plotly-plot') ? gd : null),
    createElement: tag => new FakeElement(tag),
    createTextNode: text => String(text),
    addEventListener(name, handler) { (documentListeners[name] = documentListeners[name] || []).push(handler); },
  };
  // The graph is bound when it appears; here it is there from the start.
  class MutationObserver {
    constructor(callback) { this.callback = callback; }
    observe() { this.callback([{ target: { closest: () => true } }]); }
  }
  const context = { window, document, MutationObserver, Promise };
  for (const file of ['modal_pages.js', 'modal_paging.js']) {
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/assets', file), 'utf8'), context);
  }
  const flush = () => new Promise(resolve => setImmediate(resolve));
  // The player at `seconds` (x = seconds on these clips), playing.
  const audio = { id: 'modal-player-audio', paused: false, currentTime: 0 };
  const playAt = (seconds) => {
    audio.currentTime = seconds;
    (documentListeners.timeupdate || []).forEach(handler => handler({ target: audio }));
  };
  return { window, gd, handlers, relayouts, elements, flush, playAt };
}

test('page windows match the server: equal widths, the last page ends with the clip', () => {
  const { window } = load();
  const pages = window.modalPages;
  assert.deepEqual(JSON.parse(JSON.stringify(pages.windows(0, 1394, 300))),
    [[0, 300], [300, 600], [600, 900], [900, 1200], [1094, 1394]]);
  assert.deepEqual(JSON.parse(JSON.stringify(pages.windows(0, 320, 300))), [[0, 320]]);
  assert.deepEqual(JSON.parse(JSON.stringify(pages.windowForRange(295, 305, pages.windows(0, 1394, 300)))), [0, 300]);
});

test('the pager steps through pages as GUI edits so Dash re-plots keep them', async () => {
  const s = load();
  assert.equal(s.relayouts.length, 0, 'the server already opened the first page');
  assert.match(s.elements['modal-page-bar'].textContent, /0–300 s · 1 \/ 5/);
  assert.equal(s.window.modalPaging.step(1), true);
  await s.flush();
  assert.deepEqual(s.relayouts[0], { update: { 'xaxis.range': [300, 600], 'xaxis.autorange': false }, gui: true });
  assert.equal(s.gd._fullLayout._guiEditing, false, 'the flag is only set during the call');
  assert.match(s.elements['modal-page-bar'].textContent, /300–600 s · 2 \/ 5/);
});

test('a re-plot that loses the page puts it back; a new clip starts on page one', async () => {
  const s = load();
  s.window.modalPaging.step(1);
  await s.flush();
  // Dash sends a figure from the server (new layout object) that shows page one.
  s.gd.layout = Object.assign({}, s.gd.layout);
  s.gd._fullLayout.xaxis.range = [0, 300];
  s.handlers.plotly_afterplot();
  await s.flush();
  assert.deepEqual(s.relayouts[1].update['xaxis.range'], [300, 600]);
  assert.equal(s.relayouts[1].gui, true);

  s.gd.layout = Object.assign({}, s.gd.layout, { meta: Object.assign({}, s.gd.layout.meta, { modal_item_id: 'clip-b' }) });
  s.gd._fullLayout.xaxis.range = [0, 300];
  s.handlers.plotly_afterplot();
  await s.flush();
  assert.equal(s.relayouts.length, 2, 'already on the first page of the new clip');
});

test('Home after a double-click returns to the page that was on screen', async () => {
  const s = load();
  s.window.modalPaging.goTo(3);
  await s.flush();
  // The reviewer zooms in, then double-clicks: Plotly first shows the whole clip.
  s.gd._fullLayout.xaxis.range = [950, 1000];
  s.handlers.plotly_relayout({ 'xaxis.range[0]': 950, 'xaxis.range[1]': 1000 });
  s.gd._fullLayout.xaxis.range = [0, 1394];
  s.handlers.plotly_relayout({ 'xaxis.autorange': true });
  assert.deepEqual(Array.from(s.window.modalPaging.homeRange()), [900, 1200]);
});

test('showing a box goes to its page, and 120 s pages are offered', async () => {
  const s = load({ stored: '120' });
  // The stored 120 s choice applies to this dashboard, which offers it.
  s.gd.layout = Object.assign({}, s.gd.layout);
  s.handlers.plotly_afterplot();
  await s.flush();
  assert.deepEqual(s.relayouts[0].update['xaxis.range'], [0, 120]);
  assert.match(s.elements['modal-page-bar'].textContent, /1 \/ 12/);
  s.window.modalPaging.show(1050, 1053);
  await s.flush();
  assert.deepEqual(s.relayouts[1].update['xaxis.range'], [960, 1080]);
});

test('clips that fit on a page get no pager or overview', () => {
  const s = load({ xMax: 14.3 });
  s.gd._fullLayout.xaxis.range = [0, 14.3];
  s.window.modalPaging.refresh();
  assert.equal(s.elements['modal-page-bar'].hidden, true);
  assert.equal(s.elements['modal-page-overview'].hidden, true);
  assert.equal(s.window.modalPaging.step(1), false);
});

test('playback turns the page when it runs off the page on screen', async () => {
  const s = load();
  s.playAt(290);
  s.playAt(301);
  await s.flush();
  assert.deepEqual(s.relayouts.at(-1).update['xaxis.range'], [300, 600]);
});

test('zoomed in, playback moves the view on by its width and keeps the zoom', async () => {
  const s = load();
  s.gd._fullLayout.xaxis.range = [100, 110];
  s.playAt(108);
  s.playAt(110.4);
  await s.flush();
  assert.deepEqual(s.relayouts.at(-1).update['xaxis.range'], [110, 120]);
  // At the end of the clip the view stops at its end.
  s.gd._fullLayout.xaxis.range = [1380, 1390];
  s.playAt(1389);
  s.playAt(1391);
  await s.flush();
  assert.deepEqual(s.relayouts.at(-1).update['xaxis.range'], [1384, 1394]);
});

test('a view the reviewer moved away from the playhead stays put', async () => {
  const s = load();
  s.playAt(100);
  // The reviewer zooms in somewhere else while it plays.
  s.gd._fullLayout.xaxis.range = [500, 510];
  s.playAt(100.3);
  s.playAt(100.6);
  await s.flush();
  assert.equal(s.relayouts.length, 0);
});
