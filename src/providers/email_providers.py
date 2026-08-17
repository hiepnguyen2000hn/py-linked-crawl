"""
Email Enrichment Providers — waterfall pattern.

Thứ tự thử: Hunter → Apollo → Snov → Pattern (best-guess)
Mỗi provider implement EmailProvider ABC.
"""
from __future__ import annotations
import os, re, socket, smtplib, unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import requests


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class EmailResult:
    email:        str
    confidence:   int          # 0-100
    source:       str          # provider name
    alternatives: list[str] = field(default_factory=list)
    verified:     bool = False

    def to_dict(self) -> dict:
        return {
            "email":        self.email,
            "confidence":   self.confidence,
            "source":       self.source,
            "alternatives": self.alternatives,
            "verified":     self.verified,
        }


EMPTY_RESULT = EmailResult(email="", confidence=0, source="none")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-zA-Z0-9]", "", text).lower()

def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split()
    if not parts: return ("", "")
    return _slug(parts[-1]), _slug(parts[0])   # first=tên, last=họ

def _clean_domain(domain: str) -> str:
    return domain.strip().lower().lstrip("www.").split("/")[0].split("?")[0]

def _has_mx(domain: str) -> bool:
    try:
        import dns.resolver
        dns.resolver.resolve(domain, "MX"); return True
    except Exception:
        pass
    try: socket.gethostbyname(domain); return True
    except Exception: return False

def _smtp_ping(email: str, domain: str) -> bool:
    try:
        mx = domain
        try:
            import dns.resolver
            records = dns.resolver.resolve(domain, "MX")
            mx = str(sorted(records, key=lambda r: r.preference)[0].exchange).rstrip(".")
        except Exception: pass
        with smtplib.SMTP(mx, 25, timeout=4) as s:
            s.ehlo("probe.local"); s.mail("probe@probe.local")
            code, _ = s.rcpt(email)
            return code == 250
    except Exception: return False


# ── Base class ────────────────────────────────────────────────────────────────

class EmailProvider(ABC):
    name: str = "base"

    @abstractmethod
    def find(self, first: str, last: str, domain: str) -> Optional[EmailResult]:
        """Return EmailResult or None if provider cannot find."""
        ...

    def test_connection(self) -> dict:
        """Return { ok, message } — override per provider."""
        return {"ok": True, "message": "No test available"}

    @property
    def is_configured(self) -> bool:
        return True


# ── Provider: Hunter.io ───────────────────────────────────────────────────────

