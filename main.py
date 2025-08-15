"""Entry point for document selection, summarization, and optional User Story creation.

Execution flow:
 1. Load configuration (Graph + SharePoint + Azure OpenAI + optional Azure DevOps).
 2. Acquire an application token (client credentials) for Microsoft Graph.
 3. Resolve the target SharePoint site + drive, list files (skipping folders).
 4. Let the user choose a file interactively (console input).
 5. Download the selected file locally (avoiding overwrite collisions).
 6. Extract text (supports txt/md/csv/log/pdf/docx) and send to Azure OpenAI for summarization
     using a prompt that returns a TITLE line and Markdown body.
 7. If Azure DevOps config present, parse the model output and create a work item.
 8. Optionally delete the local temporary file based on configured policy.

The summarization prompt can be refined in config.json without code changes.
"""

import json
import sys
from typing import Optional
import time

from src.config import AppConfig
from src.auth import GraphAuth
from src.graph_client import GraphClient, SharePointTarget
import os
from src.llm_client import LLMClient
from src.doc_reader import read_text_from_file
from src.azure_devops_client import AzureDevOpsClient


def main(config_path: Optional[str] = None) -> int:
    cfg = AppConfig.load(config_path)
    # Authenticate (client credentials) and acquire bearer token for Graph
    auth = GraphAuth(cfg)
    token = auth.get_token()

    graph = GraphClient(cfg, token)

    # Measure retrieval time (resolve site + drive + list items)
    t_retrieval_start = time.perf_counter()
    # Resolve site + drive IDs (SharePoint identifiers)
    site_id = graph.resolve_site()
    drive_id = graph.resolve_drive(site_id)
    target = SharePointTarget(site_id=site_id, drive_id=drive_id)

    folder = cfg.sharepoint.folder_path or None
    items = graph.list_items(target, folder)
    t_retrieval_end = time.perf_counter()

    def fmt_dur(seconds: float) -> str:
        m, rem = divmod(seconds, 60.0)
        return f"{int(m):02d}:{rem:06.4f}"

    # Print numbered list of files (skip folders) to help user choose
    files = []
    print("Files:")
    for it in items:
        if "folder" in it:
            continue
        files.append(it)
    for idx, it in enumerate(files, start=1):
        name = it.get("name")
        size = it.get("size")
        mtime = it.get("lastModifiedDateTime")
        kind = it.get("file", {}).get("mimeType", "file")
        print(f"{idx}. {name}  [{kind}]  {size} bytes  modified {mtime}")

    if not files:
        print("No files found to download in the specified location.")
        return 0

    print(f"Retrieval Time: {fmt_dur(t_retrieval_end - t_retrieval_start)}")

    # Prompt user to select a file by number
    while True:
        try:
            choice = input("Enter the number of the document to download (or press Enter to cancel): ").strip()
            if choice == "":
                print("Cancelled.")
                return 0
            num = int(choice)
            if 1 <= num <= len(files):
                break
            print(f"Please enter a number between 1 and {len(files)}.")
        except ValueError:
            print("Invalid input. Please enter a number.")

    selected = files[num - 1]
    filename = selected.get("name") or "downloaded-file"
    dest = os.path.abspath(filename)
    # Avoid overwriting: if exists, add (1), (2), ... suffix
    if os.path.exists(dest):
        root, ext = os.path.splitext(dest)
        i = 1
        while True:
            candidate = f"{root} ({i}){ext}"
            if not os.path.exists(candidate):
                dest = candidate
                break
            i += 1

    print(f"Downloading '{filename}' to '{dest}'...")
    t_dl_start = time.perf_counter()
    graph.download_item(target, selected.get("id"), dest)
    t_dl_end = time.perf_counter()
    print("Download complete.")
    # Download metrics
    try:
        downloaded_size = os.path.getsize(dest)
    except OSError:
        downloaded_size = 0
    print(f"Download Time: {fmt_dur(t_dl_end - t_dl_start)}  |  Downloaded Size: {downloaded_size} bytes")
    # Determine effective deployment (env override takes precedence)
    dep_name = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT")
    if not dep_name and getattr(cfg, "azure_openai", None):
        dep_name = cfg.azure_openai.deployment
    print(f"Preparing AI summarization with deployment '{dep_name or 'unknown'}'... this may take a few moments.")

    # Read file text and summarize via Azure OpenAI
    summary: Optional[str] = None
    summarize_ok = False
    try:
        text = read_text_from_file(dest)
        if not text.strip():
            print("Downloaded file appears empty or unreadable for text extraction.")
        else:
            llm = LLMClient(cfg)
            # Load prompts: allow overrides in config
            p = (cfg.prompts or {}).get("summarize", {})
            system_prompt = p.get("system") if isinstance(p, dict) else None
            user_prompt = p.get("user") if isinstance(p, dict) else None
            # --- Summarization timing ---
            t_sum_start = time.perf_counter()
            summary = llm.summarize(text, system_prompt=system_prompt, user_prompt=user_prompt)
            t_sum_end = time.perf_counter()
            summarize_ok = True
            print("\n===== SUMMARY (TITLE + MARKDOWN) =====\n")
            print(summary)
            print("\n======================================\n")
            sum_duration = t_sum_end - t_sum_start
            print(f"AI Summarization Time: {fmt_dur(sum_duration)} | Input Chars: {len(text)} | Output Chars: {len(summary or '')}")

            # --- Azure DevOps work item creation timing ---
            if cfg.azure_devops and summary:
                try:
                    azdo = AzureDevOpsClient(cfg)
                    t_azdo_start = time.perf_counter()
                    status, result = azdo.create_user_story(summary)
                    t_azdo_end = time.perf_counter()
                    if status < 300:
                        print(f"Azure DevOps work item created: {result}")
                    else:
                        print(f"Failed to create Azure DevOps work item: {result}")
                    print(f"Azure DevOps Work Item Creation Time: {fmt_dur(t_azdo_end - t_azdo_start)} | Status: {status}")
                except Exception as e:
                    print(f"Azure DevOps creation error: {e}")
    except Exception as e:
        print(f"Summarization failed: {e}")
    finally:
    # (Summarization timing already printed immediately after completion.)
        # Delete based on policy
        policy = getattr(cfg, "delete_after", "on_success").lower()
        should_delete = policy == "always" or (policy == "on_success" and summarize_ok)
        if should_delete:
            try:
                os.remove(dest)
                print(f"Deleted temporary file: {dest}")
            except Exception as e:
                print(f"Warning: failed to delete '{dest}': {e}")

    return 0


if __name__ == "__main__":
    path = None
    if len(sys.argv) > 1:
        path = sys.argv[1]
    raise SystemExit(main(path))
