from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

_MOD_PATH = (
    Path(__file__).resolve().parent.parent
    / "services"
    / "observability"
    / "dream_pipeline_lite.py"
)
_SPEC = importlib.util.spec_from_file_location("dream_pipeline_lite_testmod", _MOD_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Не удалось загрузить dream_pipeline_lite.py для теста simple_mode_v2")
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)

build_lite_frame_image_prompt = _MOD.build_lite_frame_image_prompt
collect_lite_frame_reference_urls = _MOD.collect_lite_frame_reference_urls
lite_environments_system_prompt = _MOD.lite_environments_system_prompt
lite_ref_slots_canonical_for_ui = _MOD.lite_ref_slots_canonical_for_ui
lite_resolve_use_previous_frame = _MOD.lite_resolve_use_previous_frame
parse_lite_frames_prev_link_response = _MOD.parse_lite_frames_prev_link_response


class SimpleModeV2(unittest.TestCase):
    def test_simple_mode_refs_ignore_previous_even_when_requested(self) -> None:
        card = {
            "title": "Кадр 2",
            "base_reference": "city_night",
            "character_references": ["dreamer_main"],
            "opora": "Ночной город, мокрый асфальт",
            "izmenenie": "герой идет вперед",
            "kad": "Полуобщий план героя в пустой улице",
        }
        refs, note, bundle, slots = collect_lite_frame_reference_urls(
            1,
            card,
            {"city_night": "https://example.com/env.png"},
            ["city_night"],
            {"dreamer_main": "https://example.com/dreamer.png"},
            ["dreamer_main"],
            "https://example.com/previous.png",
            use_previous_for_refs=True,
            prev_frame_title="Кадр 1",
            simple_mode=True,
        )
        self.assertEqual(bundle, "simple_dreamer_env_only")
        self.assertEqual(refs, ["https://example.com/env.png", "https://example.com/dreamer.png"])
        self.assertNotIn("previous", note.lower())
        self.assertEqual([s.get("role") for s in slots], ["environment", "dreamer"])

    def test_simple_mode_canonical_always_marks_previous_not_in_api(self) -> None:
        raw_slots = [
            {
                "order": 1,
                "role": "environment",
                "label": "Окружение (simple mode)",
                "detail": "night_city",
                "url": "https://example.com/env.png",
                "pending": False,
            },
            {
                "order": 2,
                "role": "dreamer",
                "label": "Главный персонаж (Dreamer)",
                "detail": "dreamer_main",
                "url": "https://example.com/dreamer.png",
                "pending": False,
            },
        ]
        canonical = lite_ref_slots_canonical_for_ui(
            1,
            True,
            False,
            raw_slots,
            "simple_dreamer_env_only",
        )
        self.assertEqual(canonical[0].get("role"), "previous_frame_skip")
        self.assertFalse(bool(canonical[0].get("in_api")))
        api_roles = [s.get("role") for s in canonical if s.get("in_api")]
        self.assertEqual(api_roles, ["environment", "character"])

    def test_simple_mode_prompt_is_self_contained(self) -> None:
        prompt = build_lite_frame_image_prompt(
            "Крупный план лица, капли дождя на коже",
            "Легкая улыбка и поворот головы",
            use_previous_for_refs=True,
            simple_mode=True,
            environment_label="ночная улица, неон, мокрый асфальт",
            dreamer_label="dreamer_main",
        )
        self.assertIn("Окружение:", prompt)
        self.assertIn("Главный персонаж:", prompt)
        self.assertNotIn("Измени предыдущий кадр", prompt)
        self.assertIn("cinematic still", prompt.lower())
        self.assertIn("Композиция:", prompt)
        self.assertIn("Анти-статичность:", prompt)
        self.assertIn("зафиксирован", prompt.lower())
        self.assertIn("No text", prompt)
        self.assertIn("no speech bubbles", prompt.lower())

    def test_simple_mode_prev_chain_is_limited_to_pair(self) -> None:
        card2 = {"use_previous_frame": True}
        prior = [{"use_previous_frame_resolved": False}]
        up2, forced2 = lite_resolve_use_previous_frame(
            card2,
            1,
            prior_frame_entries=prior,
            simple_mode=True,
        )
        self.assertTrue(up2)
        self.assertFalse(forced2)
        self.assertEqual(card2.get("prev_pair_state"), "open")

        card3 = {"use_previous_frame": True}
        prior2 = [{"use_previous_frame_resolved": False}, {"use_previous_frame_resolved": True}]
        up3, forced3 = lite_resolve_use_previous_frame(
            card3,
            2,
            prior_frame_entries=prior2,
            simple_mode=True,
        )
        self.assertFalse(up3)
        self.assertTrue(forced3)
        self.assertEqual(card3.get("prev_pair_state"), "closed")

    def test_simple_mode_environment_prompt_has_no_living_beings_rule(self) -> None:
        prompt = lite_environments_system_prompt(simple_mode=True).lower()
        self.assertTrue(("без живых существ" in prompt) or ("no living beings" in prompt))

    def test_simple_mode_refs_do_not_fallback_to_non_dreamer(self) -> None:
        card = {
            "title": "Кадр 3",
            "base_reference": "city_night",
            "character_references": ["sidekick"],
            "opora": "Тёмная улица",
            "izmenenie": "Фигура вдалеке",
            "kad": "Сцена без явного dreamer",
        }
        refs, _, bundle, slots = collect_lite_frame_reference_urls(
            2,
            card,
            {"city_night": "https://example.com/env.png"},
            ["city_night"],
            {"sidekick": "https://example.com/sidekick.png"},
            ["sidekick"],
            None,
            use_previous_for_refs=False,
            simple_mode=True,
        )
        self.assertEqual(bundle, "simple_dreamer_env_only")
        self.assertEqual(refs, ["https://example.com/env.png"])
        self.assertEqual([s.get("role") for s in slots], ["environment"])

    def test_prev_classifier_parses_keyframe_flags(self) -> None:
        raw = """
        {
          "use_previous_frame_by_index": [false, true, false],
          "keyframe_by_index": [true, false, true],
          "keyframe_reason_by_index": ["старт", "", "поворот"]
        }
        """
        prev, key, reason = parse_lite_frames_prev_link_response(raw, n_frames=3)
        self.assertEqual(prev, [False, True, False])
        self.assertEqual(key, [True, False, True])
        self.assertEqual(reason[0], "старт")
        self.assertEqual(reason[2], "поворот")

    def test_prev_classifier_normalizes_all_non_key(self) -> None:
        raw = """
        {
          "use_previous_frame_by_index": [false, true, false, false],
          "keyframe_by_index": [false, false, false, false],
          "keyframe_reason_by_index": ["", "", "", ""]
        }
        """
        _, key, reason = parse_lite_frames_prev_link_response(raw, n_frames=4)
        self.assertTrue(key[0])
        self.assertTrue(key[-1])
        self.assertGreaterEqual(sum(1 for x in key if x), 2)
        self.assertTrue(bool(reason[0]))


if __name__ == "__main__":
    unittest.main()
