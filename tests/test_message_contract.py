import asyncio
import unittest

from model import Conversation, EditMessageRequest, ImageCleanupRequest, Room, Session
from service import _validated_image_urls


class MessageContractTests(unittest.TestCase):
    def test_session_keeps_backend_resolved_display_name_for_presence(self):
        session = Session(
            session_id="session-1",
            user_id=12,
            display_name="Rahim Example",
            profile_image=None,
            time_to_live=30,
        )
        stored = session.model_dump()
        self.assertEqual(stored["display_name"], "Rahim Example")
        self.assertEqual(stored["user_id"], 12)
        self.assertNotIn("access_token", stored)

    def test_conversation_response_can_expose_viewer_specific_peer_name(self):
        conversation = Conversation(
            conversation_id="direct-12-34",
            name="Peer Full Name",
            people=[12, 34],
            peer_user_id=34,
            peer_name="Peer Full Name",
            peer_phone_number="+998000000000",
        )
        payload = conversation.model_dump()
        self.assertEqual(payload["name"], "Peer Full Name")
        self.assertEqual(payload["peer_user_id"], 34)
        self.assertEqual(payload["peer_name"], "Peer Full Name")

    def test_message_can_store_sender_display_name(self):
        message = Room(
            room_id="message-1",
            conversation_id="direct-12-34",
            text="hello",
            who_sent=12,
            sender_name="Rahim Example",
        )
        self.assertEqual(message.sender_name, "Rahim Example")

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
            image_ids=["01234567-89ab-cdef-0123-456789abcdef"],
        )
        self.assertIsNone(message.text)
        self.assertEqual(len(message.images), 1)
        self.assertEqual(len(message.image_ids), 1)

    def test_legacy_image_urls_can_have_no_managed_image_id(self):
        message = Room(
            room_id="legacy-image",
            conversation_id="direct-1-2",
            text=None,
            who_sent=1,
            images=["https://legacy.example.test/image.jpg"],
            image_ids=[None],
        )
        self.assertIsNone(message.image_ids[0])

    def test_cleanup_request_limits_image_count(self):
        request = ImageCleanupRequest(image_ids=[
            "01234567-89ab-cdef-0123-456789abcdef"
        ])
        self.assertEqual(len(request.image_ids), 1)

    def test_edit_request_accepts_text_and_images(self):
        request = EditMessageRequest(
            text="updated",
            images=["https://images.example.test/a.jpg"],
        )
        self.assertEqual(request.text, "updated")
        self.assertEqual(request.images, ["https://images.example.test/a.jpg"])

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
