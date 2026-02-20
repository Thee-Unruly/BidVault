"""
sharepoint.py
─────────────
Connects to SharePoint via Microsoft Graph API.
Downloads documents and feeds them into the ingestion pipeline.

This is the integration layer between SharePoint (your document vault)
and BidVault's vector search layer.

SETUP (one-time, done by IT admin):
  1. Create an App Registration in Azure Active Directory
     → Azure Portal → App Registrations → New Registration
     → Name: "BidVault"

  2. Add API Permissions:
     → Microsoft Graph → Application permissions:
        - Sites.Read.All
        - Files.Read.All
     → Grant admin consent

  3. Create a Client Secret:
     → Certificates & Secrets → New client secret
     → Copy the value immediately (only shown once)

  4. Set environment variables:
     SHAREPOINT_TENANT_ID     — Azure AD tenant ID
     SHAREPOINT_CLIENT_ID     — App registration client ID
     SHAREPOINT_CLIENT_SECRET — Client secret value
     SHAREPOINT_SITE_URL      — e.g. https://yourfirm.sharepoint.com/sites/BidDocs

ENVIRONMENT VARIABLES:
  SHAREPOINT_TENANT_ID
  SHAREPOINT_CLIENT_ID
  SHAREPOINT_CLIENT_SECRET
  SHAREPOINT_SITE_URL
  SHAREPOINT_LIBRARY_NAME     — Document library name, default "Documents"
"""

import os
import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .pipeline import IngestionPipeline, IngestionRequest, IngestionResult


GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL  = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


# ── AUTH ──────────────────────────────────────────────────────────────────────

