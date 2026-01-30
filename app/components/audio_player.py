from dash import html, dcc
import dash_bootstrap_components as dbc
import base64
import os
from typing import Optional

def create_audio_player(audio_file_path: Optional[str], spectrogram_filename: str, player_id: str = None) -> html.Div:
    """
    Create an enhanced audio player component with beautiful styling and time slider.
    
    Args:
        audio_file_path: Path to the audio file (.flac)
        spectrogram_filename: Name of the spectrogram file (for labeling)
        player_id: Unique ID for the audio player
    
    Returns:
        Dash HTML component with styled audio player and time slider
    """
    if not audio_file_path or not os.path.exists(audio_file_path):
        return html.Div([
            html.Div([
                html.I(className="fas fa-music", style={
                    'color': '#6c757d', 
                    'margin-right': '8px',
                    'font-size': '14px'
                }),
                html.Small("No audio available", style={
                    'color': '#6c757d', 
                    'font-style': 'italic',
                    'font-weight': '500'
                })
            ], style={
                'display': 'flex',
                'align-items': 'center',
                'justify-content': 'center'
            })
        ], style={
            'text-align': 'center', 
            'padding': '10px',
            'background': 'rgba(248, 249, 250, 0.5)',
            'border-radius': '8px',
            'border': '1px solid #e9ecef'
        })
    
    # Generate unique ID if not provided
    if player_id is None:
        player_id = f"audio-{hash(spectrogram_filename) % 10000}"
    
    audio_filename = os.path.basename(audio_file_path)
    
    return html.Div([
        # Audio icon and filename
        html.Div([
            html.I(className="fas fa-headphones", style={
                'color': '#667eea',
                'margin-right': '8px',
                'font-size': '14px',
                'flex-shrink': '0'  # Keep icon size fixed
            }),
            html.Span(f"Audio: {audio_filename}", style={
                'font-size': '12px',
                'font-weight': '500',
                'color': '#495057',
                'overflow': 'hidden',
                'text-overflow': 'ellipsis',
                'white-space': 'nowrap',
                'min-width': '0'  # Allow shrinking
            })
        ], style={
            'display': 'flex',
            'align-items': 'center',
            'margin-bottom': '8px',
            'padding': '6px 0',
            'max-width': '100%',  # Constrain to container
            'overflow': 'hidden'
        }),
        
        # Custom audio controls with time slider
        html.Div([
            # Play/Pause button
            html.Div([
                dbc.Button([
                    html.I(
                        className="fas fa-play", 
                        id=f'{player_id}-play-icon', 
                        style={'font-size': '10px'}
                    )
                ], 
                id=f'{player_id}-play-btn', 
                size='sm',
                style={
                    'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                    'border': 'none',
                    'color': 'white',
                    'width': '28px',
                    'height': '28px',
                    'border-radius': '50%',
                    'display': 'flex',
                    'align-items': 'center',
                    'justify-content': 'center',
                    'margin-right': '8px'
                })
            ], style={'display': 'flex', 'align-items': 'center'}),
            
            # Time slider and duration
            html.Div([
                # Time display and slider
                html.Div([
                    html.Span("0:00", id=f'{player_id}-current-time', style={
                        'font-size': '10px',
                        'color': '#6c757d',
                        'margin-right': '8px',
                        'min-width': '30px'
                    }),
                    
                    # Dash slider with better interaction handling
                    dcc.Slider(
                        id=f'{player_id}-time-slider',
                        min=0,
                        max=100,
                        step=0.1,
                        value=0,
                        marks=None,
                        tooltip={"placement": "bottom", "always_visible": False},
                        className='custom-time-slider',
                        updatemode='drag'  # Allow dragging
                    ),
                    
                    html.Span("0:00", id=f'{player_id}-duration', style={
                        'font-size': '10px',
                        'color': '#6c757d',
                        'margin-left': '8px',
                        'min-width': '30px'
                    })
                ], style={
                    'display': 'flex',
                    'align-items': 'center',
                    'flex': '1'
                })
            ], style={'flex': '1'})
        ], style={
            'display': 'flex',
            'align-items': 'center',
            'margin-bottom': '5px'
        }),
        
        # Hidden HTML5 audio element for actual playback
        html.Audio(
            id=f'{player_id}-audio',
            src=f'/audio/{audio_filename}',  # Direct src instead of lazy loading
            preload='metadata',  # Load metadata immediately
            style={'display': 'none'}
        ),
        
        # Hidden dummy element for slider callback
        html.Div(id={'type': 'slider-dummy', 'id': player_id}, style={'display': 'none'})
    ], style={
        'padding': '10px',
        'background': 'rgba(102, 126, 234, 0.05)',
        'border-radius': '8px',
        'border': '1px solid rgba(102, 126, 234, 0.2)',
        'margin': '5px 0'
    })


