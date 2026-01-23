// Audio player control functions
window.dash_clientside = Object.assign({}, window.dash_clientside, {
    namespace: {
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

                // Handle pitch shift sliders (for modal audio players)
                const pitchSlider = document.getElementById(playerId + '-pitch-slider');
                const pitchDisplay = document.getElementById(playerId + '-pitch-display');

                if (pitchSlider && !pitchSlider.hasPitchListener) {
                    pitchSlider.hasPitchListener = true;

                    // Listen for changes to the Dash slider value
                    const observer = new MutationObserver(function (mutations) {
                        const sliderElement = pitchSlider.querySelector('.rc-slider-handle');
                        if (sliderElement) {
                            const ariaValue = sliderElement.getAttribute('aria-valuenow');
                            if (ariaValue) {
                                const rate = parseFloat(ariaValue);
                                if (!isNaN(rate) && rate >= 0.5 && rate <= 2.0) {
                                    audio.playbackRate = rate;
                                    if (pitchDisplay) {
                                        pitchDisplay.textContent = rate.toFixed(1) + 'x';
                                    }
                                }
                            }
                        }
                    });

                    observer.observe(pitchSlider, {
                        attributes: true,
                        subtree: true,
                        attributeFilter: ['aria-valuenow', 'style']
                    });
                }

                // Play/pause button click handler
                if (playBtn && !playBtn.hasClickHandler) {
                    playBtn.hasClickHandler = true;
                    playBtn.addEventListener('click', function (e) {
                        e.preventDefault();
                        e.stopPropagation();

                        if (audio.paused) {
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
            });

            return '';
        }
    }
});

// Helper function to safely update slider position (avoid conflicts)
function updateSliderPositionSafely(slider, progress) {
    try {
        // Only update if we're confident we won't interfere with user interaction
        if (slider.isUserInteracting) return;

        const sliderContainer = slider.querySelector('.rc-slider');
        if (sliderContainer) {
            const handle = sliderContainer.querySelector('.rc-slider-handle');
            const track = sliderContainer.querySelector('.rc-slider-track');
            if (handle && track) {
                // Use requestAnimationFrame to ensure smooth updates
                requestAnimationFrame(() => {
                    if (!slider.isUserInteracting) {
                        handle.style.left = progress + '%';
                        track.style.width = progress + '%';
                        handle.setAttribute('aria-valuenow', progress);
                    }
                });
            }
        }
    } catch (e) {
        console.warn('Error updating slider position:', e);
    }
}

// Improved slider interaction setup - better click/drag detection
function setupSliderInteraction(slider, audio) {
    const sliderContainer = slider.querySelector('.rc-slider');
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

    // Handle mouse move while potentially dragging
    document.addEventListener('mousemove', function (e) {
        if (isActivelyDragging) {
            if (!dragStarted) {
                // This is the start of an actual drag
                dragStarted = true;
            }
            handleSliderSeek(e, sliderContainer, audio);
        }
    });

    // Handle mouse up (end of interaction)
    document.addEventListener('mouseup', function (e) {
        if (isActivelyDragging) {
            const clickDuration = Date.now() - mouseDownTime;

            // If it was a quick click (not a drag), handle it as a seek
            if (!dragStarted && clickDuration < 200) {
                handleSliderSeek(e, sliderContainer, audio);
            }

            isActivelyDragging = false;
            dragStarted = false;

            // Give a small delay before allowing updates again
            setTimeout(() => {
                slider.isUserInteracting = false;
            }, 100);
        }
    });

    // Disable Dash's default click handling on the slider
    sliderContainer.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
    });
}

// Improved slider seeking function
function handleSliderSeek(e, sliderContainer, audio) {
    if (!audio.duration) return;

    const rect = sliderContainer.getBoundingClientRect();
    const x = e.clientX - rect.left;
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
    updateSliderPositionImmediately(sliderContainer.parentElement, progress);

    console.log('Seeking to:', newTime, 'seconds (', progress, '%)');
}

// Function to update slider position immediately (used during manual seeking)
function updateSliderPositionImmediately(slider, progress) {
    try {
        const sliderContainer = slider.querySelector('.rc-slider');
        if (sliderContainer) {
            const handle = sliderContainer.querySelector('.rc-slider-handle');
            const track = sliderContainer.querySelector('.rc-slider-track');
            if (handle && track) {
                handle.style.left = progress + '%';
                track.style.width = progress + '%';
                handle.setAttribute('aria-valuenow', progress);
            }
        }
    } catch (e) {
        console.warn('Error updating slider position immediately:', e);
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