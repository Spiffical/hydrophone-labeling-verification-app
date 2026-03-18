// Audio player control functions
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.namespace = Object.assign({}, window.dash_clientside.namespace, {
    // Initialize audio players when page loads
    initializeAudioPlayers: function () {
        // Optimized initialization - minimal logging, fast DOM queries
        cleanupDetachedAudioPlayers();
        const audioElements = document.querySelectorAll('audio[id$="-audio"]');

        audioElements.forEach(function (audio) {
            const playerId = audio.id.replace('-audio', '');
            const playerEntry = ensureAudioPlayerEntry(playerId, audio);
            const cleanupFns = playerEntry.cleanupFns;
            const playBtn = document.getElementById(playerId + '-play-btn');
            const playIcon = document.getElementById(playerId + '-play-icon');
            const timeSlider = document.getElementById(playerId + '-time-slider');
            const currentTimeEl = document.getElementById(playerId + '-current-time');
            const durationEl = document.getElementById(playerId + '-duration');
            const pitchSlider = document.getElementById(playerId + '-pitch-slider');
            const pitchDisplay = document.getElementById(playerId + '-pitch-display');
            const eqDisplay = document.getElementById(playerId + '-eq-display');
            const gainSlider = document.getElementById(playerId + '-gain-slider');
            const gainDisplay = document.getElementById(playerId + '-gain-display');
            const lowEqBands = [
                { key: 'eq-20', frequency: 20, slider: document.getElementById(playerId + '-eq-20-slider') },
                { key: 'eq-40', frequency: 40, slider: document.getElementById(playerId + '-eq-40-slider') },
                { key: 'eq-80', frequency: 80, slider: document.getElementById(playerId + '-eq-80-slider') },
                { key: 'eq-160', frequency: 160, slider: document.getElementById(playerId + '-eq-160-slider') },
                { key: 'eq-315', frequency: 315, slider: document.getElementById(playerId + '-eq-315-slider') },
                { key: 'eq-630', frequency: 630, slider: document.getElementById(playerId + '-eq-630-slider') },
                { key: 'eq-1250', frequency: 1250, slider: document.getElementById(playerId + '-eq-1250-slider') },
                { key: 'eq-2500', frequency: 2500, slider: document.getElementById(playerId + '-eq-2500-slider') },
                { key: 'eq-5000', frequency: 5000, slider: document.getElementById(playerId + '-eq-5000-slider') },
                { key: 'eq-10000', frequency: 10000, slider: document.getElementById(playerId + '-eq-10000-slider') },
                { key: 'eq-16000', frequency: 16000, slider: document.getElementById(playerId + '-eq-16000-slider') },
            ];
            const hasLowEqSliders = lowEqBands.some(function (band) { return !!band.slider; });

            if (!audio.hasEventListeners) {
                audio.hasEventListeners = true;

                const formatClock = function (totalSeconds) {
                    if (!isFinite(totalSeconds) || totalSeconds < 0) return '0:00';
                    const minutes = Math.floor(totalSeconds / 60);
                    const seconds = Math.floor(totalSeconds % 60);
                    return minutes + ':' + (seconds < 10 ? '0' : '') + seconds;
                };

                const updateDurationLabel = function () {
                    if (!durationEl) return;
                    if (!isFinite(audio.duration) || audio.duration <= 0) return;
                    durationEl.textContent = formatClock(audio.duration);
                };

                // Update duration when metadata is loaded
                audio.addEventListener('loadedmetadata', function () {
                    updateDurationLabel();
                });

                // Some browsers update duration after metadata; keep label in sync.
                audio.addEventListener('durationchange', function () {
                    updateDurationLabel();
                });

                // Update time and slider during playback
                audio.addEventListener('timeupdate', function () {
                    if (currentTimeEl) {
                        currentTimeEl.textContent = formatClock(audio.currentTime || 0);
                    }
                    updateDurationLabel();

                    // Only update slider if user is not interacting with it
                    if (
                        timeSlider &&
                        !timeSlider.isUserInteracting &&
                        !audio.isSliderSeeking &&
                        isFinite(audio.duration) &&
                        audio.duration > 0
                    ) {
                        const progress = (audio.currentTime / audio.duration) * 100;
                        updateSliderPositionSafely(timeSlider, progress);
                    }

                    // Update playback position marker on spectrogram if in modal
                    if (playerId.startsWith('modal-') && isFinite(audio.duration) && audio.duration > 0) {
                        updateSpectrogramPlaybackMarker(audio.currentTime, audio.duration);
                    }
                });

                // Reset play button when audio ends
                audio.addEventListener('ended', function () {
                    if (playIcon) {
                        playIcon.className = 'fas fa-play';
                    }
                });

                // Handle play/pause events
                audio.addEventListener('play', function () {
                    if (playIcon) {
                        playIcon.className = 'fas fa-pause';
                    }
                });

                audio.addEventListener('pause', function () {
                    if (playIcon) {
                        playIcon.className = 'fas fa-play';
                    }
                });

                // Handle seeking
                audio.addEventListener('seeking', function () {
                    audio.isSliderSeeking = true;
                });

                audio.addEventListener('seeked', function () {
                    audio.isSliderSeeking = false;
                });

                // Metadata can already be available when listeners are attached.
                updateDurationLabel();
                setTimeout(updateDurationLabel, 120);
            }

            const preloadMode = String(
                audio.getAttribute('data-audio-preload-mode') || audio.getAttribute('preload') || ''
            ).toLowerCase();
            if (preloadMode === 'auto') {
                ensureAudioSourceLoaded(audio, true);
            }

            // Set up Web Audio API only for modal players that expose tone controls.
            if (!audio.audioContext && (pitchSlider || hasLowEqSliders || gainSlider)) {
                try {
                    const AudioContext = window.AudioContext || window.webkitAudioContext;
                    audio.audioContext = new AudioContext();
                    audio.sourceNode = audio.audioContext.createMediaElementSource(audio);

                    // Create full-range EQ filters with logarithmic band spacing.
                    audio.lowEqFilters = {};
                    let chainTail = audio.sourceNode;
                    lowEqBands.forEach(function (band) {
                        const filter = audio.audioContext.createBiquadFilter();
                        filter.type = 'peaking';
                        filter.frequency.value = band.frequency;
                        filter.Q.value = 1.05;
                        filter.gain.value = 0;
                        chainTail.connect(filter);
                        chainTail = filter;
                        audio.lowEqFilters[band.key] = filter;
                    });

                    // Create gain node for post-EQ amplification.
                    audio.gainNode = audio.audioContext.createGain();
                    audio.gainNode.gain.value = 1.0;

                    // Connect: source -> low EQ chain -> gain -> destination
                    chainTail.connect(audio.gainNode);
                    audio.gainNode.connect(audio.audioContext.destination);

                    registerPlayerCleanup(cleanupFns, function () {
                        try {
                            if (!audio.paused) {
                                audio.pause();
                            }
                        } catch (pauseError) {
                            console.debug('Error pausing audio during cleanup:', pauseError);
                        }
                        try {
                            if (audio.sourceNode) {
                                audio.sourceNode.disconnect();
                            }
                        } catch (disconnectError) {
                            console.debug('Error disconnecting audio source:', disconnectError);
                        }
                        try {
                            if (audio.gainNode) {
                                audio.gainNode.disconnect();
                            }
                        } catch (disconnectError) {
                            console.debug('Error disconnecting gain node:', disconnectError);
                        }
                        try {
                            if (audio.lowEqFilters) {
                                Object.keys(audio.lowEqFilters).forEach(function (key) {
                                    const filter = audio.lowEqFilters[key];
                                    if (filter && typeof filter.disconnect === 'function') {
                                        filter.disconnect();
                                    }
                                });
                            }
                        } catch (disconnectError) {
                            console.debug('Error disconnecting EQ filters:', disconnectError);
                        }
                        try {
                            if (audio.audioContext && audio.audioContext.state !== 'closed') {
                                audio.audioContext.close().catch(function () { });
                            }
                        } catch (closeError) {
                            console.debug('Error closing audio context:', closeError);
                        }
                        audio.audioContext = null;
                        audio.sourceNode = null;
                        audio.gainNode = null;
                        audio.lowEqFilters = null;
                    });

                    console.log('Web Audio API initialized for:', playerId);
                } catch (e) {
                    console.warn('Web Audio API not available:', e);
                }
            }

            if (pitchSlider) {
                bindSliderValueSync(pitchSlider, 0.1, 4.0, function (rate) {
                    audio.playbackRate = rate;
                    if (pitchDisplay) {
                        pitchDisplay.textContent = rate.toFixed(2) + 'x';
                    }
                }, cleanupFns);
            }

            const getSliderRoundedDb = function (slider) {
                if (!slider) return 0;
                const current = readSliderValue(slider, -24, 24);
                if (current === null) return 0;
                return Math.round(current);
            };

            const applyEqBandGain = function (band, dbGain) {
                if (!audio.lowEqFilters || !audio.lowEqFilters[band.key]) return;
                audio.lowEqFilters[band.key].gain.value = dbGain;
            };

            const refreshEqFilterGains = function () {
                lowEqBands.forEach(function (band) {
                    if (!band.slider) return;
                    const roundedGain = getSliderRoundedDb(band.slider);
                    applyEqBandGain(band, roundedGain);
                });
            };

            const updateLowEqDisplay = function () {
                if (!eqDisplay) return;
                eqDisplay.textContent = 'Full-range EQ: 20 Hz to 16 kHz';
            };

            lowEqBands.forEach(function (band) {
                if (!band.slider) return;
                bindSliderValueSync(band.slider, -24, 24, function (dbGain) {
                    const roundedGain = Math.round(dbGain);
                    applyEqBandGain(band, roundedGain);
                    updateLowEqDisplay();
                }, cleanupFns);
            });

            refreshEqFilterGains();
            updateLowEqDisplay();

            if (gainSlider) {
                bindSliderValueSync(gainSlider, 1, 50, function (amplification) {
                    const normalized = Math.round(amplification * 10) / 10;
                    if (audio.gainNode) {
                        audio.gainNode.gain.value = normalized;
                    } else {
                        // Fallback when Web Audio API is not available.
                        audio.volume = clamp(normalized, 0, 1);
                    }
                    if (gainDisplay) {
                        gainDisplay.textContent = normalized.toFixed(1) + 'x';
                    }
                }, cleanupFns);
            }

            // Play/pause button click handler
            if (playBtn && !playBtn.hasClickHandler) {
                playBtn.hasClickHandler = true;
                playBtn.addEventListener('click', function (e) {
                    e.preventDefault();
                    e.stopPropagation();

                    if (audio.paused) {
                        ensureAudioSourceLoaded(audio, true);
                        if (audio.audioContext && audio.audioContext.state === 'suspended') {
                            audio.audioContext.resume().catch(function () { });
                        }
                        // Always restart from the beginning if playback is at (or past) the end.
                        const hasFiniteDuration = isFinite(audio.duration) && audio.duration > 0;
                        const atEnd = hasFiniteDuration && audio.currentTime >= (audio.duration - 0.05);
                        if (audio.ended || atEnd) {
                            audio.currentTime = 0;
                            if (timeSlider) {
                                updateSliderPositionSafely(timeSlider, 0);
                            }
                        }

                        // Pause all other audio players first
                        audioElements.forEach(function (otherAudio) {
                            if (otherAudio !== audio && !otherAudio.paused) {
                                otherAudio.pause();
                            }
                        });

                        // Play this audio
                        audio.play().catch(function (error) {
                            console.error('Error playing audio:', playerId, error);
                        });
                    } else {
                        audio.pause();
                    }
                });
            }

            // Set up slider event listeners with better handling
            if (timeSlider && !timeSlider.hasSliderListeners) {
                timeSlider.hasSliderListeners = true;
                if (playerId.startsWith('modal-')) {
                    setupSliderInteraction(timeSlider, audio, cleanupFns);
                } else {
                    attachSliderValueSeekSync(timeSlider, audio, cleanupFns);
                }
            }

            // Keep audio currentTime synchronized with timeline slider value.
            // We removed the bindSliderValueSync loop here because we manually set 
            // audio.currentTime during the handleSliderSeek() call.
            // bindSliderValueSync was fighting the native user drag, causing jumping.
        });

        return '';
    }
});

