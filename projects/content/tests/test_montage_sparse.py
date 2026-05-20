"""Тесты разрежённого плана монтажа и фолбэка motion_prompt.

Запуск из корня репозитория content: PYTHONPATH=. .venv/bin/python -m unittest tests.test_montage_sparse -v
"""
from __future__ import annotations

import unittest

from services.observability.dream_pipeline_lite import (
    lite_effective_prompt_mode,
    lite_build_prev_line_animation_markup,
    lite_collect_animate_i2v_segments,
    lite_frames_from_montage_form_metadata,
    lite_frames_metadata_for_montage_form,
    lite_first_frame_stored_image_url,
    lite_motion_prompt_for_prev_segment,
    lite_resolve_montage_preset,
    lite_sanitize_animation_markup_for_i2v,
    lite_sanitize_i2v_text_prompt,
    lite_transition_plan_with_selection,
    lite_transitions_wan26_system_prompt,
    lite_transitions_user_payload_dict,
    parse_lite_transition_plan_from_model_text,
)
from services.observability.dream_lite_run_worker import _normalize_provider_duration_sec
from services.observability.tools_dev import _map_video_job_status


class ParseSparseMontage(unittest.TestCase):
    def test_dense_legacy_unchanged_shape(self) -> None:
        raw = """
        {
          "scenes": [],
          "transitions": [
            {"from_frame_index": 0, "to_frame_index": 1, "transition_type": "animate_transition", "motion_prompt": "a"},
            {"from_frame_index": 1, "to_frame_index": 2, "transition_type": "hard_cut", "cut_reason": "x"}
          ]
        }
        """
        plan = parse_lite_transition_plan_from_model_text(raw, 3, fallback_on_error=False)
        self.assertEqual(plan.get("montage_mode"), "sparse")
        self.assertEqual(len(plan["transitions"]), 2)

    def test_sparse_chain_skips_middle_indices(self) -> None:
        raw = """
        {
          "scenes": [],
          "transitions": [
            {"from_frame_index": 0, "to_frame_index": 2, "transition_type": "animate_transition", "motion_prompt": "m1", "segment_mode": "pairwise"},
            {"from_frame_index": 2, "to_frame_index": 4, "transition_type": "animate_transition", "motion_prompt": "m2", "segment_mode": "pairwise"}
          ]
        }
        """
        plan = parse_lite_transition_plan_from_model_text(raw, 5, fallback_on_error=False)
        self.assertEqual(plan.get("montage_mode"), "sparse")
        self.assertEqual(len(plan["transitions"]), 2)
        self.assertEqual(plan["transitions"][0]["to_frame_index"], 2)

    def test_keyframes_builds_pairs(self) -> None:
        raw = """
        {
          "keyframes": [0, 2, 4],
          "scenes": [],
          "transitions": [
            {"from_frame_index": 0, "to_frame_index": 2, "transition_type": "animate_transition", "motion_prompt": "ab"},
            {"from_frame_index": 2, "to_frame_index": 4, "transition_type": "animate_transition", "motion_prompt": "bc"}
          ]
        }
        """
        plan = parse_lite_transition_plan_from_model_text(raw, 5, fallback_on_error=False)
        self.assertEqual(plan.get("montage_mode"), "sparse")
        self.assertEqual(plan.get("keyframes"), [0, 2, 4])
        self.assertEqual(len(plan.get("frame_selection") or []), 5)

    def test_seedance_transition_fields_are_preserved(self) -> None:
        raw = """
        {
          "keyframes": [0, 2],
          "transitions": [
            {
              "from_frame_index": 0,
              "to_frame_index": 2,
              "transition_type": "animate_transition",
              "motion_prompt": "bridge",
              "duration_sec": 7,
              "segment_story": "герой проходит путь",
              "voiceover_text": "Он идёт вперёд."
            }
          ]
        }
        """
        plan = parse_lite_transition_plan_from_model_text(raw, 3, fallback_on_error=False)
        tr = (plan.get("transitions") or [])[0]
        self.assertEqual(tr.get("duration_sec"), 7)
        self.assertIn("герой проходит путь", str(tr.get("segment_story") or ""))
        self.assertEqual(tr.get("voiceover_text"), "Он идёт вперёд.")
        self.assertTrue(bool(tr.get("phase_timing_text_present")))

    def test_seedance_transition_gets_phase_and_microact_fallback(self) -> None:
        raw = """
        {
          "keyframes": [0, 2],
          "transitions": [
            {
              "from_frame_index": 0,
              "to_frame_index": 2,
              "transition_type": "animate_transition",
              "motion_prompt": "bridge",
              "duration_sec": 7
            }
          ]
        }
        """
        plan = parse_lite_transition_plan_from_model_text(raw, 3, fallback_on_error=False)
        tr = (plan.get("transitions") or [])[0]
        self.assertIn("Ранняя фаза", str(tr.get("segment_story") or ""))
        self.assertTrue(bool(tr.get("phase_timing_text_present")))
        self.assertTrue(bool(tr.get("micro_act_contract_applied")))

    def test_frame_selection_normalization_adds_boundaries_and_reasons(self) -> None:
        raw = """
        {
          "transitions": [
            {"from_frame_index": 0, "to_frame_index": 2, "transition_type": "animate_transition", "motion_prompt": "m1"},
            {"from_frame_index": 2, "to_frame_index": 4, "transition_type": "animate_transition", "motion_prompt": "m2"}
          ],
          "frame_selection": [
            {"frame_index": 2, "selected": true, "reason": "новая фаза действия"}
          ]
        }
        """
        plan = parse_lite_transition_plan_from_model_text(raw, 5, fallback_on_error=False)
        self.assertEqual(plan.get("keyframes"), [0, 2, 4])
        sel = list(plan.get("frame_selection") or [])
        self.assertEqual(len(sel), 5)
        self.assertTrue(sel[0]["selected"])
        self.assertTrue(sel[4]["selected"])
        self.assertTrue(bool(sel[0]["reason"]))
        self.assertEqual(sel[2]["reason"], "новая фаза действия")

    def test_invalid_json_uses_fallback(self) -> None:
        plan = parse_lite_transition_plan_from_model_text("not json", 4, fallback_on_error=True)
        self.assertTrue(plan.get("_parse_fallback"))
        self.assertEqual(plan.get("montage_mode"), "sparse")
        self.assertEqual(len(plan["transitions"]), 3)


