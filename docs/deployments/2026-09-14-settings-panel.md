# Spectrogram settings viewport fix

The compact settings popup's fixed right offset placed its left edge at -88 px
in a 1065 × 755 browser viewport. Its desktop height was also unconstrained.

Added `app/assets/spectrogram_panel_position.js` and
`app/assets/zz_spectrogram_panel.css`. The popup width and horizontal position
are constrained to the visible viewport with 12 px margins; its height is
limited to available space and its contents scroll. Toggle, window resize,
page scroll and visual viewport changes recalculate the position. The actual
containing block is measured to account for the toolbar's backdrop filter.
Noncompact inline settings are unaffected.

Deployed only this change to the active anomaly dashboard on port 18053.
Because Dash's running asset list is fixed, appended the JS and CSS to the
already loaded `command_panels.js` and `styles.css` respectively. No server
restart was needed. Existing source and live reviews were preserved.
The exact deployed diff is `2026-09-14-settings-panel.patch`; original assets
are backed up on oncvm-daq in `/home/sbialek/ONC/review-ui-20260914/panel-before`.

Live browser checks passed at 1065 × 755, 390 × 640, 1065 × 420, and
1440 × 900, including resizing while open and scrolling to the bottom controls
on mobile. The popup remained within the viewport, and no browser console
errors were reported. JavaScript syntax and whitespace checks passed.

Whale-call-analysis changes were inspected only. No multi-range, grid-layout,
colormap, or cache-freshness changes from that project were imported.
