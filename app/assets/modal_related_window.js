// The view-only window for a similar clip (modal-related-viewer, evidence_figure_callbacks.py)
// floats beside the review window. Drag it by its title bar; it keeps that place while the
// page stays open, also when it is closed and opened again. Buttons and links in the title
// bar still work as usual.
//
// Opening a clip takes a server round trip, and its spectrogram is drawn on the server the
// first time it is shown, which can take a while. So the pressed button spins until the window
// shows that clip, and the window shows "Drawing spectrogram" (zz_workbench.css) instead of the
// previous clip's image until the new one has loaded.
(function () {
    'use strict';
    let offset = { x: 0, y: 0 };
    let drag = null;

    function place(dialog) {
        if (!dialog) return;
        dialog.style.transform = (offset.x || offset.y) ? `translate(${offset.x}px, ${offset.y}px)` : '';
    }

    function keepOnScreen(dialog) {
        // Keep enough of the title bar on screen to grab it again.
        const rect = dialog.getBoundingClientRect();
        const minVisible = 80;
        let dx = 0;
        let dy = 0;
        if (rect.top < 0) dy = -rect.top;
        if (rect.top > window.innerHeight - 40) dy = window.innerHeight - 40 - rect.top;
        if (rect.right < minVisible) dx = minVisible - rect.right;
        if (rect.left > window.innerWidth - minVisible) dx = window.innerWidth - minVisible - rect.left;
        if (dx || dy) {
            offset = { x: offset.x + dx, y: offset.y + dy };
            place(dialog);
        }
    }

    document.addEventListener('mousedown', (event) => {
        if (event.button !== 0 || !event.target.closest) return;
        const header = event.target.closest('.modal-related-dialog .modal-header');
        if (!header || event.target.closest('button, a, input, select, textarea')) return;
        drag = {
            dialog: header.closest('.modal-related-dialog'),
            x: event.clientX - offset.x,
            y: event.clientY - offset.y,
        };
        event.preventDefault();
    });

    document.addEventListener('mousemove', (event) => {
        if (!drag) return;
        offset = { x: event.clientX - drag.x, y: event.clientY - drag.y };
        place(drag.dialog);
    });

    document.addEventListener('mouseup', () => {
        if (!drag) return;
        keepOnScreen(drag.dialog);
        drag = null;
    });

    function shownTitle() {
        const title = document.getElementById('modal-related-title');
        return title && document.querySelector('.modal-related-window') ? title.textContent.trim() : '';
    }

    function hideUntilLoaded(image) {
        // A reused <img> keeps showing the last clip until the new source arrives.
        if (!image || (image.complete && image.naturalWidth > 0)) return;
        image.classList.add('is-loading');
        const reveal = () => image.classList.remove('is-loading');
        image.addEventListener('load', reveal, { once: true });
        image.addEventListener('error', reveal, { once: true });
    }

    document.addEventListener('click', (event) => {
        const button = event.target.closest && event.target.closest('.modal-evidence-related-button');
        if (!button) return;
        const label = button.textContent.trim();
        button.classList.add('is-loading');
        button.setAttribute('aria-busy', 'true');
        const started = Date.now();
        let shownAt = null;
        const timer = setInterval(() => {
            // The window is mounted again each time it opens: put it back where it was left.
            place(document.querySelector('.modal-related-dialog'));
            if (shownAt === null && shownTitle() === label) {
                shownAt = Date.now();
                button.classList.remove('is-loading');
                button.removeAttribute('aria-busy');
                hideUntilLoaded(document.querySelector('.modal-related-image'));
            }
            const waited = Date.now() - started;
            if (shownAt === null && waited > 60000) {
                button.classList.remove('is-loading');
                button.removeAttribute('aria-busy');
            }
            if ((shownAt !== null && Date.now() - shownAt > 1500) || waited > 60000) clearInterval(timer);
        }, 100);
    });
})();
