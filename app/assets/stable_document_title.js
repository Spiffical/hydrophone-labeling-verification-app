(function () {
    "use strict";

    var title = "Hydrophone Acoustic Review Suite";

    function enforceTitle() {
        if (document.title !== title) {
            document.title = title;
        }
    }

    function observeTitle() {
        enforceTitle();
        if (!document.head) {
            return;
        }
        new MutationObserver(enforceTitle).observe(document.head, {
            childList: true,
            subtree: true,
            characterData: true,
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", observeTitle, {once: true});
    } else {
        observeTitle();
    }
    window.addEventListener("pageshow", enforceTitle);
})();
