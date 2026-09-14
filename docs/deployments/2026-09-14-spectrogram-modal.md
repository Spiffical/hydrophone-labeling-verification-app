# Responsive spectrogram modal

Reproduced on the active anomaly-review app at port 18053 using September 7
clips. At 962 × 715, the dialog was only 500 px wide, its content extended to
y=1884, and the Next and header Close buttons were at x=1195 and x=1245,
outside both the dialog and viewport. The long filename's intrinsic width
prevented the flex header from shrinking.

Added `app/assets/zz_spectrogram_modal.css`:

- Use available width up to 1140 px, leaving 12 px viewport margins.
- Constrain dialog height to the dynamic viewport; scroll the body while
  retaining the header/navigation and footer Close button.
- Wrap long filenames inside a shrinkable grid column. On phones, place
  navigation in a separate row and reserve a column for Close.
- Scale graph height to the screen and reflow frequency/contrast controls on
  narrow screens. Very short screens cap the title height with text scrolling.

Deployed the same CSS by appending it to the live app's existing `styles.css`,
preserving all other changes and avoiding a server restart. Original stylesheet:
`/home/sbialek/ONC/review-ui-20260914/modal-before/styles.css` on oncvm-daq.
The exact stylesheet diff is `2026-09-14-spectrogram-modal.patch`.

Live browser validation covered 962 × 715, 390 × 640, 812 × 375,
320 × 568 and 1440 × 900. Checked resize while open, expanded display
settings, horizontal bounds, scrolling to Save/Edit labels and audio controls,
Next (item 1 → 2), and both Close buttons. The plot resizes with the dialog.
No review labels or annotations were changed or saved during this check.
Whitespace checks passed; no Python/callback changes were required.
