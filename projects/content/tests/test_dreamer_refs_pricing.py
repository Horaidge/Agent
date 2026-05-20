from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.images.openrouter_image_models_catalog import (
    OPENROUTER_IMAGE_MODELS_CATALOG,
    catalog_models_for_template,
    openrouter_model_supports_reference_images,
)
from services.observability import dream_pipeline_lite as lite_mod
from services.tools.openrouter_image_tools import tool_generate_image_openrouter


class DreamerOnlySimpleModeTests(unittest.TestCase):
    def test_run_lite_env_char_visual_chain_skips_non_dreamer_in_simple_mode(self) -> None:
        env_text = (
            "## Окружения\n"
            "### snowy_tunnel\n"
            "Снежный тоннель.\n\n"
            "## Персонажи\n"
            "### dreamer\n"
            "Главный персонаж.\n\n"
            "### sidekick\n"
            "Второстепенный персонаж.\n"
        )

        def _fake_tool(*args, **kwargs):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                to_dict=lambda: {
                    "ok": True,
                    "image_urls": ["https://example.com/out.png"],
                    "error": None,
                    "model": kwargs.get("model") or "google/gemini-2.5-flash-image",
                }
            )

        with patch.object(lite_mod, "tool_generate_image_openrouter", side_effect=_fake_tool):
            _env_results, char_results, _u_env, _u_char, _env_order, _char_order = lite_mod.run_lite_env_char_visual_chain(
                environments_text=env_text,
                image_model="bytedance-seed/seedream-4.5",
                simple_mode=True,
            )

        self.assertEqual(len(char_results), 2)
        self.assertTrue(char_results[0].get("ok"))
        self.assertEqual(char_results[0].get("generation_status"), None)
        self.assertEqual(char_results[1].get("generation_status"), "skipped_simple_mode_non_dreamer")
        self.assertEqual(char_results[1].get("skip_reason"), "simple_mode_dreamer_only_policy")


class ImageRefsContractTests(unittest.TestCase):
    def test_seedream_strict_model_does_not_fallback_and_keeps_refs(self) -> None:
        captured: dict[str, object] = {}

        def _fake_settings():  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                openrouter_image_model="google/gemini-2.5-flash-image",
                openrouter_image_model_fallback="openai/gpt-5-image-mini",
            )

        def _fake_generate(**kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return ["https://example.com/image.png"], {"total_tokens": 123}

        with (
            patch("services.tools.openrouter_image_tools.get_settings", side_effect=_fake_settings),
            patch(
                "services.tools.openrouter_image_tools.generate_image_urls_via_openrouter_with_usage",
                side_effect=_fake_generate,
            ),
        ):
            res = tool_generate_image_openrouter(
                "prompt",
                model="bytedance-seed/seedream-4.5",
                reference_image_urls=["https://example.com/ref1.png", "https://example.com/ref2.png"],
                strict_model=True,
            ).to_dict()

        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("model"), "bytedance-seed/seedream-4.5")
        self.assertEqual(res.get("models_tried"), ["bytedance-seed/seedream-4.5"])
        self.assertEqual(captured.get("model"), "bytedance-seed/seedream-4.5")
        self.assertEqual(
            captured.get("reference_image_urls"),
            ["https://example.com/ref1.png", "https://example.com/ref2.png"],
        )

    def test_model_without_refs_is_blocked_when_refs_passed(self) -> None:
        def _fake_settings():  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                openrouter_image_model="google/gemini-2.5-flash-image",
                openrouter_image_model_fallback="openai/gpt-5-image-mini",
            )

        with patch("services.tools.openrouter_image_tools.get_settings", side_effect=_fake_settings):
            res = tool_generate_image_openrouter(
                "prompt",
                model="qwen/qwen-image",
                reference_image_urls=["https://example.com/ref1.png"],
                strict_model=True,
            ).to_dict()
        self.assertFalse(res.get("ok"))
        self.assertIn("не поддерживает reference images", str(res.get("error") or ""))


class PricingCatalogTests(unittest.TestCase):
    def test_every_catalog_model_has_non_empty_cost_hint(self) -> None:
        rows = catalog_models_for_template(
            settings_default_id="google/gemini-2.5-flash-image",
            settings_fallback_id="openai/gpt-5-image-mini",
        )
        self.assertGreaterEqual(len(rows), len(OPENROUTER_IMAGE_MODELS_CATALOG))
        for row in rows:
            hint = str(row.get("cost_hint") or "").strip()
            self.assertTrue(bool(hint), f"empty cost_hint for model {row.get('id')}")
            self.assertIn("Цена", hint)

    def test_reference_capability_flags_are_defined(self) -> None:
        self.assertTrue(openrouter_model_supports_reference_images("bytedance-seed/seedream-4.5"))
        self.assertFalse(openrouter_model_supports_reference_images("qwen/qwen-image"))


if __name__ == "__main__":
    unittest.main()
