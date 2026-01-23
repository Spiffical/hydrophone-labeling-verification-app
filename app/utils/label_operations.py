"""
Label file operations for the labeling verification app.
Handles reading and writing labels.json files with proper locking.
"""
import json
import os
import tempfile
from typing import Dict, List, Optional, Any, Union
from filelock import FileLock

# Create a FileLock instance at module level
_lock_file = os.path.join(tempfile.gettempdir(), 'hydrophone_labels_lock.lock')
_file_lock = FileLock(_lock_file)


def load_labels(filepath: str) -> Dict[str, List[str]]:
    """
    Load labels from a JSON file.
    
    Args:
        filepath: Path to the labels.json file
        
    Returns:
        Dictionary mapping spectrogram filenames to lists of label strings
    """
    if not filepath or not os.path.exists(filepath):
        return {}
    
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        # Normalize all labels to list format
        normalized = {}
        for filename, labels in data.items():
            if isinstance(labels, list):
                normalized[filename] = labels
            else:
                normalized[filename] = [str(labels)]
        
        return normalized
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading labels from {filepath}: {e}")
        return {}


def save_labels(filepath: str, filename: str, labels: List[str]) -> bool:
    """
    Save or update labels for a specific file.
    Uses file locking to prevent concurrent write issues.
    
    Args:
        filepath: Path to the labels.json file
        filename: The spectrogram filename being labeled
        labels: List of label strings to save
        
    Returns:
        True if save was successful, False otherwise
    """
    with _file_lock:
        # Load existing data
        current_data = {}
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            try:
                with open(filepath, 'r') as f:
                    current_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                current_data = {}
        
        # Update or remove the entry
        if labels:
            current_data[filename] = labels
        elif filename in current_data:
            del current_data[filename]
        
        # Write back
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
            
            with open(filepath, 'w') as f:
                json.dump(current_data, f, indent=4, sort_keys=True)
            return True
        except IOError as e:
            print(f"Error saving labels to {filepath}: {e}")
            return False


def add_label(filepath: str, filename: str, label: str) -> bool:
    """
    Add a single label to a file's labels.
    
    Args:
        filepath: Path to the labels.json file
        filename: The spectrogram filename
        label: The label to add
        
    Returns:
        True if successful
    """
    with _file_lock:
        current_data = load_labels(filepath)
        labels = current_data.get(filename, [])
        
        if label not in labels:
            labels.append(label)
        
        return save_labels_unlocked(filepath, current_data, filename, labels)


def remove_label(filepath: str, filename: str, label: str) -> bool:
    """
    Remove a single label from a file's labels.
    
    Args:
        filepath: Path to the labels.json file
        filename: The spectrogram filename
        label: The label to remove
        
    Returns:
        True if successful
    """
    with _file_lock:
        current_data = load_labels(filepath)
        labels = current_data.get(filename, [])
        
        if label in labels:
            labels.remove(label)
        
        return save_labels_unlocked(filepath, current_data, filename, labels)


def save_labels_unlocked(filepath: str, current_data: Dict, filename: str, labels: List[str]) -> bool:
    """
    Internal function to save labels without acquiring lock (caller must hold lock).
    """
    if labels:
        current_data[filename] = labels
    elif filename in current_data:
        del current_data[filename]
    
    try:
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(current_data, f, indent=4, sort_keys=True)
        return True
    except IOError as e:
        print(f"Error saving labels to {filepath}: {e}")
        return False


def get_labels_for_file(filepath: str, filename: str) -> List[str]:
    """
    Get labels for a specific file.
    
    Args:
        filepath: Path to the labels.json file
        filename: The spectrogram filename
        
    Returns:
        List of label strings for the file
    """
    data = load_labels(filepath)
    return data.get(filename, [])


def get_default_labels_path(spectrogram_folder: str) -> str:
    """
    Get the default labels.json path for a spectrogram folder.
    
    For hierarchical structures: DATE/DEVICE/labels.json
    For flat structures: FOLDER/labels.json
    
    Args:
        spectrogram_folder: Path to the spectrograms folder
        
    Returns:
        Path to the labels.json file
    """
    if not spectrogram_folder:
        return ""
    
    # If spectrogram_folder ends with "onc_spectrograms", put labels.json at the device level
    if spectrogram_folder.endswith("onc_spectrograms"):
        parent = os.path.dirname(spectrogram_folder)
        return os.path.join(parent, "labels.json")
    
    # Otherwise put it in the same folder
    return os.path.join(spectrogram_folder, "labels.json")