function getAudioControlState() {
    if (!window.__hydroAudioControlState) {
        window.__hydroAudioControlState = {
            players: new Map(),
            reinitTimer: null,
            rootObserver: null,
        };
    }
    return window.__hydroAudioControlState;
}

function registerPlayerCleanup(cleanupFns, cleanupFn) {
    if (!Array.isArray(cleanupFns) || typeof cleanupFn !== 'function') return;
    cleanupFns.push(cleanupFn);
}

function addTrackedEventListener(target, eventName, handler, options, cleanupFns) {
    if (!target || typeof target.addEventListener !== 'function' || typeof handler !== 'function') return;
    target.addEventListener(eventName, handler, options);
    registerPlayerCleanup(cleanupFns, function () {
        if (target && typeof target.removeEventListener === 'function') {
            target.removeEventListener(eventName, handler, options);
        }
    });
}

function ensureAudioPlayerEntry(playerId, audio) {
    const state = getAudioControlState();
    const existing = state.players.get(playerId);
    if (existing && existing.audio !== audio) {
        cleanupAudioPlayer(playerId);
    }
    if (!state.players.has(playerId)) {
        state.players.set(playerId, {
            audio: audio,
            cleanupFns: [],
        });
    }
    const entry = state.players.get(playerId);
    entry.audio = audio;
    return entry;
}