class CollectSegmentsStride(unittest.TestCase):
    def test_sparse_ignores_reference_stride(self) -> None:
        plan = {
            "montage_mode": "sparse",
            "transitions": [
                {
                    "from_frame_index": 0,
                    "to_frame_index": 2,
                    "transition_type": "animate_transition",
                    "motion_prompt": "x",
                    "segment_mode": "pairwise",
                }
            ],
        }
        frames = [
            {"index": 0, "ok": True, "urls": ["http://a/0.png"]},
            {"index": 1, "ok": True, "urls": ["http://a/1.png"]},
            {"index": 2, "ok": True, "urls": ["http://a/2.png"]},
        ]
        segs = lite_collect_animate_i2v_segments(
            plan,
            frames,
            prompt_mode="first_last_frame",
            scene_segment_stride=2,
            reference_frame_stride=2,
        )
        self.assertEqual(len(segs), 1)

    def test_builds_anchor_segments_when_intermediate_frames_have_no_image(self) -> None:
        plan = {
            "montage_mode": "sparse",
            "transitions": [
                {
                    "from_frame_index": 0,
                    "to_frame_index": 1,
                    "transition_type": "animate_transition",
                    "motion_prompt": "x",
                }
            ],
        }
        frames = [
            {"index": 0, "ok": True, "urls": ["http://a/0.png"], "image_generated_ok": True},
            {
                "index": 1,
                "ok": False,
                "urls": [],
                "image_generated_ok": False,
                "izmenenie": "межкадровый поворот",
            },
            {"index": 2, "ok": True, "urls": ["http://a/2.png"], "image_generated_ok": True},
        ]
        segs = lite_collect_animate_i2v_segments(
            plan,
            frames,
            prompt_mode="first_last_frame",
        )
        pairs = [(int(s["from_frame_index"]), int(s["to_frame_index"])) for s in segs]
        self.assertIn((0, 2), pairs)

    def test_segment_duration_story_voiceover_pass_through(self) -> None:
        plan = {
            "montage_mode": "sparse",
            "transitions": [
                {
                    "from_frame_index": 0,
                    "to_frame_index": 2,
                    "transition_type": "animate_transition",
                    "motion_prompt": "bridge",
                    "duration_sec": 7,
                    "segment_story": "story",
                    "voiceover_text": "voice",
                }
            ],
        }
        frames = [
            {"index": 0, "ok": True, "urls": ["http://a/0.png"]},
            {"index": 2, "ok": True, "urls": ["http://a/2.png"]},
        ]
        segs = lite_collect_animate_i2v_segments(plan, frames, prompt_mode="first_last_frame")
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0].get("duration_sec"), 7)
        self.assertIn("story", str(segs[0].get("segment_story") or ""))
        self.assertEqual(segs[0].get("voiceover_text"), "voice")
        self.assertTrue(bool(segs[0].get("final_prompt")))

    def test_locked_seedance_forces_first_frame_only_contract(self) -> None:
        plan = {
            "montage_mode": "sparse",
            "transitions": [
                {
                    "from_frame_index": 0,
                    "to_frame_index": 2,
                    "transition_type": "animate_transition",
                    "motion_prompt": "bridge",
                }
            ],
        }
        frames = [
            {"index": 0, "ok": True, "urls": ["http://a/0.png"]},
            {"index": 2, "ok": True, "urls": ["http://a/2.png"]},
        ]
        segs = lite_collect_animate_i2v_segments(
            plan,
            frames,
            prompt_mode="first_last_frame",
            montage_preset="seedance",
            audio_required=True,
        )
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0].get("prompt_mode"), "first_frame_only")
        self.assertEqual(segs[0].get("last_frame_url"), "")
        self.assertEqual(segs[0].get("effective_prompt_policy"), "locked_seedance_first_frame_only")


