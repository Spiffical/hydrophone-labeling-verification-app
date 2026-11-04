(function () {
    if (window.__reviewCardKeysReady) return;
    window.__reviewCardKeysReady = true;

    // Review cards are divs that open on click, so give them a button's keys.
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        const card = event.target;
        if (!card.classList || !card.classList.contains('review-card')) return;
        // Enter means "save and next" while a clip is open.
        if (document.querySelector('.modal.show')) return;
        event.preventDefault();
        card.click();
    });
}());
