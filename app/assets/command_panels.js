(function () {
    if (window.__commandPanelExclusivityReady) return;
    window.__commandPanelExclusivityReady = true;

    document.addEventListener("click", function (event) {
        var closeButton = event.target.closest("[data-command-panel-close]");
        if (closeButton) {
            var panelToClose = closeButton.closest("details[data-command-panel]");
            if (panelToClose) panelToClose.open = false;
            event.preventDefault();
            event.stopPropagation();
            return;
        }

        var clickedPanel = event.target.closest("details[data-command-panel]");
        if (!clickedPanel) {
            document.querySelectorAll("details[data-command-panel][open]").forEach(function (panel) {
                panel.open = false;
            });
            return;
        }

        var summary = event.target.closest("summary");
        if (!summary || summary.parentElement !== clickedPanel) return;

        if (clickedPanel.open) return;

        document.querySelectorAll("details[data-command-panel][open]").forEach(function (candidate) {
            if (candidate !== clickedPanel) candidate.open = false;
        });
    }, true);
}());
