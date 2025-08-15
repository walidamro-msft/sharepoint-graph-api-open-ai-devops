"""Azure DevOps work item helper.

Creates a "User Story" (or other configured type) from the LLM-produced summary output.
The LLM prompt enforces a simple contract:

    TITLE: <one line title>
    ---
    <markdown body>

This client parses that structure and issues a JSON Patch request to the Azure DevOps REST API.

Security note: A Personal Access Token (PAT) is used for simplicity. For production scenarios
consider using OAuth via a service principal / pipeline identity with least privilege scopes.
"""

import base64
import json
import re
from typing import Optional, Tuple
import requests

from .config import AppConfig


class AzureDevOpsClient:
    """Minimal Azure DevOps Work Item client (User Story creation)."""

    def __init__(self, cfg: AppConfig):
        if not cfg.azure_devops:
            raise ValueError("azure_devops settings missing in config.json")
        self.cfg = cfg
        self.org_url = cfg.azure_devops.organization.rstrip('/')
        self.project = cfg.azure_devops.project
        # Allow PAT override via env (done in config load) but still support header building here
        self.pat = cfg.azure_devops.pat
        self.api_version = cfg.azure_devops.api_version
        self.work_item_type = cfg.azure_devops.work_item_type or "User Story"
        self.area_path = cfg.azure_devops.area_path
        self.iteration_path = cfg.azure_devops.iteration_path

    def _auth_header(self) -> dict:
        """Return Authorization header using basic auth with PAT (username blank)."""
        token = f":{self.pat}".encode()
        b64 = base64.b64encode(token).decode()
        return {"Authorization": f"Basic {b64}"}

    @staticmethod
    def parse_title_and_body(summary_output: str) -> Tuple[str, str]:
        """Extract TITLE: line and markdown body separated by --- as per prompt contract."""
        title_match = re.search(r'^TITLE:\s*(.+)$', summary_output, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else "Generated User Story"
        # Split on first --- line
        parts = re.split(r'^---\s*$', summary_output, flags=re.MULTILINE)
        if len(parts) >= 2:
            # parts[0] contains title line maybe, body in parts[1] or beyond
            body_candidates = parts[1:]
            body = '\n\n'.join(p.strip() for p in body_candidates if p.strip())
        else:
            # Fallback: remove TITLE line
            body = re.sub(r'^TITLE:.*$', '', summary_output, flags=re.MULTILINE).strip()
        return title, body

    def create_user_story(self, summary_output: str) -> Tuple[int, Optional[str]]:
        """Create a work item from model output.

        Args:
            summary_output: Raw text produced by the LLM (expected format described above).
        Returns:
            (status_code, work_item_url_or_error_message)
        """
        title, body = self.parse_title_and_body(summary_output)
        url = f"{self.org_url}/{self.project}/_apis/wit/workitems/${self.work_item_type}?api-version={self.api_version}"
        ops = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
            {"op": "add", "path": "/fields/System.Description", "value": body},
        ]
        if self.area_path:
            ops.append({"op": "add", "path": "/fields/System.AreaPath", "value": self.area_path})
        if self.iteration_path:
            ops.append({"op": "add", "path": "/fields/System.IterationPath", "value": self.iteration_path})

        headers = {
            **self._auth_header(),
            'Content-Type': 'application/json-patch+json'
        }
        resp = requests.post(url, headers=headers, data=json.dumps(ops))
        if resp.status_code >= 300:
            return resp.status_code, f"Error creating work item: {resp.status_code} {resp.text}"
        data = resp.json()
        return resp.status_code, data.get('url')