def create_modal_audio_player(audio_file_path: Optional[str], spectrogram_filename: str, player_id: str = None) -> html.Div:
    """
    Create an enhanced audio player for the modal with pitch shift controls.
    
    Args:
        audio_file_path: Path to the audio file
        spectrogram_filename: Name of the spectrogram file
        player_id: Unique ID for the audio player
    
    Returns:
        Enhanced Dash HTML component with pitch shift controls
    """
    if not audio_file_path or not os.path.exists(audio_file_path):
        return html.Div([
            html.Div([
                html.I(className="fas fa-music", style={
                    'color': '#6c757d', 
                    'margin-right': '8px',
                    'font-size': '16px'
                }),
                html.Small("No audio available", style={
                    'color': '#6c757d', 
                    'font-style': 'italic',
                    'font-weight': '500'
                })
            ], style={
                'display': 'flex',
                'align-items': 'center',
                'justify-content': 'center',
                'padding': '15px'
            })
        ], style={
            'background': 'rgba(248, 249, 250, 0.5)',
            'border-radius': '8px',
            'border': '1px solid #e9ecef'
        })
    
    # Generate unique ID if not provided
    if player_id is None:
        player_id = f"audio-{hash(spectrogram_filename) % 10000}"
    
    audio_filename = os.path.basename(audio_file_path)
    
    return html.Div([
        # Audio icon and filename
        html.Div([
            html.I(className="fas fa-waveform-lines modal-audio-icon"),
            html.Span(f"Audio: {audio_filename}", className="modal-audio-filename")
        ], className="modal-audio-header"),

        # Custom audio controls with time slider
        html.Div([
            # Play/Pause button
            html.Div([
                dbc.Button([
                    html.I(
                        className="fas fa-play",
                        id=f'{player_id}-play-icon',
                        style={'font-size': '12px'}
                    )
                ],
                id=f'{player_id}-play-btn',
                size='sm',
                className="modal-play-btn")
            ], style={'display': 'flex', 'align-items': 'center'}),

            # Time slider and duration
            html.Div([
                html.Span("0:00", id=f'{player_id}-current-time', className="modal-time-display"),

                # Dash slider for time control
                dcc.Slider(
                    id=f'{player_id}-time-slider',
                    min=0,
                    max=100,
                    step=0.1,
                    value=0,
                    marks=None,
                    tooltip={"placement": "bottom", "always_visible": False},
                    className='custom-time-slider',
                    updatemode='drag'
                ),

                html.Span("0:00", id=f'{player_id}-duration', className="modal-time-display")
            ], style={
                'display': 'flex',
                'align-items': 'center',
                'flex': '1'
            })
        ], style={
            'display': 'flex',
            'align-items': 'center',
            'margin-bottom': '12px'
        }),
        
        # Pitch shift controls
        html.Div([
            html.Label([
                html.I(className="fas fa-gauge-high modal-control-icon"),
                html.Span("Playback Speed:", className="modal-control-label")
            ], className="modal-control-header"),

            html.Div([
                dcc.Slider(
                    id=f'{player_id}-pitch-slider',
                    min=0.1,
                    max=4.0,
                    step=0.05,
                    value=1.0,
                    marks={
                        0.1: {'label': '0.1x', 'style': {'fontSize': '9px'}},
                        0.25: {'label': '0.25x', 'style': {'fontSize': '9px'}},
                        0.5: {'label': '0.5x', 'style': {'fontSize': '9px'}},
                        1.0: {'label': '1x', 'style': {'fontSize': '10px', 'fontWeight': 'bold'}},
                        2.0: {'label': '2x', 'style': {'fontSize': '9px'}},
                        4.0: {'label': '4x', 'style': {'fontSize': '9px'}}
                    },
                    tooltip={"placement": "bottom", "always_visible": False},
                    className='pitch-shift-slider'
                ),
                html.Div(id=f'{player_id}-pitch-display', children="1.0x", className="modal-control-display")
            ])
        ], className="modal-control-section"),

        # Bass boost / Low frequency equalizer
        html.Div([
            html.Label([
                html.I(className="fas fa-volume-low modal-control-icon"),
                html.Span("Bass Boost (Low Freq):", className="modal-control-label")
            ], className="modal-control-header"),

            html.Div([
                dcc.Slider(
                    id=f'{player_id}-bass-slider',
                    min=0,
                    max=24,
                    step=1,
                    value=0,
                    marks={
                        0: {'label': '0 dB', 'style': {'fontSize': '9px'}},
                        6: {'label': '+6', 'style': {'fontSize': '9px'}},
                        12: {'label': '+12', 'style': {'fontSize': '9px'}},
                        18: {'label': '+18', 'style': {'fontSize': '9px'}},
                        24: {'label': '+24 dB', 'style': {'fontSize': '9px'}}
                    },
                    tooltip={"placement": "bottom", "always_visible": False},
                    className='bass-boost-slider'
                ),
                html.Div(id=f'{player_id}-bass-display', children="0 dB", className="modal-control-display")
            ])
        ], className="modal-control-section"),
        
        # Hidden HTML5 audio element
        html.Audio(
            id=f'{player_id}-audio',
            src=f'/audio/{audio_filename}',
            preload='metadata',
            style={'display': 'none'}
        ),
        
        # Hidden dummy elements for callbacks
        html.Div(id={'type': 'slider-dummy', 'id': player_id}, style={'display': 'none'}),
        html.Div(id=f'{player_id}-pitch-output', style={'display': 'none'}),
        html.Div(id=f'{player_id}-bass-output', style={'display': 'none'})
    ], className="modal-audio-container")

