(function () {
    const modes = ['label', 'verify', 'explore'];
    const statuses = ['all', 'unverified', 'accepted_only', 'rejected_only', 'mixed',
        'contains_accepted', 'contains_rejected', 'verified'];
    const object = value => value && typeof value === 'object' && !Array.isArray(value);
    const copy = value => JSON.parse(JSON.stringify(value));
    function reviewerKey(profile) {
        return String((profile || {}).email || '').trim().toLowerCase() || '__local__';
    }
    function normalize(value) {
        const saved = object(value) ? value : {};
        const tabs = {};
        modes.forEach(mode => {
            const tab = object(saved.tabs) && object(saved.tabs[mode]) ? saved.tabs[mode] : {};
            tabs[mode] = {};
            ['date', 'device'].forEach(field => {
                tabs[mode][field] = typeof tab[field] === 'string' && tab[field] ? tab[field] : null;
            });
        });
        const thresholds = { __global__: .5 };
        if (object(saved.thresholds)) {
            Object.entries(saved.thresholds).forEach(([key, value]) => {
                if (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1) {
                    thresholds[key] = value;
                }
            });
        }
        return { tabs, thresholds,
            status: statuses.includes(saved.status) ? saved.status : 'all',
            // null means all classes, while [] intentionally means no classes.
            classes: Array.isArray(saved.classes)
                ? [...new Set(saved.classes.filter(value => typeof value === 'string' && value.trim()))] : null,
        };
    }
    window.dash_clientside = Object.assign({}, window.dash_clientside, {
        reviewPreferences: {
            persistTabs: function (date, device, mode, tabs, profile, owner, dateOptions, deviceOptions) {
                const dc = window.dash_clientside;
                if (owner !== reviewerKey(profile) || !modes.includes(mode)) return dc.no_update;
                const next = normalize({ tabs }).tabs;
                const changed = (dc.callback_context.triggered || []).map(t => t.prop_id.split('.')[0]);
                if (changed.includes('global-date-selector') && dateOptions && dateOptions.length) next[mode].date = date || null;
                if (changed.includes('global-device-selector') && deviceOptions && deviceOptions.length) next[mode].device = device || null;
                return JSON.stringify(next) === JSON.stringify(tabs) ? dc.no_update : next;
            },
            restore: function (profile, preferences) {
                const key = reviewerKey(profile);
                const saved = normalize(object(preferences) && Object.hasOwn(preferences, key) ? preferences[key] : null);
                return [saved.tabs, saved.thresholds, saved.classes, saved.status,
                    saved.thresholds.__global__, key];
            },
            remember: function (tabs, thresholds, classes, status, profile, owner, preferences) {
                const dc = window.dash_clientside;
                const key = reviewerKey(profile);
                // Do not let pre-hydration defaults or another profile's state overwrite saved settings.
                if (owner !== key) return dc.no_update;
                const saved = normalize({ tabs, thresholds, classes, status });
                const previous = object(preferences) ? preferences : {};
                if (Object.hasOwn(previous, key) && JSON.stringify(previous[key]) === JSON.stringify(saved)) {
                    return dc.no_update;
                }
                return Object.assign({}, copy(previous), { [key]: saved });
            },
        },
    });
})();
