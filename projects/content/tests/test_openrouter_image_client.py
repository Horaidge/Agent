import unittest

from services.images.openrouter_image_client import _message_content_for_request


class OpenRouterImageClientTests(unittest.TestCase):
    def test_message_content_with_refs_places_text_first(self) -> None:
        content = _message_content_for_request(
            "prompt text",
            ["https://example.com/ref1.png", "https://example.com/ref2.png"],
        )
        self.assertIsInstance(content, list)
        parts = list(content or [])
        self.assertGreaterEqual(len(parts), 3)
        self.assertEqual(parts[0].get("type"), "text")
        self.assertEqual(parts[0].get("text"), "prompt text")
        self.assertEqual(parts[1].get("type"), "image_url")
        self.assertEqual(parts[2].get("type"), "image_url")


if __name__ == "__main__":
    unittest.main()