def create_audio_player_with_controls(audio_file_path: Optional[str], spectrogram_filename: str, player_id: str = None) -> html.Div:
    """
    Create an enhanced audio player with additional controls and beautiful styling.
    """
    if not audio_file_path or not os.path.exists(audio_file_path):
        return html.Div([
            html.Div([
                html.I(className="fas fa-music", style={
                    'color': '#6c757d', 
                    'margin-right': '8px',
                    'font-size': '16px'
                }),
                html.Small("No audio available", style={
                    'color': '#6c757d', 
                    'font-style': 'italic',
                    'font-weight': '500'
                })
            ], style={
                'display': 'flex',
                'align-items': 'center',
                'justify-content': 'center'
            })
        ], style={
            'text-align': 'center', 
            'padding': '15px',
            'background': 'rgba(248, 249, 250, 0.8)',
            'border-radius': '10px',
            'border': '1px solid #e9ecef'
        })
    
    # Generate unique ID if not provided
    if player_id is None:
        player_id = f"audio-{hash(spectrogram_filename) % 10000}"
    
    audio_filename = os.path.basename(audio_file_path)
    
    return html.Div([
        # Header with audio info
        html.Div([
            html.I(className="fas fa-waveform-lines", style={
                'color': '#667eea',
                'margin-right': '10px',
                'font-size': '16px',
                'flex-shrink': '0'  # Keep icon size fixed
            }),
            html.Span(f"{audio_filename}", style={
                'font-size': '14px',
                'font-weight': '600',
                'color': '#495057',
                'overflow': 'hidden',
                'text-overflow': 'ellipsis',
                'white-space': 'nowrap',
                'min-width': '0'  # Allow shrinking
            })
        ], style={
            'display': 'flex',
            'align-items': 'center',
            'margin-bottom': '12px',
            'padding-bottom': '8px',
            'border-bottom': '1px solid rgba(102, 126, 234, 0.2)',
            'max-width': '100%',  # Constrain to container
            'overflow': 'hidden'
        }),
        
        # Audio element (hidden, controlled via JavaScript)
        html.Audio(
            id=f'{player_id}-audio',
            src=f'/audio/{audio_filename}',  # Direct src instead of lazy loading
            preload='metadata',  # Load metadata immediately
            style={'display': 'none'}
        ),
        
        # Custom controls with better styling
        html.Div([
            dbc.ButtonGroup([
                dbc.Button([
                    html.I(className="fas fa-play", style={'font-size': '12px'})
                ], id=f'{player_id}-play', size='sm', 
                style={
                    'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                    'border': 'none',
                    'color': 'white',
                    'width': '35px',
                    'height': '30px'
                }),
                dbc.Button([
                    html.I(className="fas fa-pause", style={'font-size': '12px'})
                ], id=f'{player_id}-pause', size='sm',
                style={
                    'background': '#6c757d',
                    'border': 'none',
                    'color': 'white',
                    'width': '35px',
                    'height': '30px'
                }),
                dbc.Button([
                    html.I(className="fas fa-stop", style={'font-size': '12px'})
                ], id=f'{player_id}-stop', size='sm',
                style={
                    'background': '#dc3545',
                    'border': 'none',
                    'color': 'white',
                    'width': '35px',
                    'height': '30px'
                }),
            ], style={'margin-bottom': '10px'}),
        ], style={'text-align': 'center'}),
        
        # Progress bar with custom styling
        html.Div([
            dbc.Progress(
                id=f'{player_id}-progress',
                value=0,
                style={
                    'height': '6px',
                    'background-color': 'rgba(102, 126, 234, 0.2)',
                    'border-radius': '3px'
                },
                bar_style={
                    'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
                }
            )
        ], style={'margin-bottom': '8px'}),
        
        # Time display
        html.Div([
            html.Small("Ready to play", style={
                'color': '#6c757d',
                'font-size': '11px',
                'font-weight': '500'
            })
        ], style={'text-align': 'center'})
    ], style={
        'padding': '15px',
        'background': 'rgba(102, 126, 234, 0.05)',
        'border-radius': '10px',
        'border': '1px solid rgba(102, 126, 234, 0.2)',
        'margin': '8px 0',
        'box-shadow': '0 2px 8px rgba(0, 0, 0, 0.05)'
    })

