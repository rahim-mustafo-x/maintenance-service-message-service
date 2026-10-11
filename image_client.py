import json
import uuid
from urllib.error import HTTPError
from urllib.parse import urlencode
from uuid import UUID

from py_eureka_client.eureka_client import do_service_async

IMAGE_SERVICE_APP = "IMAGE-SERVICE"  # name registered in Eureka
IMAGE_SERVICE_TIMEOUT = 15


def _bearer(auth: str) -> str:
    token = auth.strip()
    if token[:7].lower() == "bearer ":
        token = token[7:].strip()
    if not token:
        raise ValueError("Missing bearer token")
    return f"Bearer {token}"


def _encode_multipart(
    field: str, filename: str, content: bytes, content_type: str
) -> tuple[bytes, str]:
    """Build a multipart/form-data body (do_service_async has no `files=` option)."""
    boundary = uuid.uuid4().hex
    safe_name = filename.replace('"', "").replace("\r", "").replace("\n", "")
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{safe_name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    return head + content + tail, f"multipart/form-data; boundary={boundary}"


async def upload_image(
    *,
    content: bytes,
    filename: str,
    content_type: str,
    owner_id: int,
    auth: str,
) -> str:
    """Forward a local attachment to Image Service and return its UUID."""
    payload, multipart_type = _encode_multipart("file", filename, content, content_type)
    query = urlencode({"ownerId": owner_id, "imageType": "SERVICE"})

    body = await do_service_async(
        IMAGE_SERVICE_APP,
        f"/v1/image?{query}",
        method="POST",
        data=payload,
        return_type="json",
        headers={
            "Authorization": _bearer(auth),
            "Content-Type": multipart_type,
        },
        timeout=IMAGE_SERVICE_TIMEOUT,
    )

    image = body.get("data") if isinstance(body, dict) else None
    image_id = image.get("id") if isinstance(image, dict) else None
    if body.get("code") not in (201, None) or not image_id:
        raise RuntimeError(body.get("message") or "Image Service returned no image ID")
    return str(UUID(str(image_id)))


async def validate_owned_image(image_id: str, owner_id: int) -> None:
    """Reject forged IDs and images owned by a different user."""
    normalized_id = str(UUID(str(image_id)))
    try:
        body = await do_service_async(
            IMAGE_SERVICE_APP,
            f"/v1/image/data/{normalized_id}",
            return_type="json",
            timeout=IMAGE_SERVICE_TIMEOUT,
        )
    except HTTPError as exc:
        if exc.code == 404:
            raise ValueError("Uploaded image no longer exists") from exc
        raise

    image = body.get("data") if isinstance(body, dict) else None
    if not isinstance(image, dict):
        raise ValueError("Image Service returned invalid image metadata")
    if int(image.get("ownerId", -1)) != int(owner_id):
        raise ValueError("Image does not belong to the authenticated user")
    if image.get("imageType") != "SERVICE":
        raise ValueError("Image is not a message attachment")


async def delete_image(image_id: str) -> None:
    normalized_id = str(UUID(str(image_id)))
    try:
        raw = await do_service_async(
            IMAGE_SERVICE_APP,
            f"/v1/image/{normalized_id}",
            method="DELETE",
            return_type="string",  # tolerate empty bodies
            timeout=IMAGE_SERVICE_TIMEOUT,
        )
    except HTTPError as exc:
        if exc.code == 404:
            return
        raise

    if raw:
        try:
            body = json.loads(raw)
        except ValueError:
            return
        if isinstance(body, dict) and body.get("code") not in (200, None):
            raise RuntimeError(body.get("message") or "Image Service refused to delete image")