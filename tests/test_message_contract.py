import asyncio
import unittest

from model import EditMessageRequest, Room
from service import _validated_image_urls, _image_id_from_url


class MessageContractTests(unittest.TestCase):
    def test_legacy_message_defaults_remain_compatible(self):
        message = Room(
            room_id="legacy-1",
            conversation_id="direct-1-2",
            text="legacy text",
            who_sent=1,
        )
        self.assertEqual(message.images, [])
        self.assertFalse(message.is_edited)
        self.assertFalse(message.is_deleted)
        self.assertIsNone(message.deleted_at)

    def test_image_only_message_is_representable(self):
        message = Room(
            room_id="image-1",
            conversation_id="direct-1-2",
            text=None,
            who_sent=1,
            images=["https://images.example.test/a.jpg"],
        )
        self.assertIsNone(message.text)
        self.assertEqual(len(message.images), 1)

    def test_edit_request_accepts_text_and_images(self):
        request = EditMessageRequest(
            text="updated",
            images=["https://images.example.test/a.jpg"],
        )
        self.assertEqual(request.text, "updated")
        self.assertEqual(request.images, ["https://images.example.test/a.jpg"])

    def test_image_id_is_extracted_from_image_service_url(self):
        image_id = "123e4567-e89b-12d3-a456-426614174000"
        self.assertEqual(
            _image_id_from_url(f"https://example.test/image-service/v1/image/{image_id}"),
            image_id,
        )

    def test_unrelated_url_does_not_yield_an_image_id(self):
        self.assertIsNone(_image_id_from_url("https://example.test/images/photo.jpg"))

    def test_new_message_model_keeps_image_service_ids(self):
        message = Room(
            room_id="image-2",
            conversation_id="direct-1-2",
            text=None,
            who_sent=1,
            images=["https://example.test/image-service/v1/image/123e4567-e89b-12d3-a456-426614174000"],
            image_ids=["123e4567-e89b-12d3-a456-426614174000"],
        )
        self.assertEqual(len(message.image_ids), 1)

    def test_image_urls_accept_http_and_https(self):
        result = asyncio.run(_validated_image_urls([
            "https://images.example.test/a.jpg",
            "http://images.example.test/b.png",
        ]))
        self.assertEqual(len(result), 2)

    def test_image_urls_reject_relative_or_non_http_urls(self):
        for url in ("images/a.jpg", "file:///tmp/a.jpg", "javascript:alert(1)", ""):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    asyncio.run(_validated_image_urls([url]))

    def test_image_count_limit(self):
        urls = [f"https://images.example.test/{i}.jpg" for i in range(11)]
        with self.assertRaises(ValueError):
            asyncio.run(_validated_image_urls(urls))


if __name__ == "__main__":
    unittest.main()
