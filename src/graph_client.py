"""Minimal Microsoft Graph client abstraction focused on SharePoint file retrieval.

Responsibilities:
 - Resolve a SharePoint site (given host + path) to its site ID.
 - Resolve a document library (drive) by name to its drive ID.
 - Enumerate items (files/folders) optionally within a sub-folder path.
 - Download a selected file to local disk (streaming, memory-efficient).

Why a thin wrapper? To isolate raw REST calls and provide clear error messages; callers do not
need to assemble Graph endpoints manually.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import requests

from .config import AppConfig


@dataclass
class SharePointTarget:
    """Resolved identifiers needed to address items in a SharePoint document library (drive)."""
    site_id: str
    drive_id: str


class GraphClient:
    """High-level helper for a subset of Graph endpoints used in this sample."""

    def __init__(self, cfg: AppConfig, access_token: str):
        self.cfg = cfg
        self.base = cfg.graph.base_url.rstrip("/")
        # Reuse an HTTP session across requests for connection pooling.
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        })

    def _get(self, url: str, **kwargs) -> Dict[str, Any]:
        """Perform a GET request and raise a descriptive error on failure."""
        r = self.session.get(url, **kwargs)
        if not r.ok:
            raise RuntimeError(f"Graph GET failed {r.status_code}: {r.text}")
        return r.json()

    def resolve_site(self) -> str:
        """Return the site ID for the configured SharePoint site path."""
        host = self.cfg.sharepoint.site_hostname
        spath = self.cfg.sharepoint.site_path
        url = f"{self.base}/sites/{host}:{spath}"
        data = self._get(url)
        return data["id"]

    def resolve_drive(self, site_id: str) -> str:
        """Return the drive (document library) ID matching the configured drive_name."""
        drive_name = self.cfg.sharepoint.drive_name
        url = f"{self.base}/sites/{site_id}/drives"
        data = self._get(url)
        drives = data.get("value", [])
        for d in drives:
            if d.get("name") == drive_name:
                return d.get("id")
        raise RuntimeError(f"Drive named '{drive_name}' not found on site {site_id}")

    def list_items(self, target: SharePointTarget, folder_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """List items (files/folders) in the root or a nested folder.

        Args:
            target: Resolved site + drive identifiers.
            folder_path: Optional relative folder (e.g. "Folder/Sub") inside the drive.
        Returns:
            A list of item objects from Graph (raw JSON dictionaries).
        """
        if folder_path:
            # Encode each segment to handle spaces/special characters.
            enc_path = "/".join([requests.utils.quote(p, safe="") for p in folder_path.strip("/").split("/")])
            url = f"{self.base}/drives/{target.drive_id}/root:/{enc_path}:/children"
        else:
            url = f"{self.base}/drives/{target.drive_id}/root/children"
        return self._get(url).get("value", [])

    def download_item(self, target: SharePointTarget, item_id: str, dest_path: str) -> str:
        """Stream a file's binary contents to disk.

        Args:
            target: Resolved SharePoint identifiers.
            item_id: Drive item ID (file) to download.
            dest_path: Local file system path to write to.
        Returns:
            The destination path (for convenience/chaining).
        Raises:
            RuntimeError: on non-successful HTTP status codes.
        """
        url = f"{self.base}/drives/{target.drive_id}/items/{item_id}/content"
        r = self.session.get(url, stream=True)
        if not r.ok:
            raise RuntimeError(f"Graph download failed {r.status_code}: {r.text}")
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1MB chunks balances speed/memory
                if chunk:
                    f.write(chunk)
        return dest_path
