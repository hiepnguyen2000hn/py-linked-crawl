"""
CRM Providers — adapter pattern.

Providers: HubSpot, Notion, Google Sheet (existing)
Mỗi provider implement CRMProvider ABC.
"""
from __future__ import annotations
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class CRMContact:
    """Normalized contact to push to CRM."""
    name:        str = ""
    email:       str = ""
    title:       str = ""
    company:     str = ""
    linkedin_url: str = ""
    status:      str = "cold"
    icp_score:   int = 0
    icp_tier:    str = ""
    notes:       str = ""
    source_row:  int = -1
    extra:       dict = field(default_factory=dict)


@dataclass
class SyncResult:
    provider:   str
    ok:         bool
    created:    int = 0
    updated:    int = 0
    skipped:    int = 0
    errors:     list[str] = field(default_factory=list)


# ── Base ──────────────────────────────────────────────────────────────────────

class CRMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def sync_contacts(self, contacts: list[CRMContact]) -> SyncResult:
        ...

    def test_connection(self) -> dict:
        return {"ok": True, "message": "No test available"}

    @property
    def is_configured(self) -> bool:
        return True


# ── HubSpot ───────────────────────────────────────────────────────────────────

class HubSpotProvider(CRMProvider):
    name = "hubspot"
    BASE = "https://api.hubapi.com"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("HUBSPOT_API_KEY", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _search_contact(self, email: str) -> str | None:
        """Trả về contact ID nếu đã tồn tại."""
        import requests
        r = requests.post(f"{self.BASE}/crm/v3/objects/contacts/search",
            headers=self._headers(),
            json={"filterGroups": [{"filters": [{"propertyName": "email",
                                                  "operator": "EQ", "value": email}]}]},
            timeout=10)
        results = r.json().get("results", [])
        return results[0]["id"] if results else None

    def _upsert(self, contact: CRMContact) -> tuple[str, str]:
        """Create hoặc update contact. Trả về (id, action)."""
        import requests
        props = {
            "firstname":       contact.name.split()[0] if contact.name else "",
            "lastname":        " ".join(contact.name.split()[1:]) if len(contact.name.split()) > 1 else "",
            "email":           contact.email,
            "jobtitle":        contact.title,
            "company":         contact.company,
            "hs_lead_status":  contact.status,
            "linkedin_bio":    contact.linkedin_url,
            "description":     f"ICP Score: {contact.icp_score} ({contact.icp_tier})\n{contact.notes}",
        }
        existing_id = self._search_contact(contact.email) if contact.email else None
        if existing_id:
            requests.patch(f"{self.BASE}/crm/v3/objects/contacts/{existing_id}",
                           headers=self._headers(), json={"properties": props}, timeout=10)
            return existing_id, "updated"
        r = requests.post(f"{self.BASE}/crm/v3/objects/contacts",
                          headers=self._headers(), json={"properties": props}, timeout=10)
        return r.json().get("id", ""), "created"

    def sync_contacts(self, contacts: list[CRMContact]) -> SyncResult:
        result = SyncResult(provider=self.name, ok=True)
        for c in contacts:
            try:
                _, action = self._upsert(c)
                if action == "created": result.created += 1
                else: result.updated += 1
            except Exception as e:
                result.errors.append(f"{c.name}: {e}")
        result.ok = len(result.errors) < len(contacts)
        return result

    def test_connection(self) -> dict:
        if not self.api_key: return {"ok": False, "message": "API key chưa được cấu hình"}
        import requests
        try:
            r = requests.get(f"{self.BASE}/crm/v3/objects/contacts?limit=1",
                             headers=self._headers(), timeout=8)
            return {"ok": r.status_code == 200, "message": "HubSpot OK" if r.status_code == 200 else f"HTTP {r.status_code}"}
        except Exception as e:
            return {"ok": False, "message": str(e)}


# ── Notion ────────────────────────────────────────────────────────────────────

class NotionProvider(CRMProvider):
    name = "notion"
    BASE = "https://api.notion.com/v1"

    def __init__(self, token: str = "", database_id: str = ""):
        self.token       = token       or os.getenv("NOTION_TOKEN", "")
        self.database_id = database_id or os.getenv("NOTION_DATABASE_ID", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.database_id)

    def _headers(self) -> dict:
        return {
            "Authorization":  f"Bearer {self.token}",
            "Content-Type":   "application/json",
            "Notion-Version": "2022-06-28",
        }

    def _build_props(self, c: CRMContact) -> dict:
        return {
            "Name":      {"title":  [{"text": {"content": c.name or "Unknown"}}]},
            "Email":     {"email":  c.email or None},
            "Title":     {"rich_text": [{"text": {"content": c.title}}]},
            "Company":   {"rich_text": [{"text": {"content": c.company}}]},
            "Status":    {"select": {"name": c.status or "cold"}},
            "ICP Score": {"number": c.icp_score or 0},
            "ICP Tier":  {"select": {"name": c.icp_tier or "D"}},
            "LinkedIn":  {"url": c.linkedin_url or None},
            "Notes":     {"rich_text": [{"text": {"content": c.notes[:2000]}}]},
        }

    def sync_contacts(self, contacts: list[CRMContact]) -> SyncResult:
        import requests
        result = SyncResult(provider=self.name, ok=True)

        # Tìm pages đã tồn tại (search by email)
        for c in contacts:
            try:
                # Check duplicate by email
                search = requests.post(f"{self.BASE}/databases/{self.database_id}/query",
                    headers=self._headers(),
                    json={"filter": {"property": "Email", "email": {"equals": c.email}}} if c.email else {},
                    timeout=10)
                existing = search.json().get("results", [])
                props = self._build_props(c)

                if existing:
                    page_id = existing[0]["id"]
                    requests.patch(f"{self.BASE}/pages/{page_id}",
                                   headers=self._headers(), json={"properties": props}, timeout=10)
                    result.updated += 1
                else:
                    requests.post(f"{self.BASE}/pages",
                        headers=self._headers(),
                        json={"parent": {"database_id": self.database_id}, "properties": props},
                        timeout=10)
                    result.created += 1
            except Exception as e:
                result.errors.append(f"{c.name}: {e}")

        result.ok = not result.errors or (result.created + result.updated) > 0
        return result

    def test_connection(self) -> dict:
        if not self.is_configured:
            return {"ok": False, "message": "Token hoặc Database ID chưa được cấu hình"}
        import requests
        try:
            r = requests.get(f"{self.BASE}/databases/{self.database_id}",
                             headers=self._headers(), timeout=8)
            if r.status_code == 200:
                db_title = r.json().get("title", [{}])[0].get("plain_text", "?")
                return {"ok": True, "message": f"Notion OK — DB: {db_title}"}
            return {"ok": False, "message": f"HTTP {r.status_code}: {r.text[:100]}"}
        except Exception as e:
            return {"ok": False, "message": str(e)}


# ── CRM Syncer ────────────────────────────────────────────────────────────────

class CRMSyncer:
    """Sync tới nhiều CRM cùng lúc, collect kết quả từng provider."""

    def __init__(self, providers: list[CRMProvider]):
        self.providers = [p for p in providers if p.is_configured]

    @classmethod
    def from_config(cls, config: dict) -> "CRMSyncer":
        """
        config = {
          "providers": ["hubspot", "notion"],
          "hubspot_api_key":   "...",
          "notion_token":      "...",
          "notion_database_id":"...",
        }
        """
        order = config.get("providers", [])
        registry: dict[str, CRMProvider] = {
            "hubspot": HubSpotProvider(config.get("hubspot_api_key", "")),
            "notion":  NotionProvider(
                config.get("notion_token", ""),
                config.get("notion_database_id", ""),
            ),
        }
        providers = [registry[p] for p in order if p in registry]
        return cls(providers)

    def sync(self, contacts: list[CRMContact]) -> list[SyncResult]:
        results = []
        for provider in self.providers:
            print(f"[crm] Syncing {len(contacts)} contacts → {provider.name}")
            r = provider.sync_contacts(contacts)
            print(f"[crm] {provider.name}: created={r.created} updated={r.updated} errors={len(r.errors)}")
            results.append(r)
        return results

    def status(self) -> list[dict]:
        return [{"name": p.name, "configured": p.is_configured} for p in self.providers]