class MotionPromptTrim(unittest.TestCase):
    def test_fallback_short(self) -> None:
        dream = "x" * 500
        f0 = {"kad": "y" * 300, "ok": True, "urls": []}
        f1 = {"kad": "z" * 300, "izmenenie": "w" * 400, "ok": True, "urls": []}
        text, src = lite_motion_prompt_for_prev_segment(
            dream_text=dream,
            f0=f0,
            f1=f1,
            transition_plan=None,
            from_index=0,
            to_index=1,
        )
        self.assertEqual(src, "frame_text")
        self.assertNotIn("Эмоциональный тон", text)
        self.assertNotIn("Micro-act rule", text)

    def test_collect_segments_strips_service_contract_tail(self) -> None:
        plan = {
            "montage_mode": "sparse",
            "transitions": [
                {
                    "from_frame_index": 0,
                    "to_frame_index": 2,
                    "transition_type": "animate_transition",
                    "motion_prompt": (
                        "Ключевой сдвиг в сцене.\n"
                        "Early phase: setup and context without late-introduced elements. "
                        "Mid phase: action develops through intermediate beats, no jump cut to finale. "
                        "Late phase: payoff near target keyframe; late-introduced elements appear only here.\n"
                        "Micro-act rule: setup -> development -> payoff."
                    ),
                    "segment_story": "setup -> development -> payoff",
                }
            ],
        }
        frames = [
            {"index": 0, "ok": True, "urls": ["http://a/0.png"]},
            {"index": 1, "ok": True, "urls": ["http://a/1.png"], "izmenenie": "просит купить пиццу"},
            {"index": 2, "ok": True, "urls": ["http://a/2.png"]},
        ]
        segs = lite_collect_animate_i2v_segments(
            plan,
            frames,
            prompt_mode="first_frame_only",
            montage_preset="seedance",
            audio_required=True,
        )
        self.assertEqual(len(segs), 1)
        mp = str(segs[0].get("motion_prompt") or "")
        self.assertNotIn("Early phase:", mp)
        self.assertNotIn("Micro-act rule:", mp)
        self.assertNotIn("setup -> development -> payoff", mp)

    def test_collect_segments_adds_simple_dialog_hint_for_gap(self) -> None:
        plan = {
            "montage_mode": "sparse",
            "transitions": [
                {
                    "from_frame_index": 0,
                    "to_frame_index": 3,
                    "transition_type": "animate_transition",
                    "motion_prompt": "Переход в той же локации.",
                }
            ],
        }
        frames = [
            {"index": 0, "ok": True, "urls": ["http://a/0.png"]},
            {"index": 1, "ok": True, "urls": ["http://a/1.png"], "izmenenie": "мужчина просит купить пиццу"},
            {"index": 2, "ok": True, "urls": ["http://a/2.png"], "izmenenie": "обсуждение очереди, дети выбирают и оплачивают"},
            {"index": 3, "ok": True, "urls": ["http://a/3.png"]},
        ]
        segs = lite_collect_animate_i2v_segments(plan, frames, prompt_mode="first_frame_only")
        self.assertEqual(len(segs), 1)
        mp = str(segs[0].get("motion_prompt") or "")
        self.assertIn("Герои", mp)

    def test_sanitize_i2v_text_prompt_removes_service_lexicon(self) -> None:
        raw = (
            "Целевой keyframe: 4. Роль кадра: scene_start. "
            "Тип движения: наблюдение -> вовлечение. "
            "Путь по промежуточным кадрам: 1: child_1 смотрит. "
            "Cinematic still, зафиксированный момент. dreamer и close_man рядом."
        )
        clean = lite_sanitize_i2v_text_prompt(raw)
        low = clean.lower()
        self.assertNotIn("keyframe", low)
        self.assertNotIn("anchor", low)
        self.assertNotIn("segment_mode", low)
        self.assertNotIn("роль кадра", low)
        self.assertNotIn("тип движения", low)
        self.assertNotIn("путь по промежуточным кадрам", low)
        self.assertNotIn("cinematic still", low)
        self.assertNotIn("зафиксированный момент", low)
        self.assertNotIn("dreamer", low)
        self.assertNotIn("child_1", low)
        self.assertNotIn("close_man", low)
        self.assertIn("главный герой", low)
        self.assertIn("знакомый мужчина", low)


