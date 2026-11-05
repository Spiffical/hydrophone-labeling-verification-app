(function () {
    if (window.__dashQueueWatchdogReady) return;
    window.__dashQueueWatchdogReady = true;

    // This app's callbacks form loops, which Dash breaks only on a queue pass that finds
    // nothing else pending, and a pass never re-runs for its own changes. So when the last
    // pass merges duplicate requests, the queue stops with everything waiting and nothing
    // running: the page sits on "Preparing page". Slow links make this likely. Counting one
    // more completed callback is the smallest change that makes Dash look at the queue again.
    const CHECK_MS = 1000;
    const BUSY_LISTS = ['prioritized', 'blocked', 'executing', 'watched', 'executed'];
    let waiting = null;

    setInterval(function () {
        const store = window.dash_stores && window.dash_stores[0];
        const queue = store && store.getState().callbacks;
        if (!queue) return;
        const stalled = queue.requested.length > 0
            && BUSY_LISTS.every(function (name) { return queue[name].length === 0; });
        // The same waiting list a whole check later: Dash acts on a change at once.
        if (stalled && queue.requested === waiting) {
            store.dispatch({ type: 'Callbacks.Completed', payload: 1 });
        }
        waiting = stalled ? queue.requested : null;
    }, CHECK_MS);
}());