class GraphAuth:
    """Manages access tokens for Microsoft Graph API."""

    def __init__(self):
        self.tenant_id     = os.environ["SHAREPOINT_TENANT_ID"]
        self.client_id     = os.environ["SHAREPOINT_CLIENT_ID"]
        self.client_secret = os.environ["SHAREPOINT_CLIENT_SECRET"]
        self._token        = None
        self._token_expiry = 0

    def get_token(self) -> str:
        """Returns a valid access token, refreshing if expired."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        import urllib.request
        import urllib.parse

        data = urllib.parse.urlencode({
            "grant_type":    "client_credentials",
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "scope":         "https://graph.microsoft.com/.default",
        }).encode()

        url = TOKEN_URL.format(tenant_id=self.tenant_id)
        req = urllib.request.Request(url, data=data, method="POST")

        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())

        self._token        = result["access_token"]
        self._token_expiry = time.time() + result["expires_in"]
        return self._token

    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.get_token()}",
            "Content-Type":  "application/json",
        }


# ── SHAREPOINT CLIENT ─────────────────────────────────────────────────────────

@dataclass
class SharePointItem:
    """Represents a file in SharePoint."""
    item_id:     str
    name:        str
    web_url:     str
    download_url: str
    size_bytes:  int
    modified_at: str

    # Custom metadata columns (if configured in SharePoint)
    category:       str  = ""
    expiry_date:    str  = ""
    sector:         str  = ""
    donor:          str  = ""
    document_year:  int  = 0
    won:            Optional[bool] = None
    client_name:    str  = ""
    source_type:    str  = "other"


class SharePointConnector:
    """
    Reads documents from a SharePoint document library.
    Downloads files and passes them to the ingestion pipeline.
    """

    def __init__(self, pipeline: Optional[IngestionPipeline] = None):
        self.auth     = GraphAuth()
        self.pipeline = pipeline or IngestionPipeline()
        self._site_id = None
        self._list_id = None

    def _get(self, url: str) -> dict:
        """Make a GET request to Graph API."""
        import urllib.request
        req = urllib.request.Request(url, headers=self.auth.headers())
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    def _get_site_id(self) -> str:
        if self._site_id:
            return self._site_id

        site_url = os.environ["SHAREPOINT_SITE_URL"]
        # Extract hostname and site path from URL
        # e.g. https://yourfirm.sharepoint.com/sites/BidDocs
        #   → hostname: yourfirm.sharepoint.com
        #   → site_path: sites/BidDocs
        from urllib.parse import urlparse
        parsed    = urlparse(site_url)
        hostname  = parsed.netloc
        site_path = parsed.path.lstrip("/")

        url    = f"{GRAPH_BASE}/sites/{hostname}:/{site_path}"
        result = self._get(url)
        self._site_id = result["id"]
        return self._site_id

    def _get_list_id(self) -> str:
        if self._list_id:
            return self._list_id

        site_id      = self._get_site_id()
        library_name = os.environ.get("SHAREPOINT_LIBRARY_NAME", "Documents")
        url          = f"{GRAPH_BASE}/sites/{site_id}/lists?$filter=displayName eq '{library_name}'"
        result       = self._get(url)

        if not result.get("value"):
            raise ValueError(f"Library '{library_name}' not found in SharePoint site")

        self._list_id = result["value"][0]["id"]
        return self._list_id

    def list_documents(self, folder: str = "") -> list[SharePointItem]:
        """
        List all documents in the SharePoint library.
        Optionally filter by subfolder (e.g. "Proposals/2024").
        Returns SharePointItem objects with metadata.
        """
        site_id = self._get_site_id()
        list_id = self._get_list_id()

        # Get items with expanded fields (custom metadata columns)
        url = (
            f"{GRAPH_BASE}/sites/{site_id}/lists/{list_id}/items"
            f"?$expand=fields,driveItem"
            f"&$select=id,fields,driveItem"
            f"&$top=500"
        )

        items    = []
        next_url = url

        while next_url:
            result   = self._get(next_url)
            next_url = result.get("@odata.nextLink")

            for item in result.get("value", []):
                fields     = item.get("fields", {})
                drive_item = item.get("driveItem", {})

                # Skip folders
                if drive_item.get("folder"):
                    continue

                # Only process supported file types
                name = fields.get("FileLeafRef", drive_item.get("name", ""))
                if not name:
                    continue
                ext = Path(name).suffix.lower()
                if ext not in (".pdf", ".docx", ".doc", ".txt"):
                    continue

                items.append(SharePointItem(
                    item_id      = item["id"],
                    name         = name,
                    web_url      = drive_item.get("webUrl", ""),
                    download_url = drive_item.get("@microsoft.graph.downloadUrl", ""),
                    size_bytes   = drive_item.get("size", 0),
                    modified_at  = drive_item.get("lastModifiedDateTime", ""),

                    # Custom columns — map from your SharePoint column names
                    category     = fields.get("Document_Category", ""),
                    expiry_date  = fields.get("Expiry_Date", ""),
                    sector       = fields.get("BidVault_Sector", ""),
                    donor        = fields.get("BidVault_Donor", ""),
                    source_type  = _map_source_type(fields.get("Document_Category", "")),
                    client_name  = fields.get("Client_Name", ""),
                    won          = _parse_won(fields.get("Bid_Won")),
                    document_year= _parse_year(fields.get("Document_Year")),
                ))

        return items

    def download_file(self, item: SharePointItem) -> str:
        """
        Download a SharePoint file to a temp directory.
        Returns the local file path.
        Caller is responsible for deleting the temp file.
        """
        if not item.download_url:
            raise ValueError(f"No download URL for {item.name}")

        import urllib.request

        suffix   = Path(item.name).suffix
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)

        # The download URL is pre-authenticated — no auth header needed
        urllib.request.urlretrieve(item.download_url, tmp_file.name)
        return tmp_file.name

    def sync_to_vector_store(
        self,
        force_reindex: bool = False,
    ) -> dict:
        """
        Sync all documents from SharePoint into the vector store.

        force_reindex: if True, re-index even documents already indexed.
                       Use when you've changed chunking or embedding strategy.

        Returns a summary dict.
        """
        print("Starting SharePoint → Vector Store sync...")
        items    = self.list_documents()
        print(f"Found {len(items)} documents in SharePoint")

        results  = {"success": 0, "skipped": 0, "failed": 0, "errors": []}

        for item in items:
            print(f"\n{'─'*50}")
            print(f"Processing: {item.name}")

            local_path = None
            try:
                local_path = self.download_file(item)

                request = IngestionRequest(
                    file_path          = local_path,
                    source_type        = item.source_type,
                    sector             = item.sector,
                    donor              = item.donor,
                    year               = item.document_year,
                    client             = item.client_name,
                    won                = item.won,
                    sharepoint_item_id = item.item_id,
                    sharepoint_url     = item.web_url,
                )

                result = self.pipeline.ingest(request)

                if result.success:
                    results["success"] += 1
                    print(f"✓ {result.chunks_stored} chunks stored")
                else:
                    results["failed"] += 1
                    results["errors"].append({"file": item.name, "error": result.error})
                    print(f"✗ Failed: {result.error}")

            except Exception as e:
                results["failed"] += 1
                results["errors"].append({"file": item.name, "error": str(e)})
                print(f"✗ Exception: {e}")

            finally:
                # Always clean up the temp file
                if local_path and os.path.exists(local_path):
                    os.unlink(local_path)

        print(f"\n{'═'*50}")
        print(f"Sync complete: {results['success']} success, {results['skipped']} skipped, {results['failed']} failed")
        return results


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _map_source_type(category: str) -> str:
    """Map SharePoint Document_Category column to SourceType enum."""
    mapping = {
        "Proposal":        "proposal",
        "Past Proposal":   "proposal",
        "RFP":             "rfp",
        "Tender":          "rfp",
        "CV":              "cv",
        "Certificate":     "certificate",
        "Project Report":  "project",
        "Methodology":     "methodology",
        "Financial":       "financial",
    }
    return mapping.get(category, "other")


def _parse_won(value) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("yes", "true", "won", "1")
    return None


def _parse_year(value) -> int:
    if not value:
        from datetime import datetime
        return datetime.now().year
    try:
        return int(str(value)[:4])
    except (ValueError, TypeError):
        from datetime import datetime
        return datetime.now().year