class MontageCoverageRules(unittest.TestCase):
    def test_environment_coverage_adaptive_by_count(self) -> None:
        plan = {
            "montage_mode": "dense",
            "transitions": [
                {"from_frame_index": 0, "to_frame_index": 1, "transition_type": "animate_transition", "motion_prompt": "a"},
                {"from_frame_index": 1, "to_frame_index": 2, "transition_type": "animate_transition", "motion_prompt": "b"},
                {"from_frame_index": 2, "to_frame_index": 3, "transition_type": "animate_transition", "motion_prompt": "c"},
                {"from_frame_index": 3, "to_frame_index": 4, "transition_type": "animate_transition", "motion_prompt": "d"},
            ],
            "keyframes": [0, 1, 2, 3, 4],
        }
        frames = [
            {"index": 0, "base_reference": "env_a"},
            {"index": 1, "base_reference": "env_a"},
            {"index": 2, "base_reference": "env_a"},
            {"index": 3, "base_reference": "env_b"},
            {"index": 4, "base_reference": "env_b"},
        ]
        out = lite_transition_plan_with_selection(plan, 5, generated_frames=frames)
        selected = [r["frame_index"] for r in out.get("frame_selection", []) if r.get("selected")]
        self.assertIn(0, selected)
        self.assertIn(2, selected)
        self.assertIn(3, selected)
        self.assertIn(4, selected)
        self.assertEqual(out.get("montage_mode"), "sparse")
        self.assertLess(len(out.get("transitions") or []), 5)


