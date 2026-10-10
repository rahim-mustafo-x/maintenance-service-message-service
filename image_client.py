import os
from uuid import UUID

import httpx


IMAGE_SERVICE_URL = os.getenv("IMAGE_SERVICE_URL", "http://image-service:7878").rstrip("/")
IMAGE_SERVICE_TIMEOUT = float(os.getenv("IMAGE_SERVICE_TIMEOUT", "15"))


def _bearer(auth: str) -> str:
    token = auth.strip()
    if token[:7].lower() == "bearer ":
        token = token[7:].strip()
    if not token:
        raise ValueError("Missing bearer token")
    return f"Bearer {token}"


async def upload_image(
    *,
    content: bytes,
    filename: str,
    content_type: str,
    owner_id: int,
    auth: str,
) -> str:
    """Forward a local attachment to Image Service and return its UUID."""
    async with httpx.AsyncClient(timeout=IMAGE_SERVICE_TIMEOUT) as client:
        response = await client.post(
            f"{IMAGE_SERVICE_URL}/v1/image",
            params={"ownerId": owner_id, "imageType": "SERVICE"},
            headers={"Authorization": _bearer(auth)},
            files={"file": (filename, content, content_type)},
        )
    response.raise_for_status()
    body = response.json()
    image = body.get("data") if isinstance(body, dict) else None
    image_id = image.get("id") if isinstance(image, dict) else None
    if body.get("code") not in (201, None) or not image_id:
        raise RuntimeError(body.get("message") or "Image Service returned no image ID")
    return str(UUID(str(image_id)))


async def validate_owned_image(image_id: str, owner_id: int) -> None:
    """Reject forged IDs and images owned by a different user."""
    normalized_id = str(UUID(str(image_id)))
    async with httpx.AsyncClient(timeout=IMAGE_SERVICE_TIMEOUT) as client:
        response = await client.get(f"{IMAGE_SERVICE_URL}/v1/image/data/{normalized_id}")
    if response.status_code == 404:
        raise ValueError("Uploaded image no longer exists")
    response.raise_for_status()
    body = response.json()
    image = body.get("data") if isinstance(body, dict) else None
    if not isinstance(image, dict):
        raise ValueError("Image Service returned invalid image metadata")
    if int(image.get("ownerId", -1)) != int(owner_id):
        raise ValueError("Image does not belong to the authenticated user")
    if image.get("imageType") != "SERVICE":
        raise ValueError("Image is not a message attachment")


async def delete_image(image_id: str) -> None:
    normalized_id = str(UUID(str(image_id)))
    async with httpx.AsyncClient(timeout=IMAGE_SERVICE_TIMEOUT) as client:
        response = await client.delete(f"{IMAGE_SERVICE_URL}/v1/image/{normalized_id}")
    if response.status_code == 404:
        return
    response.raise_for_status()
    body = response.json()
    if isinstance(body, dict) and body.get("code") not in (200, None):
        raise RuntimeError(body.get("message") or "Image Service refused to delete image")
