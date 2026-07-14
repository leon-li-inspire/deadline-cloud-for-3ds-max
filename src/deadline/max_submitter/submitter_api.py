# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from pymxs import runtime as rt  # type: ignore[import]

from deadline.client.job_bundle.submission import AssetReferences
from deadline.client.submitter_api import SubmitterAPI, SubmitterSettings

from .data_classes import RenderSubmitterUISettings, StateSetData


@dataclass
class MaxSubmitterSettings(SubmitterSettings):
    """3ds Max-specific submission settings."""

    renderer: str = ""
    camera_selection: str = ""
    state_sets: list[str] = field(default_factory=list)
    image_width: int = 0
    image_height: int = 0
    output_file_name: str = ""
    output_file_format: str = ""
    description: str = ""


class MaxSubmitterAPI(SubmitterAPI):
    """SubmitterAPI implementation for 3ds Max submissions."""

    def get_settings(self) -> MaxSubmitterSettings:
        settings = MaxSubmitterSettings()
        settings.name = rt.maxFileName or "Untitled"
        settings.project_path = rt.maxFilePath or ""
        settings.input_filenames = (
            [str(Path(rt.maxFilePath) / rt.maxFileName)] if rt.maxFileName else []
        )

        anim_range = rt.animationRange
        start_frame = int(anim_range.start)
        end_frame = int(anim_range.end)
        settings.frame_list = f"{start_frame}-{end_frame}"

        settings.renderer = str(rt.renderers.current.classof) if rt.renderers.current else ""

        render_width = rt.renderWidth
        render_height = rt.renderHeight
        settings.image_width = int(render_width) if render_width else 0
        settings.image_height = int(render_height) if render_height else 0

        output_path = rt.rendOutputFilename or ""
        if output_path:
            settings.output_path = str(Path(output_path).parent)
            settings.output_file_name = Path(output_path).stem
            settings.output_file_format = Path(output_path).suffix
            settings.output_directories = [settings.output_path]

        return settings

    def get_job_template(
        self,
        settings: SubmitterSettings,
        host_requirements: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        from .create_job_bundle import get_job_template

        native_settings = self._to_native_settings(settings)
        state_sets = self._get_state_sets(settings)
        cameras = self._get_cameras()

        with open(Path(__file__).parent / "default_max_job_template.yaml") as fh:
            default_job_template = yaml.safe_load(fh)

        job_template = get_job_template(default_job_template, native_settings, state_sets, cameras)

        if host_requirements:
            for step in job_template.get("steps", []):
                step["hostRequirements"] = host_requirements

        return job_template

    def get_parameter_values(
        self,
        settings: SubmitterSettings,
        queue_parameters: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        from .create_job_bundle import get_parameters_values

        native_settings = self._to_native_settings(settings)
        state_sets = self._get_state_sets(settings)

        return get_parameters_values(native_settings, state_sets, queue_parameters)

    def get_asset_references(self, settings: SubmitterSettings) -> dict[str, Any]:
        scene_file = str(Path(rt.maxFilePath) / rt.maxFileName) if rt.maxFileName else ""

        asset_refs = AssetReferences(
            input_filenames={scene_file} if scene_file else set(),
            input_directories=set(settings.input_directories),
            output_directories=set(settings.output_directories),
        )
        return asset_refs.to_dict()

    def _to_native_settings(self, settings: SubmitterSettings):
        native = RenderSubmitterUISettings()
        native.name = settings.name
        native.priority = settings.priority
        native.initial_status = settings.initial_status
        native.max_failed_tasks_count = settings.max_failed_tasks_count
        native.max_retries_per_task = settings.max_retries_per_task

        # Carry over the common SubmitterSettings so they reach the job template
        # and parameter values. Without this, project/output paths come through
        # empty and the frame range falls back to defaults.
        native.frame_list = settings.frame_list or native.frame_list
        native.project_path = settings.project_path or native.project_path
        native.output_path = settings.output_path or native.output_path
        native.input_filenames = settings.input_filenames or native.input_filenames
        native.input_directories = settings.input_directories or native.input_directories
        native.output_directories = settings.output_directories or native.output_directories

        # The batch-render parameter builder only honours frame_list when the
        # override flag is set; otherwise it reads the scene's frame range.
        # Respect an explicit frame_list by enabling the override.
        native.override_frame_range = settings.override_frame_range or bool(settings.frame_list)

        if isinstance(settings, MaxSubmitterSettings):
            native.description = settings.description
            # Renderer is required by the adaptor schema and is written verbatim
            # into the step init-data. Without this it stays empty and the render
            # fails. get_settings() populates it from the active scene renderer.
            native.renderer = settings.renderer or native.renderer
            # Only override the camera selection when a specific camera was chosen.
            # An empty value must NOT be propagated: the native default is
            # ALL_CAMERAS_STR, and the job template only adds a "Camera" parameter
            # when camera_selection != ALL_CAMERAS_STR. Copying "" would emit a
            # Camera parameter whose value is outside the template's allowedValues
            # and the CreateJob call fails with a ValidationException.
            if settings.camera_selection:
                native.camera_selection = settings.camera_selection

        return native

    def _get_state_sets(self, settings: SubmitterSettings):
        anim_range = rt.animationRange
        frame_range = f"{int(anim_range.start)}-{int(anim_range.end)}"
        output_path = rt.rendOutputFilename or ""

        return [
            StateSetData(
                state_set="Default",
                renderer=str(rt.renderers.current.classof) if rt.renderers.current else "",
                frame_range=settings.frame_list or frame_range,
                output_directories={str(Path(output_path).parent)} if output_path else set(),
                output_file_dir=str(Path(output_path).parent) if output_path else "",
                output_file_name=Path(output_path).stem if output_path else "",
                output_file_format=Path(output_path).suffix if output_path else "",
                image_resolution=(
                    int(rt.renderWidth or 0),
                    int(rt.renderHeight or 0),
                ),
                ui_group_label=None,
            )
        ]

    def _get_cameras(self):
        cameras = []
        for obj in rt.cameras:
            cameras.append(str(obj.name))
        return cameras