class AnimationMarkupFromKeyframes(unittest.TestCase):
    def test_builds_one_segment_per_keyframe_gap(self) -> None:
        plan = {
            "keyframes": [0, 2, 4],
            "transitions": [
                {"from_frame_index": 0, "to_frame_index": 2, "transition_type": "animate_transition", "motion_prompt": "a", "duration_sec": 7},
                {"from_frame_index": 2, "to_frame_index": 4, "transition_type": "animate_transition", "motion_prompt": "b", "duration_sec": 8},
            ],
        }
        frames = [
            {"index": 0, "title": "f0", "ok": True, "urls": ["http://a/0.png"]},
            {"index": 1, "title": "f1", "ok": False, "urls": []},
            {"index": 2, "title": "f2", "ok": True, "urls": ["http://a/2.png"]},
            {"index": 3, "title": "f3", "ok": False, "urls": []},
            {"index": 4, "title": "f4", "ok": True, "urls": ["http://a/4.png"]},
        ]
        markup = lite_build_prev_line_animation_markup(
            dream_text="story",
            generated_frames=frames,
            transition_plan=plan,
            prompt_mode="first_last_frame",
        )
        lines = list(markup.get("lines") or [])
        self.assertEqual(len(lines), 1)
        segs = list(lines[0].get("segments") or [])
        self.assertEqual(len(segs), 2)
        self.assertEqual((segs[0]["from_frame_index"], segs[0]["target_frame_index"]), (0, 2))
        self.assertEqual((segs[1]["from_frame_index"], segs[1]["target_frame_index"]), (2, 4))


class TransitionPayloadContract(unittest.TestCase):
    def test_payload_keeps_only_minimal_human_fields(self) -> None:
        payload = lite_transitions_user_payload_dict(
            dream_text="story",
            env_cards=[],
            char_cards=[],
            generated_frames=[
                {
                    "index": 0,
                    "title": "Кадр 1",
                    "img_prompt": "Dreamer runs through rain",
                    "kad": "погоня",
                    "izmenenie": "ускорение",
                    "ok": True,
                    "urls": ["data:image/png;base64,AAAABBBBCCCC"],
                    "image_id": "frame_000",
                    "generation_status": "generated",
                    "use_previous_frame_resolved": True,
                    "forced_prev_chain_break": False,
                }
            ],
        )
        frames = list(payload.get("frames") or [])
        self.assertEqual(len(frames), 1)
        row = frames[0]
        self.assertEqual(set(payload.keys()), {"dream_text", "frames"})
        self.assertEqual(set(row.keys()), {"index", "is_keyframe", "description", "change"})
        self.assertEqual(row.get("description"), "погоня")
        self.assertEqual(row.get("change"), "ускорение")
        self.assertNotIn("image_url", row)
        self.assertNotIn("image_id", row)
        self.assertNotIn("generation_status", row)

    def test_payload_for_keyframe_has_image_url_and_humanized_names(self) -> None:
        payload = lite_transitions_user_payload_dict(
            dream_text="story",
            env_cards=[],
            char_cards=[],
            generated_frames=[
                {
                    "index": 0,
                    "is_keyframe": True,
                    "ok": True,
                    "urls": ["/dev/static/frame0.png"],
                    "kad": "dreamer стоит рядом с child_1",
                    "izmenenie": "close_man подходит, child_2 машет рукой",
                },
                {
                    "index": 1,
                    "is_keyframe": False,
                    "ok": False,
                    "urls": [],
                    "kad": "child_1 смотрит на стол",
                    "izmenenie": "dreamer отвечает",
                },
            ],
        )
        frames = list(payload.get("frames") or [])
        self.assertEqual(frames[0].get("image_url"), "/dev/static/frame0.png")
        self.assertNotIn("image_url", frames[1])
        txt = f"{frames[0].get('description','')} {frames[0].get('change','')} {frames[1].get('description','')} {frames[1].get('change','')}".lower()
        self.assertNotIn("dreamer", txt)
        self.assertNotIn("child_1", txt)
        self.assertNotIn("child_2", txt)
        self.assertNotIn("close_man", txt)
        self.assertIn("главный герой", txt)
        self.assertIn("дети", txt)
        self.assertIn("знакомый мужчина", txt)