class HunterProvider(EmailProvider):
    name = "hunter"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("HUNTER_API_KEY", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def find(self, first: str, last: str, domain: str) -> Optional[EmailResult]:
        if not self.api_key: return None
        try:
            r = requests.get("https://api.hunter.io/v2/email-finder", params={
                "domain": domain, "first_name": first, "last_name": last,
                "api_key": self.api_key,
            }, timeout=10)
            data = r.json().get("data", {})
            email = data.get("email", "")
            if not email: return None
            return EmailResult(
                email=email, confidence=data.get("score", 50),
                source="hunter", verified=True,
            )
        except Exception: return None

    def test_connection(self) -> dict:
        if not self.api_key: return {"ok": False, "message": "API key chưa được cấu hình"}
        try:
            r = requests.get("https://api.hunter.io/v2/account",
                             params={"api_key": self.api_key}, timeout=8)
            data = r.json()
            if r.status_code == 200:
                searches = data.get("data", {}).get("requests", {}).get("searches", {})
                used = searches.get("used", "?")
                avail = searches.get("available", "?")
                return {"ok": True, "message": f"Kết nối OK — {used}/{avail} searches đã dùng"}
            return {"ok": False, "message": data.get("errors", [{}])[0].get("details", "Lỗi không xác định")}
        except Exception as e:
            return {"ok": False, "message": str(e)}


# ── Provider: Apollo.io ───────────────────────────────────────────────────────

class ApolloProvider(EmailProvider):
    name = "apollo"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("APOLLO_API_KEY", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def find(self, first: str, last: str, domain: str) -> Optional[EmailResult]:
        if not self.api_key: return None
        try:
            r = requests.post(
                "https://api.apollo.io/v1/people/match",
                headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
                json={"first_name": first, "last_name": last, "domain": domain,
                      "reveal_personal_emails": False},
                timeout=12,
            )
            person = r.json().get("person") or {}
            email = person.get("email", "")
            if not email: return None
            return EmailResult(
                email=email,
                confidence=90 if person.get("email_status") == "verified" else 60,
                source="apollo",
                verified=person.get("email_status") == "verified",
            )
        except Exception: return None

    def test_connection(self) -> dict:
        if not self.api_key: return {"ok": False, "message": "API key chưa được cấu hình"}
        try:
            r = requests.get("https://api.apollo.io/v1/auth/health",
                             headers={"x-api-key": self.api_key}, timeout=8)
            if r.status_code == 200:
                return {"ok": True, "message": "Apollo kết nối OK"}
            return {"ok": False, "message": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"ok": False, "message": str(e)}


# ── Provider: Snov.io ─────────────────────────────────────────────────────────

class SnovProvider(EmailProvider):
    name = "snov"

    def __init__(self, client_id: str = "", client_secret: str = ""):
        self.client_id     = client_id     or os.getenv("SNOV_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("SNOV_CLIENT_SECRET", "")
        self._token: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _get_token(self) -> str:
        if self._token: return self._token
        r = requests.post("https://api.snov.io/v1/oauth/access_token", data={
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }, timeout=8)
        self._token = r.json().get("access_token", "")
        return self._token

    def find(self, first: str, last: str, domain: str) -> Optional[EmailResult]:
        if not self.is_configured: return None
        try:
            token = self._get_token()
            if not token: return None
            r = requests.post("https://api.snov.io/v1/get-emails-by-name",
                json={"firstName": first, "lastName": last, "domain": domain, "limit": 1},
                headers={"Authorization": f"Bearer {token}"}, timeout=10)
            emails = r.json().get("data", {}).get("emails", [])
            if not emails: return None
            best = emails[0]
            return EmailResult(
                email=best.get("email", ""),
                confidence=int(best.get("confidence", 0) * 100),
                source="snov",
                verified=best.get("emailStatus") == "valid",
            )
        except Exception: return None

    def test_connection(self) -> dict:
        if not self.is_configured:
            return {"ok": False, "message": "Client ID/Secret chưa được cấu hình"}
        try:
            token = self._get_token()
            return {"ok": bool(token), "message": "Snov kết nối OK" if token else "Lấy token thất bại"}
        except Exception as e:
            return {"ok": False, "message": str(e)}


# ── Provider: Pattern (no API key needed) ────────────────────────────────────

class PatternProvider(EmailProvider):
    name = "pattern"

    def find(self, first: str, last: str, domain: str) -> Optional[EmailResult]:
        if not first or not domain: return None
        if not _has_mx(domain): return None
        fl = first[0] if first else ""
        patterns = [
            f"{first}@{domain}",
            f"{first}.{last}@{domain}",
            f"{first}{last}@{domain}",
            f"{fl}{last}@{domain}",
            f"{fl}.{last}@{domain}",
        ]
        patterns = [p for p in patterns if "." in p.split("@")[1] and ".@" not in p]

        # SMTP verify top 3
        for email in patterns[:3]:
            if _smtp_ping(email, domain):
                return EmailResult(email=email, confidence=60, source="pattern+smtp", verified=True,
                                   alternatives=[p for p in patterns[1:4] if p != email])

        return EmailResult(email=patterns[0], confidence=20, source="pattern",
                           alternatives=patterns[1:4]) if patterns else None

    def test_connection(self) -> dict:
        return {"ok": True, "message": "Pattern provider luôn sẵn sàng (không cần API key)"}


# ── Waterfall Enricher ────────────────────────────────────────────────────────

class EmailEnricher:
    """
    Thử từng provider theo thứ tự — dừng khi tìm được email confidence >= threshold.
    """
    def __init__(self, providers: list[EmailProvider], min_confidence: int = 30):
        self.providers      = providers
        self.min_confidence = min_confidence

    @classmethod
    def from_config(cls, config: dict) -> "EmailEnricher":
        """
        config = {
          "providers": ["hunter", "apollo", "snov", "pattern"],
          "hunter_api_key": "...",
          "apollo_api_key": "...",
          "snov_client_id": "...",
          "snov_client_secret": "...",
        }
        """
        order = config.get("providers", ["hunter", "apollo", "snov", "pattern"])
        registry: dict[str, EmailProvider] = {
            "hunter":  HunterProvider(config.get("hunter_api_key", "")),
            "apollo":  ApolloProvider(config.get("apollo_api_key", "")),
            "snov":    SnovProvider(config.get("snov_client_id", ""), config.get("snov_client_secret", "")),
            "pattern": PatternProvider(),
        }
        providers = [registry[p] for p in order if p in registry]
        if not providers:
            providers = [PatternProvider()]
        return cls(providers)

    def find(self, full_name: str, domain: str) -> EmailResult:
        domain = _clean_domain(domain)
        first, last = _split_name(full_name)
        for provider in self.providers:
            if not provider.is_configured:
                continue
            result = provider.find(first, last, domain)
            if result and result.email and result.confidence >= self.min_confidence:
                print(f"[email] {full_name}@{domain} → {result.email} ({result.confidence}%) via {result.source}")
                return result
        return EMPTY_RESULT

    def status(self) -> list[dict]:
        return [
            {
                "name":          p.name,
                "configured":    p.is_configured,
                "priority":      i + 1,
            }
            for i, p in enumerate(self.providers)
        ]
