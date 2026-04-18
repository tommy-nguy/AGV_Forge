"""
YouTube Publisher sử dụng YouTube Data API v3.
"""

import os
import pickle
from pathlib import Path
from typing import Optional, Dict, Any
import structlog

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .base_publisher import BasePublisher, PublishError

logger = structlog.get_logger(__name__)


class YouTubePublisher(BasePublisher):
    """Upload video lên YouTube."""

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
    API_SERVICE_NAME = "youtube"
    API_VERSION = "v3"

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.client_id = credentials.get("client_id")
        self.client_secret = credentials.get("client_secret")
        self.token_path = Path(credentials.get("token_path", "youtube_token.pickle"))
        self.service = None

    def authenticate(self) -> bool:
        """Xác thực OAuth 2.0 với YouTube."""
        creds = None
        if self.token_path.exists():
            with open(self.token_path, "rb") as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Cần client_secrets.json
                client_secrets = {
                    "installed": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                }
                flow = InstalledAppFlow.from_client_config(client_secrets, self.SCOPES)
                creds = flow.run_local_server(port=0)

            with open(self.token_path, "wb") as token:
                pickle.dump(creds, token)

        self.service = build(self.API_SERVICE_NAME, self.API_VERSION, credentials=creds)
        self.authenticated = True
        logger.info("YouTube authentication successful")
        return True

    def upload_video(
        self,
        video_path: Path,
        title: str,
        description: str,
        thumbnail_path: Optional[Path] = None,
        privacy_status: str = "private",
        category_id: str = "22",
        tags: Optional[list] = None,
        **kwargs
    ) -> str:
        """Upload video và thumbnail (nếu có)."""
        if not self.authenticated:
            self.authenticate()

        if not video_path.exists():
            raise PublishError(f"Video file not found: {video_path}")

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or [],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/*",
            resumable=True,
            chunksize=1024 * 1024 * 5,  # 5MB chunks
        )

        logger.info("Uploading to YouTube", title=title)
        request = self.service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.debug("Upload progress", progress=f"{int(status.progress() * 100)}%")

        video_id = response["id"]
        logger.info("Video uploaded", video_id=video_id)

        # Upload thumbnail nếu có
        if thumbnail_path and thumbnail_path.exists():
            self.service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path))
            ).execute()
            logger.info("Thumbnail uploaded", video_id=video_id)

        return video_id

    def get_publish_status(self, video_id: str) -> Dict[str, Any]:
        """Lấy trạng thái video."""
        if not self.authenticated:
            self.authenticate()
        response = self.service.videos().list(
            id=video_id,
            part="status,statistics"
        ).execute()
        items = response.get("items", [])
        return items[0] if items else {}