class Step4MetadataRoundtrip(unittest.TestCase):
    def test_roundtrip_keeps_image_href_and_runtime_ok(self) -> None:
        rows = lite_frames_metadata_for_montage_form(
            [
                {
                    "index": 0,
                    "ok": False,
                    "image_generated_ok": True,
                    "urls": ["/dev/static/dream_lite/frame.png"],
                    "title": "frame0",
                }
            ]
        )
        self.assertTrue(bool(rows and rows[0].get("image_href")))
        self.assertTrue(bool(rows[0].get("ok")))
        restored = lite_frames_from_montage_form_metadata(rows)
        self.assertTrue(bool(restored and restored[0].get("image_href")))
        self.assertEqual(
            lite_first_frame_stored_image_url(restored[0]),
            "/dev/static/dream_lite/frame.png",
        )


class EffectivePromptModePolicy(unittest.TestCase):
    def test_seedance_audio_locked_forces_first_frame_only(self) -> None:
        pm, policy, locked = lite_effective_prompt_mode(
            prompt_mode="first_last_frame",
            montage_preset="seedance",
            audio_required=True,
        )
        self.assertEqual(pm, "first_frame_only")
        self.assertEqual(policy, "locked_seedance_first_frame_only")
        self.assertTrue(locked)

    def test_wan_single_anchor_forces_first_frame_only(self) -> None:
        pm, policy, locked = lite_effective_prompt_mode(
            prompt_mode="first_last_frame",
            montage_preset="wan_2_6_single_anchor",
            audio_required=False,
        )
        self.assertEqual(pm, "first_frame_only")
        self.assertEqual(policy, "locked_wan_single_anchor")
        self.assertTrue(locked)

    def test_kling_reference_forces_first_frame_only(self) -> None:
        pm, policy, locked = lite_effective_prompt_mode(
            prompt_mode="first_last_frame",
            montage_preset="kling_v3_reference_motion",
            audio_required=False,
        )
        self.assertEqual(pm, "first_frame_only")
        self.assertEqual(policy, "locked_kling_reference_motion")
        self.assertTrue(locked)


class MontagePresetResolve(unittest.TestCase):
    def test_resolve_kling_from_model_id(self) -> None:
        preset = lite_resolve_montage_preset(
            selected_video_model="kwaivgi/kling-v3.0-std",
            configured_preset="",
        )
        self.assertEqual(preset, "kling_v3_reference_motion")