function cleanupAudioPlayer(playerId) {
    const state = getAudioControlState();
    const entry = state.players.get(playerId);
    if (!entry) return;
    state.players.delete(playerId);
    const cleanupFns = Array.isArray(entry.cleanupFns) ? entry.cleanupFns.slice().reverse() : [];
    cleanupFns.forEach(function (cleanupFn) {
        try {
            cleanupFn();
        } catch (e) {
            console.debug('Error cleaning up audio player:', playerId, e);
        }
    });
}

function cleanupDetachedAudioPlayers() {
    const state = getAudioControlState();
    Array.from(state.players.entries()).forEach(function (entryTuple) {
        const playerId = entryTuple[0];
        const entry = entryTuple[1];
        if (!entry || !entry.audio || !entry.audio.isConnected) {
            cleanupAudioPlayer(playerId);
        }
    });
}

function scheduleAudioPlayerInitialization(delayMs) {
    const state = getAudioControlState();
    if (state.reinitTimer) {
        clearTimeout(state.reinitTimer);
    }
    state.reinitTimer = setTimeout(function () {
        state.reinitTimer = null;
        if (window.dash_clientside && window.dash_clientside.namespace) {
            window.dash_clientside.namespace.initializeAudioPlayers();
        }
    }, delayMs);
}

