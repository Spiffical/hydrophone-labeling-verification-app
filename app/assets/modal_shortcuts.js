(function () {
    'use strict';

    function visible(element) {
        return !!element && element.getClientRects().length > 0 &&
            window.getComputedStyle(element).visibility !== 'hidden';
    }

    document.addEventListener('keydown', function (event) {
        if (event.defaultPrevented || event.repeat || event.isComposing ||
            event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
        const modal = document.getElementById('image-modal');
        if (!visible(modal)) return;
        // A label editor, confirmation, or other dialog owns the keyboard until closed.
        if (Array.from(document.querySelectorAll('.modal')).some(function (dialog) {
            return dialog !== modal && !dialog.contains(modal) && visible(dialog);
        })) return;
        if (visible(document.getElementById('modal-busy-overlay'))) return;
        const target = event.target;
        if (target && (target.isContentEditable || target.closest(
            'input, textarea, select, [role="slider"], [role="spinbutton"], [role="combobox"], [contenteditable="true"]'
        ))) return;

        const ids = { ArrowLeft: 'modal-nav-prev', ArrowRight: 'modal-nav-next' };
        const button = event.key.toLowerCase() === 'e'
            ? modal.querySelector('button[id*="modal-action-edit"]')
            : document.getElementById(ids[event.key]);
        if (!visible(button) || button.disabled || button.getAttribute('aria-disabled') === 'true') return;
        event.preventDefault();
        // Use the existing click path, including unsaved-change and navigation guards.
        button.click();
    });
}());
