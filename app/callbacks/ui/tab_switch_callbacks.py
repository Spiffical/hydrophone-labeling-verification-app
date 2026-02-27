"""Tab mode switching callbacks."""

from dash import Input, Output


def register_mode_tab_callbacks(app):
    """Register callbacks that synchronize tab buttons and active mode store."""

    app.clientside_callback(
        """
        function(labelClicks, verifyClicks, exploreClicks) {
            var dc = (window.dash_clientside || {});
            var ctx = dc.callback_context || null;
            if (ctx && ctx.triggered && ctx.triggered.length > 0) {
                var id = ctx.triggered[0].prop_id.split('.')[0];
                if (id === 'tab-btn-label') return 'label';
                if (id === 'tab-btn-verify') return 'verify';
                if (id === 'tab-btn-explore') return 'explore';
                return dc.no_update;
            }
            var lc = labelClicks || 0;
            var vc = verifyClicks || 0;
            var ec = exploreClicks || 0;
            var max = Math.max(lc, vc, ec);
            if (max === 0) return dc.no_update;
            if (max === lc) return 'label';
            if (max === vc) return 'verify';
            return 'explore';
        }
        """,
        Output("mode-tabs", "data"),
        [Input("tab-btn-label", "n_clicks"),
         Input("tab-btn-verify", "n_clicks"),
         Input("tab-btn-explore", "n_clicks")],
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(mode) {
            var labelStyle = {display: mode === 'label' ? 'block' : 'none'};
            var verifyStyle = {display: mode === 'verify' ? 'block' : 'none'};
            var exploreStyle = {display: mode === 'explore' ? 'block' : 'none'};
            var labelClass = 'mode-tab' + (mode === 'label' ? ' mode-tab--active' : '');
            var verifyClass = 'mode-tab' + (mode === 'verify' ? ' mode-tab--active' : '');
            var exploreClass = 'mode-tab' + (mode === 'explore' ? ' mode-tab--active' : '');
            return [labelStyle, verifyStyle, exploreStyle, labelClass, verifyClass, exploreClass];
        }
        """,
        [Output("label-tab-content", "style"),
         Output("verify-tab-content", "style"),
         Output("explore-tab-content", "style"),
         Output("tab-btn-label", "className"),
         Output("tab-btn-verify", "className"),
         Output("tab-btn-explore", "className")],
        Input("mode-tabs", "data"),
        prevent_initial_call=True,
    )
