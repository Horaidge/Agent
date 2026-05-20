from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from services.dreams.dream_lite_service import video_policy_bundle_for_montage_preset
from services.observability.dream_pipeline_lite import (
    lite_build_prev_line_animation_markup,
    lite_effective_prompt_mode,
)
from services.video.openrouter_video_client import OpenRouterVideoError
from services.video.video_job_service import VideoJobService, _validate_reference_image_url


class _FakeRepo:
    def __init__(self) -> None:
        self.patches: list[tuple[str, dict]] = []

    def update_job_sync(self, job_id: str, patch: dict) -> None:
        self.patches.append((job_id, dict(patch)))


class KlingPresetPolicyTests(unittest.TestCase):
    def test_bundle_for_kling_reference_preset(self) -> None:
        bundle = video_policy_bundle_for_montage_preset("kling_v3_reference_motion")
        self.assertEqual(bundle.get("montage_preset"), "kling_v3_reference_motion")
        self.assertEqual(int(bundle.get("duration_sec") or 0), 5)
        self.assertEqual(str(bundle.get("resolution") or ""), "720x720")

    def test_effective_prompt_mode_locked_for_kling_reference(self) -> None:
        pm, policy, locked = lite_effective_prompt_mode(
            prompt_mode="first_last_frame",
            montage_preset="kling_v3_reference_motion",
            audio_required=False,
        )
        self.assertEqual(pm, "first_frame_only")
        self.assertEqual(policy, "locked_kling_reference_motion")
        self.assertTrue(locked)

    def test_markup_payload_uses_reference_contract(self) -> None:
        markup = lite_build_prev_line_animation_markup(
            dream_text="сон",
            generated_frames=[
                {"index": 0, "ok": True, "urls": ["https://img/0.jpg"], "is_keyframe": True, "kad": "старт"},
                {"index": 1, "ok": True, "urls": ["https://img/1.jpg"], "is_keyframe": True, "kad": "момент"},
            ],
            transition_plan={
                "keyframes": [0, 1],
                "transitions": [
                    {
                        "from_frame_index": 0,
                        "to_frame_index": 1,
                        "transition_type": "animate_transition",
                        "motion_prompt": "движение",
                    }
                ],
            },
            prompt_mode="first_last_frame",
            montage_preset="kling_v3_reference_motion",
        )
        seg = (((markup.get("lines") or [{}])[0]).get("segments") or [{}])[0]
        payload = dict(seg.get("api_payload_preview") or {})
        self.assertEqual(payload.get("size"), "720x720")
        self.assertEqual(int(payload.get("duration_sec") or 0), 5)
        self.assertTrue(str(payload.get("reference_image_url") or "").startswith("https://"))
        self.assertTrue(bool(payload.get("input_references")))

    def test_kling_segments_keep_all_runtime_keyframes(self) -> None:
        markup = lite_build_prev_line_animation_markup(
            dream_text="сон",
            generated_frames=[
                {"index": 0, "ok": True, "urls": ["https://img/0.jpg"], "is_keyframe": True, "kad": "кадр 0"},
                {"index": 1, "ok": True, "urls": ["https://img/1.jpg"], "is_keyframe": True, "kad": "кадр 1"},
                {"index": 2, "ok": True, "urls": ["https://img/2.jpg"], "is_keyframe": True, "kad": "кадр 2"},
            ],
            transition_plan={
                "keyframes": [0],
                "transitions": [
                    {
                        "from_frame_index": 0,
                        "to_frame_index": 1,
                        "transition_type": "animate_transition",
                        "motion_prompt": "движение",
                    }
                ],
            },
            prompt_mode="first_last_frame",
            montage_preset="kling_v3_reference_motion",
        )
        segs = list((markup.get("lines") or [{}])[0].get("segments") or [])
        self.assertGreaterEqual(len(segs), 3)


class KlingReferenceRuntimeTests(unittest.TestCase):
    def test_reference_url_validation_rejects_non_https(self) -> None:
        ok, err = _validate_reference_image_url("http://example.com/a.jpg", relaxed=False)
        self.assertFalse(ok)
        self.assertEqual(err, "reference_image_must_be_public_https")

    def test_openrouter_fallback_to_frame_images_on_4xx(self) -> None:
        repo = _FakeRepo()
        settings = SimpleNamespace(
            openrouter_video_provider_json="",
            openrouter_video_model="kwaivgi/kling-v3.0-std",
            public_base_url="https://example.org",
            dashscope_video_endpoint="",
            video_generation_backend="openrouter",
        )
        svc = VideoJobService(repo, settings)  # type: ignore[arg-type]
        calls: list[dict] = []

        def _submit(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise OpenRouterVideoError("HTTP 400: unsupported input_references")
            return "job-or-id", "https://openrouter.ai/api/v1/videos/job-or-id", {"id": "job-or-id"}

        with (
            patch("services.video.video_job_service._resolve_image_url_for_provider", return_value="https://cdn/img.jpg"),
            patch("services.video.video_job_service._validate_reference_image_url", return_value=(True, "")),
            patch("services.video.video_job_service.submit_openrouter_video_job", side_effect=_submit),
            patch("services.video.video_job_service.threading.Thread") as thread_mock,
        ):
            thread_mock.return_value.start.return_value = None
            out = svc._start_openrouter_job(
                "job-1",
                prompt="prompt",
                image_url="https://cdn/img.jpg",
                last_frame_url=None,
                duration=7,
                resolution="720x720",
                openrouter_model="kwaivgi/kling-v3.0-std",
                openrouter_provider=None,
                montage_preset="kling_v3_reference_motion",
                dev_relaxed_validation=False,
            )

        self.assertEqual(out, "job-1")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].get("first_frame_url"), None)
        self.assertEqual(calls[0].get("input_references"), ["https://cdn/img.jpg"])
        self.assertEqual(calls[1].get("first_frame_url"), "https://cdn/img.jpg")
        self.assertEqual(calls[1].get("input_references"), None)


if __name__ == "__main__":
    unittest.main()
