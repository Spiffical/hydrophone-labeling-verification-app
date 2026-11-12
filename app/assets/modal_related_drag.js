// The view-only window for a similar clip (modal-related-viewer, evidence_figure_callbacks.py)
// floats beside the review window. Drag it by its title bar; it keeps that place while the
// page stays open, also when it is closed and opened again. Buttons and links in the title
// bar still work as usual.
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

    // The window is mounted again each time a similar-clip button opens it: put it
    // back where it was left once it appears (and keep it there while it renders).
    document.addEventListener('click', (event) => {
        if (!event.target.closest || !event.target.closest('.modal-evidence-related-button')) return;
        let tries = 0;
        const timer = setInterval(() => {
            place(document.querySelector('.modal-related-dialog'));
            tries += 1;
            if (tries >= 40) clearInterval(timer);
        }, 100);
    });
})();