function trackMutationObserver(observer, target, options, cleanupFns) {
    if (!observer || !target || typeof observer.observe !== 'function') return;
    observer.observe(target, options);
    registerPlayerCleanup(cleanupFns, function () {
        try {
            observer.disconnect();
        } catch (e) {
            console.debug('Error disconnecting mutation observer:', e);
        }
    });
}

function ensureAudioSourceLoaded(audio, shouldLoad) {
    if (!audio) return false;
    const datasetSrc = audio.getAttribute('data-audio-src') || '';
    const currentSrc = audio.getAttribute('src') || '';
    if (!currentSrc && datasetSrc) {
        audio.setAttribute('src', datasetSrc);
    }
    if (shouldLoad && typeof audio.load === 'function' && (datasetSrc || currentSrc)) {
        audio.load();
    }
    return !!(audio.getAttribute('src') || audio.currentSrc);
}

// Helper function to safely update slider position (avoid conflicts)
function updateSliderPositionSafely(slider, progress) {
    try {
        // Only update if we're confident we won't interfere with user interaction
        if (slider.isUserInteracting) return;

        // Use requestAnimationFrame to ensure smooth updates
        requestAnimationFrame(() => {
            if (!slider.isUserInteracting) {
                setSliderVisualProgress(slider, progress);
            }
        });
    } catch (e) {
        console.warn('Error updating slider position:', e);
    }
}

function getSliderRoot(slider) {
    if (!slider) return null;
    return (
        slider.querySelector('.dash-slider-root') ||
        slider.querySelector('.dash-slider') ||
        slider.querySelector('.dash-slider-container') ||
        slider.querySelector('.rc-slider')
    );
}

function getSliderHandle(slider) {
    if (!slider) return null;
    return slider.querySelector('.dash-slider-thumb[role="slider"]') || slider.querySelector('.rc-slider-handle');
}

function setSliderVisualProgress(slider, progress) {
    const clamped = clamp(progress, 0, 100);

    const dashRoot = slider.querySelector('.dash-slider-root');
    if (dashRoot) {
        const dashRange = dashRoot.querySelector('.dash-slider-range');
        const dashThumb = dashRoot.querySelector('.dash-slider-thumb[role="slider"]');
        const dashThumbWrapper = dashThumb ? dashThumb.parentElement : null;
        const dashInput = slider.querySelector('.dash-range-slider-input');

        if (dashRange) {
            dashRange.style.left = '0%';
            dashRange.style.right = (100 - clamped) + '%';
        }

        if (dashThumbWrapper) {
            // Match Dash slider offset behavior: +8px at 0%, -8px at 100%.
            const pxOffset = (8 - (clamped * 0.16)).toFixed(3);
            dashThumbWrapper.style.left = `calc(${clamped}% + ${pxOffset}px)`;
        }

        if (dashThumb) {
            dashThumb.setAttribute('aria-valuenow', String(clamped));
        }

        if (dashInput && !Number.isNaN(clamped)) {
            dashInput.value = String(Math.round(clamped * 1000) / 1000);
        }

        return;
    }

    const rcRoot = slider.querySelector('.rc-slider');
    if (rcRoot) {
        const rcHandle = rcRoot.querySelector('.rc-slider-handle');
        const rcTrack = rcRoot.querySelector('.rc-slider-track');
        if (rcHandle && rcTrack) {
            rcHandle.style.left = clamped + '%';
            rcTrack.style.width = clamped + '%';
            rcHandle.setAttribute('aria-valuenow', String(clamped));
        }
    }
}

function getClientXFromEvent(e) {
    if (e && e.touches && e.touches.length > 0) return e.touches[0].clientX;
    if (e && e.changedTouches && e.changedTouches.length > 0) return e.changedTouches[0].clientX;
    if (e && typeof e.clientX === 'number') return e.clientX;
    return null;
}