def create_simple_audio_link(audio_file_path: Optional[str], spectrogram_filename: str) -> html.Div:
    """
    Create a beautifully styled download link for the audio file.
    """
    if not audio_file_path or not os.path.exists(audio_file_path):
        return html.Div([
            html.Div([
                html.I(className="fas fa-music", style={
                    'color': '#6c757d', 
                    'margin-right': '8px'
                }),
                html.Small("No audio available", style={
                    'color': '#6c757d', 
                    'font-style': 'italic',
                    'font-weight': '500'
                })
            ], style={
                'display': 'flex',
                'align-items': 'center',
                'justify-content': 'center'
            })
        ], style={
            'text-align': 'center', 
            'padding': '10px',
            'background': 'rgba(248, 249, 250, 0.5)',
            'border-radius': '8px',
            'border': '1px solid #e9ecef'
        })
    
    audio_filename = os.path.basename(audio_file_path)
    
    return html.Div([
        html.A([
            html.Div([
                html.I(className="fas fa-download", style={
                    'color': '#667eea',
                    'margin-right': '8px',
                    'font-size': '14px'
                }),
                html.Span(f"Download: {audio_filename[:25]}{'...' if len(audio_filename) > 25 else ''}", style={
                    'color': '#667eea',
                    'font-weight': '500',
                    'font-size': '12px'
                })
            ], style={
                'display': 'flex',
                'align-items': 'center',
                'justify-content': 'center',
                'padding': '8px 12px',
                'background': 'rgba(102, 126, 234, 0.1)',
                'border-radius': '6px',
                'border': '1px solid rgba(102, 126, 234, 0.3)',
                'transition': 'all 0.3s ease'
            })
        ], href=f'/audio/{audio_filename}', download=audio_filename, target='_blank',
        style={'text-decoration': 'none'})
    ], style={'text-align': 'center', 'padding': '5px'}) 