class WanSingleAnchorSegments(unittest.TestCase):
    def test_collect_segments_builds_one_per_keyframe(self) -> None:
        plan = {
            "keyframes": [0, 2, 4],
            "transitions": [
                {"from_frame_index": 0, "to_frame_index": 2, "transition_type": "animate_transition", "motion_prompt": "до второго keyframe"},
                {"from_frame_index": 2, "to_frame_index": 4, "transition_type": "animate_transition", "motion_prompt": "после второго keyframe"},
            ],
        }
        frames = [
            {"index": 0, "ok": True, "urls": ["http://a/0.png"], "is_keyframe": True, "kad": "dreamer стартует на ярмарке"},
            {"index": 1, "ok": False, "urls": [], "izmenenie": "child_1 и child_2 обсуждают покупку"},
            {"index": 2, "ok": True, "urls": ["http://a/2.png"], "is_keyframe": True, "kad": "close_man просит пиццу"},
            {"index": 3, "ok": False, "urls": [], "izmenenie": "оплата и ожидание заказа"},
            {"index": 4, "ok": True, "urls": ["http://a/4.png"], "is_keyframe": True, "kad": "появление вертолёта"},
        ]
        segs = lite_collect_animate_i2v_segments(
            plan,
            frames,
            prompt_mode="first_last_frame",
            montage_preset="wan_2_6_single_anchor",
        )
        self.assertEqual(len(segs), 3)
        self.assertEqual(segs[0].get("from_frame_index"), 0)
        self.assertEqual(segs[1].get("from_frame_index"), 2)
        self.assertEqual(segs[2].get("from_frame_index"), 4)
        self.assertEqual(segs[0].get("anchor_role"), "scene_start")
        self.assertTrue(bool(segs[0].get("is_scene_start")))
        self.assertEqual(segs[1].get("anchor_role"), "central_moment")
        self.assertEqual(segs[1].get("segment_mode"), "single_anchor")
        self.assertEqual(segs[1].get("last_frame_url"), "")
        mp0 = str(segs[0].get("motion_prompt") or "")
        self.assertIn("Камера", mp0)
        self.assertTrue(bool(segs[0].get("final_prompt")))
        self.assertNotIn("Целевой keyframe", mp0)
        self.assertNotIn("Роль кадра", mp0)
        self.assertNotIn("Тип движения", mp0)
        self.assertNotIn("Путь по промежуточным кадрам", mp0)
        self.assertNotIn("anchor", mp0.lower())
        self.assertNotIn("keyframe", mp0.lower())
        self.assertNotIn("dreamer", mp0.lower())
        self.assertNotIn("child_1", mp0.lower())
        self.assertNotIn("child_2", mp0.lower())
        self.assertNotIn("close_man", mp0.lower())
        self.assertNotIn("1:", mp0)
        self.assertNotIn("2:", mp0)
        self.assertNotIn("сквозное развитие", mp0.lower())
        self.assertNotIn("этап", mp0.lower())
        self.assertNotIn("шаг", mp0.lower())
        self.assertEqual(int(segs[0].get("target_keyframe") or 0), 2)
        self.assertNotIn("1:", str(segs[0].get("gap_path_summary") or ""))
        self.assertGreaterEqual(int(segs[0].get("duration_sec") or 0), 3)
        self.assertLessEqual(int(segs[0].get("duration_sec") or 0), 10)

    def test_markup_exposes_anchor_fields(self) -> None:
        plan = {
            "keyframes": [0, 2],
            "transitions": [
                {"from_frame_index": 0, "to_frame_index": 2, "transition_type": "animate_transition", "motion_prompt": "контекст"},
            ],
        }
        frames = [
            {"index": 0, "ok": True, "urls": ["http://a/0.png"], "is_keyframe": True, "kad": "старт"},
            {"index": 1, "ok": False, "urls": [], "izmenenie": "движение к anchor"},
            {"index": 2, "ok": True, "urls": ["http://a/2.png"], "is_keyframe": True, "kad": "anchor"},
        ]
        markup = lite_build_prev_line_animation_markup(
            dream_text="story",
            generated_frames=frames,
            transition_plan=plan,
            prompt_mode="first_last_frame",
            montage_preset="wan_2_6_single_anchor",
        )
        segs = list((markup.get("lines") or [{}])[0].get("segments") or [])
        self.assertEqual(len(segs), 2)
        self.assertTrue("anchor_role" in segs[0])
        self.assertTrue("post_anchor_beats" in segs[0])
        self.assertIn("Камера", str(segs[0].get("motion_prompt_suggested") or ""))
        self.assertTrue(bool((segs[0].get("api_payload_preview") or {}).get("prompt")))
        self.assertNotIn(
            "image_prompt",
            str((segs[0].get("api_payload_preview") or {}).get("prompt") or "").lower(),
        )
        self.assertEqual(
            sorted((segs[0].get("api_payload_preview") or {}).keys()),
            ["duration_sec", "image_url", "prompt"],
        )
        self.assertEqual(int(segs[0].get("target_frame_index") or 0), 2)

    def test_markup_sanitizer_rewrites_old_prompt_payload(self) -> None:
        markup = {
            "lines": [
                {
                    "line_index": 0,
                    "segments": [
                        {
                            "segment_index": 0,
                            "motion_prompt_suggested": "Целевой keyframe: 3. dreamer ждёт. cinematic still.",
                            "api_payload_preview": {"prompt": "Роль кадра: scene_start. child_1 в кадре."},
                        }
                    ],
                }
            ]
        }
        out = lite_sanitize_animation_markup_for_i2v(markup)
        seg = (((out.get("lines") or [{}])[0]).get("segments") or [{}])[0]
        prompt = str(((seg.get("api_payload_preview") or {}).get("prompt") or ""))
        self.assertNotIn("keyframe", prompt.lower())
        self.assertNotIn("роль кадра", prompt.lower())
        self.assertNotIn("dreamer", prompt.lower())
        self.assertNotIn("child_1", prompt.lower())