// Improved slider interaction setup - better click/drag detection
function setupSliderInteraction(slider, audio, cleanupFns) {
    const sliderContainer = getSliderRoot(slider);
    if (!sliderContainer) return;

    let isActivelyDragging = false;
    let dragStarted = false;
    let mouseDownTime = 0;
    let resumeAfterSeek = false;
    let fallbackSeekActive = false;
    let fallbackResumeAfterSeek = false;
    let fallbackInteractionTimer = null;

    const clearFallbackTimer = function () {
        if (fallbackInteractionTimer) {
            clearTimeout(fallbackInteractionTimer);
            fallbackInteractionTimer = null;
        }
    };

    const beginFallbackSeek = function () {
        if (fallbackSeekActive) return;
        fallbackSeekActive = true;
        slider.isUserInteracting = true;
        fallbackResumeAfterSeek = !audio.paused && !audio.ended;
        if (fallbackResumeAfterSeek) {
            audio.pause();
        }
    };

    const endFallbackSeek = function () {
        clearFallbackTimer();
        if (!fallbackSeekActive) return;
        fallbackSeekActive = false;
        if (!isActivelyDragging) {
            slider.isUserInteracting = false;
        }
        if (fallbackResumeAfterSeek && audio.paused) {
            audio.play().catch(function (error) {
                console.error('Error resuming audio after fallback seek:', error);
            });
        }
        fallbackResumeAfterSeek = false;
    };

    const scheduleFallbackRelease = function () {
        clearFallbackTimer();
        fallbackInteractionTimer = setTimeout(function () {
            endFallbackSeek();
        }, 220);
    };

    const syncAudioTimeFromSliderValue = function () {
        if (!isFinite(audio.duration) || audio.duration <= 0) return;
        const progress = readSliderValue(slider, 0, 100);
        if (progress === null) return;
        const targetTime = (progress / 100) * audio.duration;
        const safeMax = Math.max(0, audio.duration - 0.01);
        const newTime = clamp(targetTime, 0, safeMax);
        if (!isFinite(newTime)) return;
        // Avoid excessive tiny writes that can trigger seek churn on some browsers.
        if (Math.abs((audio.currentTime || 0) - newTime) > 0.01) {
            audio.currentTime = newTime;
        }
        updateSliderPositionImmediately(slider, progress);
    };

    const beginInteraction = function (e) {
        if (isActivelyDragging) return;
        if (e && typeof e.button === 'number' && e.button !== 0) return;
        mouseDownTime = Date.now();
        dragStarted = false;
        isActivelyDragging = true;
        slider.isUserInteracting = true;
        endFallbackSeek();

        // Pause while scrubbing, then optionally resume on release.
        resumeAfterSeek = !audio.paused && !audio.ended;
        if (resumeAfterSeek) {
            audio.pause();
        }

        handleSliderSeek(e, sliderContainer, slider, audio);

        if (e && e.cancelable) {
            e.preventDefault();
        }
        if (e) {
            e.stopPropagation();
        }
    };

    const continueInteraction = function (e) {
        if (!isActivelyDragging) return;
        dragStarted = true;
        handleSliderSeek(e, sliderContainer, slider, audio);
        if (e && e.cancelable) {
            e.preventDefault();
        }
    };

    const endInteraction = function (e, clickThresholdMs) {
        if (!isActivelyDragging) return;

        const clickDuration = Date.now() - mouseDownTime;
        const shouldApplyFinalSeek = dragStarted || clickDuration < clickThresholdMs;
        if (shouldApplyFinalSeek) {
            handleSliderSeek(e, sliderContainer, slider, audio);
        }

        isActivelyDragging = false;
        dragStarted = false;
        slider.isUserInteracting = false;

        if (resumeAfterSeek && audio.paused) {
            audio.play().catch(function (error) {
                console.error('Error resuming audio after seek:', error);
            });
        }
        resumeAfterSeek = false;

        if (e && e.cancelable) {
            e.preventDefault();
        }
        if (e) {
            e.stopPropagation();
        }
    };

    const startInteraction = function (e) { beginInteraction(e); };
    const interactionTargets = [sliderContainer, slider].filter(Boolean);
    interactionTargets.forEach(function (target) {
        addTrackedEventListener(target, 'mousedown', startInteraction, undefined, cleanupFns);
        addTrackedEventListener(target, 'touchstart', startInteraction, { passive: false }, cleanupFns);
        addTrackedEventListener(target, 'pointerdown', startInteraction, undefined, cleanupFns);
    });

    // Handle mouse move while potentially dragging
    const onMouseMove = function (e) {
        continueInteraction(e);
    };
    addTrackedEventListener(document, 'mousemove', onMouseMove, undefined, cleanupFns);

    const onTouchMove = function (e) {
        continueInteraction(e);
    };
    addTrackedEventListener(document, 'touchmove', onTouchMove, { passive: false }, cleanupFns);

    const onPointerMove = function (e) {
        continueInteraction(e);
    };
    addTrackedEventListener(document, 'pointermove', onPointerMove, undefined, cleanupFns);

    // Handle mouse up (end of interaction)
    const onMouseUp = function (e) {
        endInteraction(e, 200);
        endFallbackSeek();
    };
    addTrackedEventListener(document, 'mouseup', onMouseUp, undefined, cleanupFns);

    const onTouchEnd = function (e) {
        endInteraction(e, 250);
        endFallbackSeek();
    };
    addTrackedEventListener(document, 'touchend', onTouchEnd, { passive: false }, cleanupFns);

    const onPointerUp = function (e) {
        endInteraction(e, 200);
        endFallbackSeek();
    };
    addTrackedEventListener(document, 'pointerup', onPointerUp, undefined, cleanupFns);

    const onPointerCancel = function () {
        endFallbackSeek();
    };
    addTrackedEventListener(document, 'pointercancel', onPointerCancel, undefined, cleanupFns);

    // Disable Dash's default click handling on the slider
    const suppressSliderClick = function (e) {
        e.preventDefault();
        e.stopPropagation();
    };
    addTrackedEventListener(sliderContainer, 'click', suppressSliderClick, undefined, cleanupFns);

    attachSliderValueSeekSync(
        slider,
        audio,
        cleanupFns,
        beginFallbackSeek,
        syncAudioTimeFromSliderValue,
        scheduleFallbackRelease,
        endFallbackSeek,
        clearFallbackTimer
    );
}

