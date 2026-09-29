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

        if (/^[0-9]$/.test(event.key)) {
            // 1-9 choose the tag for new boxes, 0 clears it (bbox_list.js).
            const boxPanel = window.bboxPanel;
            if (boxPanel && boxPanel.handleTagKey(event.key)) event.preventDefault();
            return;
        }

        const pageSteps = { '[': -1, ']': 1, PageUp: -1, PageDown: 1 };
        if (pageSteps[event.key]) {
            // Pages of a long clip (modal_paging.js).
            const paging = window.modalPaging;
            if (paging && paging.step(pageSteps[event.key])) event.preventDefault();
            return;
        }

        if (event.key === 'Escape' || event.key.toLowerCase() === 'b') {
            // B toggles draw mode and Esc stops it (bbox_draw_mode.js).
            const draw = window.bboxDrawMode;
            if (!draw || (event.key === 'Escape' && !draw.isOn())) return;
            if (event.key === 'Escape') draw.disable(); else draw.toggle();
            event.preventDefault();
            return;
        }

        if (event.key === 'Enter') {
            // A focused button or link keeps Enter for itself.
            if (target && target.closest && target.closest('button, a, summary, [role="button"]')) return;
            const workbench = window.modalWorkbench;
            if (!workbench) return;
            event.preventDefault();
            workbench.saveAndNext();
            return;
        }

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
