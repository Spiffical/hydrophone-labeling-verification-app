// Audio player control functions
window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.namespace = Object.assign({}, window.dash_clientside.namespace, {
        // Initialize audio players when page loads
        initializeAudioPlayers: function () {
            // Optimized initialization - minimal logging, fast DOM queries
            const audioElements = document.querySelectorAll('audio[id$="-audio"]');

            audioElements.forEach(function (audio) {
                const playerId = audio.id.replace('-audio', '');
                const playBtn = document.getElementById(playerId + '-play-btn');
                const playIcon = document.getElementById(playerId + '-play-icon');
                const timeSlider = document.getElementById(playerId + '-time-slider');
                const currentTimeEl = document.getElementById(playerId + '-current-time');
                const durationEl = document.getElementById(playerId + '-duration');
                const pitchSlider = document.getElementById(playerId + '-pitch-slider');
                const pitchDisplay = document.getElementById(playerId + '-pitch-display');
                const bassSlider = document.getElementById(playerId + '-bass-slider');
                const bassDisplay = document.getElementById(playerId + '-bass-display');

                if (!audio.hasEventListeners) {
                    audio.hasEventListeners = true;

                    // Update duration when metadata is loaded
                    audio.addEventListener('loadedmetadata', function () {
                        if (durationEl && audio.duration) {
                            const minutes = Math.floor(audio.duration / 60);
                            const seconds = Math.floor(audio.duration % 60);
                            durationEl.textContent = minutes + ':' + (seconds < 10 ? '0' : '') + seconds;
                        }
                    });

                    // Update time and slider during playback
                    audio.addEventListener('timeupdate', function () {
                        if (currentTimeEl && audio.duration) {
                            const minutes = Math.floor(audio.currentTime / 60);
                            const seconds = Math.floor(audio.currentTime % 60);
                            currentTimeEl.textContent = minutes + ':' + (seconds < 10 ? '0' : '') + seconds;

                            // Only update slider if user is not interacting with it
                            if (timeSlider && !timeSlider.isUserInteracting && !audio.isSliderSeeking) {
                                const progress = (audio.currentTime / audio.duration) * 100;
                                updateSliderPositionSafely(timeSlider, progress);
                            }

                            // Update playback position marker on spectrogram if in modal
                            if (playerId.startsWith('modal-')) {
                                updateSpectrogramPlaybackMarker(audio.currentTime, audio.duration);
                            }
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
                }

                // Set up Web Audio API only for modal players that expose tone controls.
                if (!audio.audioContext && (pitchSlider || bassSlider)) {
                    try {
                        const AudioContext = window.AudioContext || window.webkitAudioContext;
                        audio.audioContext = new AudioContext();
                        audio.sourceNode = audio.audioContext.createMediaElementSource(audio);

                        // Create bass boost filter (low shelf filter)
                        audio.bassFilter = audio.audioContext.createBiquadFilter();
                        audio.bassFilter.type = 'lowshelf';
                        audio.bassFilter.frequency.value = 200; // Boost frequencies below 200Hz
                        audio.bassFilter.gain.value = 0; // Initial gain (0 dB)

                        // Connect: source -> bass filter -> destination
                        audio.sourceNode.connect(audio.bassFilter);
                        audio.bassFilter.connect(audio.audioContext.destination);

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
                    });
                }

                if (bassSlider) {
                    bindSliderValueSync(bassSlider, 0, 24, function (gain) {
                        const roundedGain = Math.round(gain);
                        // Apply bass boost via Web Audio API
                        if (audio.bassFilter) {
                            audio.bassFilter.gain.value = roundedGain;
                        }
                        if (bassDisplay) {
                            bassDisplay.textContent = (roundedGain > 0 ? '+' : '') + roundedGain + ' dB';
                        }
                    });
                }

                // Play/pause button click handler
                if (playBtn && !playBtn.hasClickHandler) {
                    playBtn.hasClickHandler = true;
                    playBtn.addEventListener('click', function (e) {
                        e.preventDefault();
                        e.stopPropagation();

                        if (audio.paused) {
                            if (audio.audioContext && audio.audioContext.state === 'suspended') {
                                audio.audioContext.resume().catch(function () { });
                            }
                            // If audio has ended, reset it to the beginning
                            if (audio.ended) {
                                audio.currentTime = 0;
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
                    setupSliderInteraction(timeSlider, audio);
                }

                // Keep audio currentTime synchronized with timeline slider value.
                // This is required for Dash 4 slider DOM where internal value changes
                // may occur without our custom drag handler firing consistently.
                if (timeSlider && !timeSlider.hasTimeSyncBinding) {
                    timeSlider.hasTimeSyncBinding = true;
                    bindSliderValueSync(timeSlider, 0, 100, function (progress) {
                        if (!audio.duration || isNaN(progress)) return;
                        const targetTime = (progress / 100) * audio.duration;
                        const delta = Math.abs((audio.currentTime || 0) - targetTime);
                        if (timeSlider.isUserInteracting || delta > 2) {
                            audio.currentTime = targetTime;
                        }
                    });
                }
            });

            return '';
        }
});

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
    return slider.querySelector('.dash-slider-root') || slider.querySelector('.rc-slider');
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
            dashInput.value = String(Math.round(clamped * 10) / 10);
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
function setupSliderInteraction(slider, audio) {
    const sliderContainer = getSliderRoot(slider);
    if (!sliderContainer) return;

    let isActivelyDragging = false;
    let dragStarted = false;
    let mouseDownTime = 0;

    // Handle mouse down (potential start of drag)
    sliderContainer.addEventListener('mousedown', function (e) {
        mouseDownTime = Date.now();
        dragStarted = false;
        isActivelyDragging = true;
        slider.isUserInteracting = true;

        // Prevent default to avoid conflicts with Dash
        e.preventDefault();
        e.stopPropagation();
    });

    sliderContainer.addEventListener('touchstart', function (e) {
        mouseDownTime = Date.now();
        dragStarted = false;
        isActivelyDragging = true;
        slider.isUserInteracting = true;
        e.preventDefault();
        e.stopPropagation();
    }, { passive: false });

    // Handle mouse move while potentially dragging
    document.addEventListener('mousemove', function (e) {
        if (isActivelyDragging) {
            if (!dragStarted) {
                // This is the start of an actual drag
                dragStarted = true;
            }
            handleSliderSeek(e, sliderContainer, slider, audio);
        }
    });

    document.addEventListener('touchmove', function (e) {
        if (isActivelyDragging) {
            if (!dragStarted) {
                dragStarted = true;
            }
            handleSliderSeek(e, sliderContainer, slider, audio);
        }
    }, { passive: false });

    // Handle mouse up (end of interaction)
    document.addEventListener('mouseup', function (e) {
        if (isActivelyDragging) {
            const clickDuration = Date.now() - mouseDownTime;

            // If it was a quick click (not a drag), handle it as a seek
            if (!dragStarted && clickDuration < 200) {
                handleSliderSeek(e, sliderContainer, slider, audio);
            }

            isActivelyDragging = false;
            dragStarted = false;

            // Give a small delay before allowing updates again
            setTimeout(() => {
                slider.isUserInteracting = false;
            }, 100);
        }
    });

    document.addEventListener('touchend', function (e) {
        if (isActivelyDragging) {
            const clickDuration = Date.now() - mouseDownTime;
            if (!dragStarted && clickDuration < 250) {
                handleSliderSeek(e, sliderContainer, slider, audio);
            }

            isActivelyDragging = false;
            dragStarted = false;
            setTimeout(() => {
                slider.isUserInteracting = false;
            }, 100);
        }
    }, { passive: false });

    // Disable Dash's default click handling on the slider
    sliderContainer.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
    });
}

// Improved slider seeking function
function handleSliderSeek(e, sliderContainer, slider, audio) {
    if (!audio.duration) return;

    const rect = sliderContainer.getBoundingClientRect();
    const clientX = getClientXFromEvent(e);
    if (clientX === null) return;

    const x = clientX - rect.left;
    const width = rect.width;

    // Ensure we stay within bounds
    const clampedX = Math.max(0, Math.min(width, x));
    const progress = (clampedX / width) * 100;

    const newTime = (progress / 100) * audio.duration;

    // If audio has ended and we're seeking to a position before the end, reset it
    if (audio.ended && newTime < audio.duration - 0.1) {
        console.log('Resetting ended audio for seeking');
        // Reset the audio element to allow playback from earlier positions
        audio.load();

        // Wait for it to be ready, then set the time
        audio.addEventListener('canplay', function onCanPlay() {
            audio.removeEventListener('canplay', onCanPlay);
            audio.currentTime = newTime;
        });
    } else {
        // Normal seeking
        audio.currentTime = newTime;
    }

    // Update the visual position immediately during manual interaction
    updateSliderPositionImmediately(slider, progress);

    console.log('Seeking to:', newTime, 'seconds (', progress, '%)');
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
function bindSliderValueSync(slider, min, max, applyValue) {
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
            slider.addEventListener(eventName, scheduleSync, { passive: true });
        });

    const observer = new MutationObserver(function () {
        scheduleSync();
    });
    observer.observe(slider, {
        attributes: true,
        childList: true,
        subtree: true,
        characterData: true
    });

    // Initial and delayed sync so first render and async hydration are covered.
    syncNow();
    setTimeout(syncNow, 100);
    setTimeout(syncNow, 350);

    // Polling fallback for environments where slider value updates bypass DOM events.
    // This keeps readouts (e.g., 1.00x / +12 dB) in sync with the actual handle value.
    if (!slider.valueSyncInterval) {
        slider.valueSyncInterval = setInterval(syncNow, 200);
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function () {
    console.log('DOM loaded, setting up audio controls...');

    // Initial setup with delay to ensure DOM is fully ready
    setTimeout(function () {
        if (window.dash_clientside && window.dash_clientside.namespace) {
            window.dash_clientside.namespace.initializeAudioPlayers();
        }
    }, 500);

    // Set up a mutation observer to handle dynamically added audio players
    const observer = new MutationObserver(function (mutations) {
        let shouldReinitialize = false;

        mutations.forEach(function (mutation) {
            if (mutation.type === 'childList') {
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
            setTimeout(function () {
                if (window.dash_clientside && window.dash_clientside.namespace) {
                    window.dash_clientside.namespace.initializeAudioPlayers();
                }
            }, 100);
        }
    });

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

        // Get the x-axis range from the graph
        const xaxis = graphDiv.layout.xaxis;
        if (!xaxis || !xaxis.range) return;

        const xMin = xaxis.range[0];
        const xMax = xaxis.range[1];
        const totalTime = xMax - xMin;

        // Calculate the position of the playback marker
        const markerPosition = xMin + (currentTime / duration) * totalTime;

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