function attachSliderValueSeekSync(
    slider,
    audio,
    cleanupFns,
    beginFallbackSeek,
    syncAudioTimeFromSliderValue,
    scheduleFallbackRelease,
    endFallbackSeek,
    clearFallbackTimer
) {
    if (!slider || slider.hasFallbackSeekListeners) return;
    slider.hasFallbackSeekListeners = true;

    const startFallbackSeek = typeof beginFallbackSeek === 'function'
        ? beginFallbackSeek
        : function () {
            slider.isUserInteracting = true;
        };
    const syncAudioTime = typeof syncAudioTimeFromSliderValue === 'function'
        ? syncAudioTimeFromSliderValue
        : function () {
            if (!isFinite(audio.duration) || audio.duration <= 0) return;
            const progress = readSliderValue(slider, 0, 100);
            if (progress === null) return;
            const targetTime = (progress / 100) * audio.duration;
            const safeMax = Math.max(0, audio.duration - 0.01);
            const newTime = clamp(targetTime, 0, safeMax);
            if (!isFinite(newTime)) return;
            if (Math.abs((audio.currentTime || 0) - newTime) > 0.01) {
                audio.currentTime = newTime;
            }
            updateSliderPositionImmediately(slider, progress);
        };
    const scheduleFallbackEnd = typeof scheduleFallbackRelease === 'function'
        ? scheduleFallbackRelease
        : function () { };
    const finishFallbackSeek = typeof endFallbackSeek === 'function'
        ? endFallbackSeek
        : function () {
            slider.isUserInteracting = false;
        };
    const clearFallback = typeof clearFallbackTimer === 'function'
        ? clearFallbackTimer
        : function () { };

    const onInputLike = function () {
        startFallbackSeek();
        syncAudioTime();
        scheduleFallbackEnd();
    };
    addTrackedEventListener(slider, 'input', onInputLike, { passive: true }, cleanupFns);
    const onChange = function () {
        startFallbackSeek();
        syncAudioTime();
        finishFallbackSeek();
    };
    addTrackedEventListener(slider, 'change', onChange, { passive: true }, cleanupFns);
    const onKeyDown = function (e) {
        const key = e && e.key;
        if (!key) return;
        if (
            key === 'ArrowLeft' ||
            key === 'ArrowRight' ||
            key === 'Home' ||
            key === 'End' ||
            key === 'PageUp' ||
            key === 'PageDown'
        ) {
            startFallbackSeek();
            requestAnimationFrame(syncAudioTime);
            scheduleFallbackEnd();
        }
    };
    addTrackedEventListener(slider, 'keydown', onKeyDown, undefined, cleanupFns);
    const onKeyUp = function (e) {
        const key = e && e.key;
        if (!key) return;
        if (
            key === 'ArrowLeft' ||
            key === 'ArrowRight' ||
            key === 'Home' ||
            key === 'End' ||
            key === 'PageUp' ||
            key === 'PageDown'
        ) {
            requestAnimationFrame(syncAudioTime);
            finishFallbackSeek();
        }
    };
    addTrackedEventListener(slider, 'keyup', onKeyUp, undefined, cleanupFns);
    const onBlur = function () {
        finishFallbackSeek();
    };
    addTrackedEventListener(slider, 'blur', onBlur, undefined, cleanupFns);
    registerPlayerCleanup(cleanupFns, function () {
        clearFallback();
        slider.isUserInteracting = false;
        slider.hasFallbackSeekListeners = false;
    });
}

