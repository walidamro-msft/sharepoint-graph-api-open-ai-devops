"""Configuration loading and strongly-typed settings models.

Centralizes parsing of `config.json` (or an override via GRAPH_APP_CONFIG env var) into dataclasses
to provide IDE/typing assistance and safer downstream access. Optional sections (Azure OpenAI,
Azure DevOps) are handled gracefully; missing required top-level keys result in errors early.

Security recommendations (communicated via comments for customers):
 - Prefer environment variables for secrets (client secret, PAT, OpenAI key) in production.
 - Do not commit real secrets in source control. The sample shows structure only.
 - PAT override through AZDO_PAT env var supported.
"""

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

CONFIG_FILENAME = os.environ.get("GRAPH_APP_CONFIG", "config.json")

@dataclass
class GraphSettings:
    authority_host: str
    scope: List[str]
    base_url: str

@dataclass
class SharePointSettings:
    site_hostname: str
    site_path: str
    drive_name: str
    folder_path: str

@dataclass
class AzureOpenAISettings:
    endpoint: str
    api_key: str
    deployment: str
    api_version: str
    max_chars_per_chunk: int = 12000
    # Optional: number of parallel workers when summarizing chunks (>1 enables concurrency)
    chunk_workers: int = 1

@dataclass
class AzureDevOpsSettings:
    """Configuration for Azure DevOps work item creation."""
    organization: str  # e.g. https://dev.azure.com/yourorg
    project: str       # Project name
    pat: str           # Personal Access Token (consider env override)
    area_path: Optional[str] = None  # Optional area path within the project
    iteration_path: Optional[str] = None  # Optional iteration path
    work_item_type: str = "User Story"  # Default type
    api_version: str = "7.1-preview.3"  # REST API version

@dataclass
class AppConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    graph: GraphSettings
    sharepoint: SharePointSettings
    azure_openai: Optional[AzureOpenAISettings] = None
    azure_devops: Optional[AzureDevOpsSettings] = None
    prompts: Dict[str, dict] = None
    # Deletion policy for downloaded files: 'always', 'on_success', or 'never'
    delete_after: str = "on_success"

    @staticmethod
    def load(path: Optional[str] = None) -> "AppConfig":
        config_path = path or CONFIG_FILENAME
        if not os.path.exists(config_path):
            raise FileNotFoundError(
                f"Config file '{config_path}' not found. Copy 'config.example.json' to 'config.json' and fill values."
            )
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    # Required sections: graph + sharepoint + root auth fields
        graph = GraphSettings(**raw["graph"]) 
        sp = SharePointSettings(**raw["sharepoint"]) 
        aoai = None
        if "azure_openai" in raw and raw["azure_openai"]:
            # Support missing optional max_chars_per_chunk by providing default
            aoai_dict = {**raw["azure_openai"]}
            if "max_chars_per_chunk" not in aoai_dict:
                aoai_dict["max_chars_per_chunk"] = 12000
            if "chunk_workers" not in aoai_dict:
                aoai_dict["chunk_workers"] = 1
            aoai = AzureOpenAISettings(**aoai_dict)
        prompts = raw.get("prompts", {}) or {}
        azdo = None
        if "azure_devops" in raw and raw["azure_devops"]:
            # Allow PAT/env override
            azdo_dict = {**raw["azure_devops"]}
            # Environment variable overrides to avoid storing secrets in file
            azdo_pat_env = os.environ.get("AZDO_PAT")
            if azdo_pat_env:
                azdo_dict["pat"] = azdo_pat_env
            azdo = AzureDevOpsSettings(**azdo_dict)
        # deletion policy with validation
        delete_after = (raw.get("delete_after") or "on_success").lower()
        if delete_after not in ("always", "on_success", "never"):
            delete_after = "on_success"
        return AppConfig(
            tenant_id=raw["tenant_id"],
            client_id=raw["client_id"],
            client_secret=raw["client_secret"],
            graph=graph,
            sharepoint=sp,
            azure_openai=aoai,
            azure_devops=azdo,
            prompts=prompts,
            delete_after=delete_after,
        )
