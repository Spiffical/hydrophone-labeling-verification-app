# Per-reviewer filter preferences: local verification

Implemented and verified locally on 2026-09-16; not deployed.

Preferences are stored in browser local storage, keyed by normalized reviewer
email. Date and device are remembered per mode; review status, selected classes,
and confidence thresholds are restored when the reviewer profile loads or changes.
This does not synchronize preferences across browsers or computers.

## Browser checks

Used a disposable local dashboard on port 18059 with two dates, two devices, two
classes, and eight recordings. No live annotations were changed.

- Reviewer Alice selected September 3, Hydrophone-B, unverified status, Sonar only,
  and 52% confidence. All five settings and the matching clip survived reload.
- A new reviewer Bob started with independent defaults.
- Bob selected All Dates, All Devices, 0% confidence, and no classes. These values
  survived reload and closing/reopening the dashboard in a new tab.
- Switching back to Alice restored her original five settings and matching clip.

Testing exposed and fixed two initialization issues: an empty device option list
could erase a restored selection, and a loaded date/device subset could hide the
rest of the dataset from discovery.

## Automated checks

- `node --test tests/*.test.cjs`: 20 passed.
- `.venv/bin/python -m pytest -q`: 238 passed, 4 skipped.
- `git diff --check`: clean.

New regression coverage checks profile isolation, hydration guards, simultaneous
date/device updates, invalid persisted values, empty class selections, 0%
thresholds, full dataset discovery, and unavailable-selection fallback.
