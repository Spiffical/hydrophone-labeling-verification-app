# Label editor save response fix — September 15, 2026

Live error logs showed `InvalidCallbackReturnValue` in `save_label_editor`: wildcard output 9 expected a list but received scalar `no_update`. This occurred when the edited clip was no longer among the mounted verification cards, such as editing again from a modal after saving under Unverified only. Label mode also returned scalar no-update values for these wildcard outputs.

The callback writes to disk before Dash validates the returned response. Consequently the old failure could leave the editor open and grid stale even though the verification had already persisted. This change does not remove or rewrite prior user verifications.

The shared verification-card update helper now always returns correctly sized lists, including empty lists when no cards are mounted and per-card no-update entries when the edited clip is absent. The label editor's other return paths follow the same rule. The shared fix also protects other review actions using that helper.

Validation:

- Added 12 HTTP endpoint cases covering Verify/Label modes, zero/matching/unrelated cards, and open/closed spectrogram modals. Ten failed before the fix; all pass afterward. Assertions cover actual JSON persistence, new label decisions, editor closure, modal labels, and retained queue counts.
- Full local suite: 224 passed, 4 skipped. Server-runtime review queue suite: 27 passed.
- Browser with disposable local data: add/save from a card, then save a second clip from its modal under Unverified only and add another label while that clip is absent from the grid. The editor closed and the modal showed the added label; only the untouched clip remained in the grid. Saved JSON confirmed both additions. The fixture had no audio, producing unrelated missing-audio-state console warnings; no save HTTP 500 occurred.
- Test writes were confined to disposable data; no live expert annotations were changed by testing.

Deployed two callback/helper files and the regression tests to `/home/sbialek/ONC/hydrophone-review-current`. Hash checks confirmed the expected source before deployment and the new source afterward. Backup and manifest: `/home/sbialek/ONC/label-save-fix-20260915/`. Only `verify-september-2026` on port 18053 was restarted through its existing launcher.