class TransitionDurationRules(unittest.TestCase):
    def test_missing_duration_is_filled_with_default(self) -> None:
        raw = """
        {
          "transitions": [
            {"from_frame_index": 0, "to_frame_index": 1, "transition_type": "animate_transition", "motion_prompt": "x"}
          ]
        }
        """
        plan = parse_lite_transition_plan_from_model_text(raw, 2, fallback_on_error=False)
        tr = (plan.get("transitions") or [])[0]
        self.assertEqual(int(tr.get("duration_sec") or 0), 5)

    def test_duration_clamped_to_15(self) -> None:
        raw = """
        {
          "transitions": [
            {"from_frame_index": 0, "to_frame_index": 1, "transition_type": "animate_transition", "motion_prompt": "x", "duration_sec": 99}
          ]
        }
        """
        plan = parse_lite_transition_plan_from_model_text(raw, 2, fallback_on_error=False)
        tr = (plan.get("transitions") or [])[0]
        self.assertEqual(int(tr.get("duration_sec") or 0), 15)


class WanPromptSource(unittest.TestCase):
    def test_wan_prompt_fallback_is_defined(self) -> None:
        text = lite_transitions_wan26_system_prompt()
        self.assertIn("wan_2_6_single_anchor", text)
        self.assertIn("Первый keyframe", text)


class TestWan26ProviderDurationPolicy(unittest.TestCase):
    def test_openrouter_wan26_forces_five_seconds(self) -> None:
        self.assertEqual(
            _normalize_provider_duration_sec(
                2,
                backend="openrouter",
                openrouter_model="alibaba/wan-2.6",
                supported_durations=[5, 10],
            ),
            5,
        )
        self.assertEqual(
            _normalize_provider_duration_sec(
                9,
                backend="openrouter",
                openrouter_model="alibaba/wan-2.6",
                supported_durations=[5, 10],
            ),
            5,
        )


class TestStaleTimeoutStatusMapping(unittest.TestCase):
    def test_stale_timeout_is_terminal_failed_status(self) -> None:
        ui_status, display = _map_video_job_status("stale_timeout")
        self.assertEqual(ui_status, "failed")
        self.assertEqual(display, "stale_timeout")


if __name__ == "__main__":
    unittest.main()
