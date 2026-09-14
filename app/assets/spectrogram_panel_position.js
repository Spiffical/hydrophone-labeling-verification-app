/* Keep compact spectrogram settings inside the viewport, including on resize. */
(function () {
    "use strict";
    const selector = "details.display-range-bar--compact[open] > .display-range-content";
    let pending = false;

    function positionPanels() {
        pending = false;
        const viewport = window.visualViewport;
        const margin = 12;
        const leftEdge = (viewport ? viewport.offsetLeft : 0) + margin;
        const topEdge = (viewport ? viewport.offsetTop : 0) + margin;
        const width = viewport ? viewport.width : document.documentElement.clientWidth;
        const height = viewport ? viewport.height : window.innerHeight;
        document.querySelectorAll(selector).forEach(function (panel) {
            const summary = panel.parentElement.querySelector("summary");
            if (!summary) return;
            const anchor = summary.getBoundingClientRect();
            const panelWidth = Math.max(0, Math.min(760, width - 2 * margin));
            const left = Math.max(leftEdge, Math.min(anchor.left, leftEdge + width - 2 * margin - panelWidth));
            // Leave usable scrolling space even when the toolbar wraps on a short screen.
            const top = Math.max(topEdge, Math.min(anchor.bottom + 9, topEdge + height / 2));
            Object.assign(panel.style, {
                position: "absolute",
                boxSizing: "border-box",
                width: panelWidth + "px",
                right: "auto",
                left: "0px",
                top: "0px",
                maxHeight: Math.max(0, topEdge + height - 2 * margin - top) + "px",
                overflowX: "hidden",
                overflowY: "auto"
            });
            // Measure the actual containing block: the toolbar's backdrop filter can
            // also contain fixed descendants, so viewport coordinates alone are unsafe.
            const origin = panel.getBoundingClientRect();
            panel.style.left = (left - origin.left) + "px";
            panel.style.top = (top - origin.top) + "px";
        });
    }

    function schedule() {
        if (pending || !document.querySelector(selector)) return;
        pending = true;
        window.requestAnimationFrame(positionPanels);
    }

    document.addEventListener("toggle", schedule, true);
    window.addEventListener("resize", schedule);
    // Ignore scrolling within the panel; only its anchor moving needs repositioning.
    document.addEventListener("scroll", function (event) {
        if (event.target instanceof Element && event.target.closest(selector)) return;
        schedule();
    }, true);
    if (window.visualViewport) {
        window.visualViewport.addEventListener("resize", schedule);
        window.visualViewport.addEventListener("scroll", schedule);
    }
    schedule();
}());
