"""HyperScale Platform — Firebase Client.

Wrapper for Firebase Admin SDK for sending push notifications.
"""

from __future__ import annotations

import firebase_admin
from firebase_admin import credentials, messaging
from typing import Any

from shared.logging import get_logger

logger = get_logger(__name__)


class FirebaseClient:
    """Firebase Cloud Messaging (FCM) client.

    Handles initialization of Firebase Admin SDK and sending
    messages to individual tokens or topics.
    """

    _initialized = False

    def __init__(self, credential_path: str | None = None) -> None:
        """Initialize Firebase Admin SDK."""
        if not FirebaseClient._initialized:
            try:
                if credential_path:
                    cred = credentials.Certificate(credential_path)
                    firebase_admin.initialize_app(cred)
                else:
                    # Initialize with default application credentials
                    # (Requires GOOGLE_APPLICATION_CREDENTIALS env var)
                    firebase_admin.initialize_app()
                FirebaseClient._initialized = True
                logger.info("firebase_admin_initialized")
            except Exception as e:
                logger.error("firebase_admin_init_failed", error=str(e))
                # Don't raise here; allow the service to degrade gracefully

    async def send_to_token(
        self,
        token: str,
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> bool:
        """Send a notification to a specific FCM token.

        Args:
            token: The FCM device token.
            title: Notification title.
            body: Notification body.
            data: Optional data payload (values must be strings).

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self._initialized:
            logger.warning("firebase_not_initialized_skipping_send")
            return False

        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                token=token,
            )
            response = messaging.send(message)
            logger.debug("fcm_message_sent", response=response, token=token[:10])
            return True
        except Exception as e:
            logger.error("fcm_send_failed", error=str(e), token=token[:10])
            return False
