#!/usr/bin/env python3
"""
Unified Predictions Tracker

Standardized JSON format for model predictions across whale detection
and anomaly detection projects. Matches the Oceans 3.0 Predictions
JSON Schema v2.0 (see OCEANS3_JSON_SCHEMA.md).

Usage:
    tracker = UnifiedPredictionTracker(output_path='predictions.json')
    tracker.set_model_info(model_id='sha256-abc123', architecture='resnet18')
    tracker.add_data_source(
        data_source_id='ICLISTENHF1353_CLAYO_2019',
        device_code='ICLISTENHF1353',
        location_name='Clayoquot Slope',
    )

    # For single-class detector (e.g., whale)
    tracker.add_item(
        item_id='seg_000',
        data_source_id='ICLISTENHF1353_CLAYO_2019',
        audio_start_time='2019-06-30T00:04:58Z',
        audio_end_time='2019-06-30T00:05:38Z',
        model_outputs=[{
            'class_hierarchy': 'Biophony > Marine mammal > ... > Fin whale',
            'score': 0.87
        }]
    )

    tracker.save()
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class UnifiedPredictionTracker:
    """Manages predictions in unified format for expert verification.

    Follows the Oceans 3.0 Predictions JSON Schema v2.0 with:
    - Model metadata (model_id hash, architecture, training info)
    - Multiple data sources (device, location, coordinates, calibration)
    - Raw model scores (not thresholded)
    - Hierarchical labels from taxonomy
    - Multi-round verification with per-label decisions
    - Pipeline provenance
    """

    VERSION = "2.0"

    def __init__(self, output_path: Union[str, Path]):
        """Initialize tracker.

        Args:
            output_path: Path to output JSON file
        """
        self.output_path = Path(output_path)
        self.data: Dict[str, Any] = {
            "schema_version": self.VERSION,
            "created_at": None,
            "updated_at": None,
            "task_type": None,
            "model": {},
            "data_sources": [],
            "spectrogram_config": {},
            "pipeline": {},
            "items": []
        }

    def set_model_info(
        self,
        model_id: str,
        architecture: Optional[str] = None,
        model_version: Optional[str] = None,
        checkpoint_path: Optional[str] = None,
        checkpoint_url: Optional[str] = None,
        trained_at: Optional[str] = None,
        wandb_run_id: Optional[str] = None,
        training_dataset_id: Optional[str] = None,
        training_dataset_version: Optional[str] = None,
        training_dataset_url: Optional[str] = None,
        training_data_time_range: Optional[str] = None,
        input_shape: Optional[List[int]] = None,
        output_classes: Optional[List[str]] = None
    ) -> None:
        """Set model metadata.

        Args:
            model_id: SHA256 hash of model weights (e.g., 'sha256-abc123')
            architecture: Model architecture name (e.g., 'resnet18')
            model_version: Human-readable version tag
            checkpoint_path: Path to model checkpoint
            checkpoint_url: URL to download the trained model weights
            trained_at: ISO timestamp of when model was trained
            wandb_run_id: Weights & Biases experiment ID
            training_dataset_id: Identifier for the training dataset
            training_dataset_version: Version of the training dataset
            training_dataset_url: URL to access the training dataset
            training_data_time_range: ISO-8601 interval (e.g., '2019-01-01T00:00:00Z/2020-01-01T00:00:00Z')
            input_shape: Expected input dimensions (e.g., [96, 96])
            output_classes: List of taxonomy paths the model can predict
        """
        model: Dict[str, Any] = {"model_id": model_id}
        optional = {
            "model_version": model_version,
            "architecture": architecture,
            "checkpoint_path": str(checkpoint_path) if checkpoint_path else None,
            "checkpoint_url": checkpoint_url,
            "trained_at": trained_at,
            "wandb_run_id": wandb_run_id,
            "training_dataset_id": training_dataset_id,
            "training_dataset_version": training_dataset_version,
            "training_dataset_url": training_dataset_url,
            "training_data_time_range": training_data_time_range,
            "input_shape": input_shape,
            "output_classes": output_classes,
        }
        for k, v in optional.items():
            if v is not None:
                model[k] = v
        self.data["model"] = model

    def add_data_source(
        self,
        data_source_id: str,
        device_code: str,
        deployment_id: Optional[str] = None,
        location_name: Optional[str] = None,
        site_code: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        depth_m: Optional[float] = None,
        channel: Optional[str] = None,
        sample_rate: Optional[float] = None,
        is_calibrated: Optional[bool] = None,
        calibration_reference: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> None:
        """Add a data source (hydrophone deployment).

        Items reference data sources via data_source_id.

        Args:
            data_source_id: Unique key within this file
            device_code: ONC device code (e.g., 'ICLISTENHF1353')
            deployment_id: ONC deployment identifier
            location_name: Human-readable location
            site_code: ONC site code (e.g., 'CLAYO')
            latitude: Decimal degrees
            longitude: Decimal degrees
            depth_m: Deployment depth in metres
            channel: Hydrophone channel (e.g., 'H')
            sample_rate: Sampling rate in Hz
            is_calibrated: True if calibrated to absolute SPL
            calibration_reference: e.g., 'dB re 1 uPa RMS'
            date_from: Start of audio time range (ISO format)
            date_to: End of audio time range (ISO format)
        """
        source: Dict[str, Any] = {
            "data_source_id": data_source_id,
            "device_code": device_code,
        }
        optional = {
            "deployment_id": deployment_id,
            "location_name": location_name,
            "site_code": site_code,
            "latitude": latitude,
            "longitude": longitude,
            "depth_m": depth_m,
            "channel": channel,
            "sample_rate": sample_rate,
            "is_calibrated": is_calibrated,
            "calibration_reference": calibration_reference,
            "date_from": date_from,
            "date_to": date_to,
        }
        for k, v in optional.items():
            if v is not None:
                source[k] = v
        self.data["data_sources"].append(source)

    def set_data_source(
        self,
        device_code: str,
        location: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        sample_rate: Optional[int] = None,
        **kwargs
    ) -> None:
        """Deprecated: use add_data_source() instead.

        Creates a single data source with an auto-generated ID.
        """
        data_source_id = kwargs.pop("data_source_id", device_code)
        self.data["data_sources"] = []  # reset to mimic old set behavior
        self.add_data_source(
            data_source_id=data_source_id,
            device_code=device_code,
            location_name=location,
            date_from=date_from,
            date_to=date_to,
            sample_rate=sample_rate,
            **kwargs,
        )

    def set_spectrogram_config(self, config: Dict[str, Any]) -> None:
        """Set spectrogram generation configuration.

        Args:
            config: Dict with parameters (nfft, window_function, overlap,
                    frequency_limits, color_limits, source, audio_source, etc.)
        """
        self.data["spectrogram_config"] = config

    def set_pipeline_info(
        self,
        pipeline_version: Optional[str] = None,
        pipeline_commit: Optional[str] = None,
        pipeline_repo: Optional[str] = None,
    ) -> None:
        """Set inference pipeline provenance.

        Args:
            pipeline_version: Semantic version of the inference pipeline
            pipeline_commit: Git commit hash
            pipeline_repo: Repository URL or name
        """
        pipeline: Dict[str, Any] = {}
        if pipeline_version is not None:
            pipeline["pipeline_version"] = pipeline_version
        if pipeline_commit is not None:
            pipeline["pipeline_commit"] = pipeline_commit
        if pipeline_repo is not None:
            pipeline["pipeline_repo"] = pipeline_repo
        self.data["pipeline"] = pipeline

    def set_task_type(self, task_type: str) -> None:
        """Set task type.

        Args:
            task_type: One of 'whale_detection', 'anomaly_detection', 'classification'
        """
        self.data["task_type"] = task_type

    def add_item(
        self,
        item_id: str,
        data_source_id: str,
        audio_start_time: str,
        audio_end_time: str,
        model_outputs: List[Dict[str, Any]],
        segment_index: Optional[int] = None,
        spectrogram_mat_path: Optional[str] = None,
        spectrogram_png_path: Optional[str] = None,
        audio_path: Optional[str] = None,
    ) -> None:
        """Add a prediction item.

        Args:
            item_id: Unique identifier (convention: {device_code}_{ISO-timestamp}_seg{NNN})
            data_source_id: FK to data_sources[].data_source_id
            audio_start_time: Absolute start time of this clip (ISO format)
            audio_end_time: Absolute end time of this clip (ISO format)
            model_outputs: List of {class_hierarchy, score} dicts (optionally with class_id)
            segment_index: Zero-based index when a recording is split into segments
            spectrogram_mat_path: Relative path to MAT spectral data file
            spectrogram_png_path: Relative path to spectrogram PNG image
            audio_path: Relative path to audio clip
        """
        item: Dict[str, Any] = {
            "item_id": item_id,
            "data_source_id": data_source_id,
            "audio_start_time": audio_start_time,
            "audio_end_time": audio_end_time,
            "model_outputs": model_outputs,
            "verifications": [],
        }
        if segment_index is not None:
            item["segment_index"] = segment_index

        paths: Dict[str, str] = {}
        if spectrogram_mat_path is not None:
            paths["spectrogram_mat_path"] = spectrogram_mat_path
        if spectrogram_png_path is not None:
            paths["spectrogram_png_path"] = spectrogram_png_path
        if audio_path is not None:
            paths["audio_path"] = audio_path
        if paths:
            item["paths"] = paths

        self.data["items"].append(item)

    def add_verification(
        self,
        item_id: str,
        verified_by: str,
        label_decisions: List[Dict[str, Any]],
        verification_status: Optional[str] = None,
        reviewer_affiliation: Optional[str] = None,
        confidence: Optional[str] = None,
        notes: str = "",
        label_source: Optional[str] = None,
        taxonomy_version: Optional[str] = None,
    ) -> bool:
        """Add expert verification to an item.

        Args:
            item_id: ID of item to verify
            verified_by: Reviewer identifier (email or username)
            label_decisions: Per-label decisions, each a dict with:
                - label (str): Taxonomy path
                - decision (str): 'accepted', 'rejected', or 'added'
                - threshold_used (float): Score threshold applied
            verification_status: 'verified', 'rejected', or 'uncertain'
            reviewer_affiliation: e.g., 'ONC', 'UVic'
            confidence: 'high', 'medium', 'low', or None
            notes: Free-text reviewer comments
            label_source: 'expert', 'auto', or 'consensus'
            taxonomy_version: Version of taxonomy used during review

        Returns:
            True if item found and updated, False otherwise
        """
        for item in self.data["items"]:
            if item["item_id"] == item_id:
                verification_round = len(item["verifications"]) + 1
                verification: Dict[str, Any] = {
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                    "verified_by": verified_by,
                    "verification_round": verification_round,
                    "label_decisions": label_decisions,
                }
                if verification_status is not None:
                    verification["verification_status"] = verification_status
                if reviewer_affiliation is not None:
                    verification["reviewer_affiliation"] = reviewer_affiliation
                if confidence is not None:
                    verification["confidence"] = confidence
                if notes:
                    verification["notes"] = notes
                if label_source is not None:
                    verification["label_source"] = label_source
                if taxonomy_version is not None:
                    verification["taxonomy_version"] = taxonomy_version
                item["verifications"].append(verification)
                return True
        return False

    def get_items_by_score_threshold(
        self,
        class_hierarchy: str,
        threshold: float,
        above: bool = True
    ) -> List[Dict]:
        """Get items filtered by score threshold for a specific class.

        Args:
            class_hierarchy: Full hierarchical class name
            threshold: Score threshold (0-1)
            above: If True, return items >= threshold; else < threshold

        Returns:
            List of matching items
        """
        matches = []
        for item in self.data["items"]:
            for output in item.get("model_outputs", []):
                if output.get("class_hierarchy") == class_hierarchy:
                    score = output.get("score", 0)
                    if (above and score >= threshold) or (not above and score < threshold):
                        matches.append(item)
                        break
        return matches

    def get_unverified_items(self) -> List[Dict]:
        """Get all items without any verifications."""
        return [item for item in self.data["items"] if not item.get("verifications")]

    def get_data_source(self, data_source_id: str) -> Optional[Dict]:
        """Look up a data source by ID.

        Args:
            data_source_id: The data_source_id to find

        Returns:
            Data source dict or None if not found
        """
        for ds in self.data.get("data_sources", []):
            if ds.get("data_source_id") == data_source_id:
                return ds
        return None

    def save(self) -> None:
        """Save data to JSON file."""
        now = datetime.now(timezone.utc).isoformat()
        if self.data["created_at"] is None:
            self.data["created_at"] = now
        self.data["updated_at"] = now

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w') as f:
            json.dump(self.data, f, indent=2)

    def load(self) -> None:
        """Load data from JSON file."""
        if self.output_path.exists():
            with open(self.output_path, 'r') as f:
                self.data = json.load(f)

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "UnifiedPredictionTracker":
        """Create tracker from existing JSON file.

        Args:
            path: Path to existing predictions JSON

        Returns:
            UnifiedPredictionTracker with loaded data
        """
        tracker = cls(path)
        tracker.load()
        return tracker

    def __len__(self) -> int:
        """Return number of items."""
        return len(self.data["items"])

    def summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        items = self.data["items"]
        if not items:
            return {"total": 0}

        all_scores = []
        for item in items:
            for output in item.get("model_outputs", []):
                if "score" in output:
                    all_scores.append(output["score"])

        verified = sum(1 for item in items if item.get("verifications"))

        summary = {
            "total_items": len(items),
            "verified": verified,
            "unverified": len(items) - verified,
        }

        if all_scores:
            summary.update({
                "mean_score": sum(all_scores) / len(all_scores),
                "min_score": min(all_scores),
                "max_score": max(all_scores),
            })

        return summary
