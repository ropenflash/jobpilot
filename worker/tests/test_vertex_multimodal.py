import base64
import unittest

from app.services.vertex_client import _payload


class VertexMultimodalPayloadTests(unittest.TestCase):
    def test_image_bytes_are_attached_to_last_user_message(self):
        payload = _payload(
            [
                {"role": "system", "content": "Inspect the job page."},
                {"role": "user", "content": "Analyze this posting."},
            ],
            json_mode=True,
            images=[("image/jpeg", b"sample-screenshot")],
        )

        self.assertEqual(len(payload["contents"]), 1)
        parts = payload["contents"][0]["parts"]
        self.assertEqual(parts[0]["text"], "Analyze this posting.")
        self.assertEqual(parts[1]["inlineData"]["mimeType"], "image/jpeg")
        self.assertEqual(
            base64.b64decode(parts[1]["inlineData"]["data"]),
            b"sample-screenshot",
        )
        self.assertEqual(
            payload["systemInstruction"]["parts"][0]["text"],
            "Inspect the job page.",
        )

    def test_rejects_unsupported_image_types(self):
        with self.assertRaises(ValueError):
            _payload(
                [{"role": "user", "content": "Analyze this."}],
                json_mode=False,
                images=[("image/gif", b"gif")],
            )


if __name__ == "__main__":
    unittest.main()