// Improved slider seeking function
function handleSliderSeek(e, sliderContainer, slider, audio) {
    if (!isFinite(audio.duration) || audio.duration <= 0) return;

    const rect = sliderContainer.getBoundingClientRect();
    const clientX = getClientXFromEvent(e);
    if (clientX === null) return;

    const x = clientX - rect.left;
    const width = rect.width;

    // Ensure we stay within bounds
    const clampedX = Math.max(0, Math.min(width, x));
    if (width <= 0) return;
    const progress = (clampedX / width) * 100;

    const targetTime = (progress / 100) * audio.duration;
    const safeMax = Math.max(0, audio.duration - 0.01);
    const newTime = clamp(targetTime, 0, safeMax);
    audio.currentTime = newTime;

    // Update the visual position immediately during manual interaction
    updateSliderPositionImmediately(slider, progress);
}

// Function to update slider position immediately (used during manual seeking)
function updateSliderPositionImmediately(slider, progress) {
    try {
        setSliderVisualProgress(slider, progress);
    } catch (e) {
        console.warn('Error updating slider position immediately:', e);
    }
}

function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}

function readSliderValue(slider, min, max) {
    if (!slider) return null;
    const handle = getSliderHandle(slider);
    if (!handle) return null;

    // Preferred source: aria-valuenow
    const aria = handle.getAttribute('aria-valuenow');
    let value = aria !== null ? parseFloat(aria) : NaN;

    // Dash/React variants may expose value text instead of numeric now
    if (isNaN(value)) {
        const ariaText = handle.getAttribute('aria-valuetext');
        value = ariaText !== null ? parseFloat(ariaText) : NaN;
    }

    // Fallback: handle left percentage
    if (isNaN(value)) {
        const pct = parseFloat(handle.style.left);
        if (!isNaN(pct)) {
            value = min + (pct / 100) * (max - min);
        }
    }

    if (isNaN(value)) return null;
    return clamp(value, min, max);
}

// Robust slider value sync for Dash 4 DOM changes:
// events + mutation observer + initial delayed sync.
function bindSliderValueSync(slider, min, max, applyValue, cleanupFns) {
    if (!slider || slider.hasValueSyncBinding) return;
    slider.hasValueSyncBinding = true;

    const syncNow = function () {
        const value = readSliderValue(slider, min, max);
        if (value !== null) {
            applyValue(value);
        }
    };

    const scheduleSync = function () {
        requestAnimationFrame(syncNow);
    };

    ['input', 'change', 'mousedown', 'mousemove', 'mouseup', 'click', 'touchstart', 'touchmove', 'touchend', 'keydown']
        .forEach(function (eventName) {
            addTrackedEventListener(slider, eventName, scheduleSync, { passive: true }, cleanupFns);
        });

    const observer = new MutationObserver(function () {
        scheduleSync();
    });
    trackMutationObserver(observer, slider, {
        attributes: true,
        childList: true,
        subtree: true,
        characterData: true
    }, cleanupFns);

    // Initial and delayed sync so first render and async hydration are covered.
    syncNow();
    setTimeout(syncNow, 100);
    setTimeout(syncNow, 350);

    // Polling fallback for environments where slider value updates bypass DOM events.
    // This keeps readouts (e.g., 1.00x / +12 dB) in sync with the actual handle value.
    if (!slider.valueSyncInterval) {
        slider.valueSyncInterval = setInterval(syncNow, 200);
        registerPlayerCleanup(cleanupFns, function () {
            if (slider.valueSyncInterval) {
                clearInterval(slider.valueSyncInterval);
                slider.valueSyncInterval = null;
            }
            slider.hasValueSyncBinding = false;
        });
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function () {
    console.log('DOM loaded, setting up audio controls...');

    // Initial setup with delay to ensure DOM is fully ready
    scheduleAudioPlayerInitialization(500);

    // Set up a mutation observer to handle dynamically added audio players
    const state = getAudioControlState();
    if (state.rootObserver) {
        state.rootObserver.disconnect();
    }

    const observer = new MutationObserver(function (mutations) {
        let shouldReinitialize = false;

        mutations.forEach(function (mutation) {
            if (mutation.type === 'childList') {
                if (mutation.removedNodes && mutation.removedNodes.length > 0) {
                    cleanupDetachedAudioPlayers();
                }
                mutation.addedNodes.forEach(function (node) {
                    if (node.nodeType === 1) { // Element node
                        const audioElements = node.querySelectorAll ? node.querySelectorAll('audio[id$="-audio"]') : [];
                        if (audioElements.length > 0 || (node.id && node.id.includes('audio-'))) {
                            shouldReinitialize = true;
                        }
                    }
                });
            }
        });

        if (shouldReinitialize) {
            scheduleAudioPlayerInitialization(100);
        }
    });

    state.rootObserver = observer;
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
});

// Function to update the playback position marker on the spectrogram
function updateSpectrogramPlaybackMarker(currentTime, duration) {
    try {
        const modalGraph = document.getElementById('modal-image-graph');
        if (!modalGraph) return;

        const graphDiv = modalGraph.querySelector('.js-plotly-plot');
        if (!graphDiv || !graphDiv.layout) return;

        if (!isFinite(currentTime) || currentTime < 0) return;

        const toFiniteNumber = function (value) {
            const n = Number(value);
            return isFinite(n) ? n : null;
        };

        // Resolve full x-domain (data coordinates), not the current zoom/pan range.
        // This keeps playback mapping stable even when the user zooms the graph.
        let domainStart = null;
        let domainEnd = null;
        const firstTrace = graphDiv.data && graphDiv.data.length ? graphDiv.data[0] : null;
        const xVals = firstTrace && Array.isArray(firstTrace.x) ? firstTrace.x : null;
        if (xVals && xVals.length) {
            const first = toFiniteNumber(xVals[0]);
            const last = toFiniteNumber(xVals[xVals.length - 1]);
            if (first !== null && last !== null) {
                let leftStep = null;
                let rightStep = null;
                if (xVals.length > 1) {
                    const second = toFiniteNumber(xVals[1]);
                    const penultimate = toFiniteNumber(xVals[xVals.length - 2]);
                    if (second !== null) leftStep = Math.abs(second - first);
                    if (penultimate !== null) rightStep = Math.abs(last - penultimate);
                }
                const halfLeft = leftStep && leftStep > 0 ? leftStep / 2 : 0;
                const halfRight = rightStep && rightStep > 0 ? rightStep / 2 : 0;
                domainStart = Math.min(first, last) - halfLeft;
                domainEnd = Math.max(first, last) + halfRight;
            }
        }

        // Fallback to figure meta x-bounds.
        const meta = graphDiv.layout.meta || {};
        if (domainStart === null || domainEnd === null || domainEnd <= domainStart) {
            const metaMin = toFiniteNumber(meta.x_min);
            const metaMax = toFiniteNumber(meta.x_max);
            if (metaMin !== null && metaMax !== null && metaMax > metaMin) {
                domainStart = metaMin;
                domainEnd = metaMax;
            }
        }

        // Last fallback: current axis range.
        const xaxis = graphDiv.layout.xaxis;
        if ((domainStart === null || domainEnd === null || domainEnd <= domainStart) && xaxis && xaxis.range) {
            const rangeMin = toFiniteNumber(xaxis.range[0]);
            const rangeMax = toFiniteNumber(xaxis.range[1]);
            if (rangeMin !== null && rangeMax !== null && rangeMax > rangeMin) {
                domainStart = rangeMin;
                domainEnd = rangeMax;
            }
        }
        if (domainStart === null || domainEnd === null || domainEnd <= domainStart) return;

        const domainSpan = domainEnd - domainStart;
        if (!isFinite(domainSpan) || domainSpan <= 0) return;

        // Primary mapping: progress through audio duration -> progress through full spectrogram domain.
        // This is robust when spectrogram bins represent centers (domain span differs slightly from duration).
        let markerPosition = null;
        if (isFinite(duration) && duration > 0) {
            const progress = clamp(currentTime / duration, 0, 1);
            markerPosition = domainStart + progress * domainSpan;
        }

        // Fallback: direct seconds-to-x conversion.
        if (markerPosition === null || !isFinite(markerPosition)) {
            let xToSeconds = toFiniteNumber(meta.x_to_seconds);
            if (xToSeconds === null || xToSeconds <= 0) {
                const xTitle = (xaxis && xaxis.title && (xaxis.title.text || xaxis.title)) || '';
                xToSeconds = String(xTitle).toLowerCase().includes('minute') ? 60.0 : 1.0;
            }
            markerPosition = domainStart + (currentTime / xToSeconds);
        }

        markerPosition = clamp(markerPosition, domainStart, domainEnd);

        // Update the shape (playback marker line)
        if (!graphDiv.layout.shapes || graphDiv.layout.shapes.length === 0) {
            graphDiv.layout.shapes = [{
                type: 'line',
                x0: markerPosition,
                x1: markerPosition,
                y0: 0,
                y1: 1,
                yref: 'paper',
                line: {
                    color: 'rgba(255, 50, 50, 0.8)',
                    width: 2,
                    dash: 'solid'
                }
            }];
        } else {
            // Update existing marker
            graphDiv.layout.shapes[0].x0 = markerPosition;
            graphDiv.layout.shapes[0].x1 = markerPosition;
            graphDiv.layout.shapes[0].line.color = 'rgba(255, 50, 50, 0.8)';
        }

        // Use Plotly's relayout to update without full redraw
        if (window.Plotly) {
            window.Plotly.relayout(graphDiv, {
                'shapes[0].x0': markerPosition,
                'shapes[0].x1': markerPosition
            });
        }
    } catch (e) {
        // Silently fail if there's an issue
        console.debug('Error updating playback marker:', e);
    }
}
