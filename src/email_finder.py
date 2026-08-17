"""
Email Finder — tìm email công việc từ tên + domain công ty.

Chiến lược:
  1. Hunter.io API (nếu có HUNTER_API_KEY)
  2. Sinh pattern email phổ biến + verify bằng SMTP check nhẹ
  3. Ghi kết quả vào sheet cột "Email_Found", "Email_Confidence"
"""
import os
import re
import socket
import smtplib
import unicodedata
import requests
from typing import Optional


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    """Chuyển tiếng Việt / unicode → ASCII slug viết thường."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-zA-Z0-9]", "", text).lower()
    return text


def _split_name(full_name: str) -> tuple[str, str]:
    """Trả về (first, last) từ full name. Xử lý cả tên Việt (họ đứng đầu)."""
    parts = full_name.strip().split()
    if not parts:
        return ("", "")
    # Tên Việt: họ ở đầu, tên ở cuối
    first = _slug(parts[-1])
    last  = _slug(parts[0])
    return first, last


def _email_patterns(first: str, last: str, domain: str) -> list[tuple[str, str]]:
    """Sinh danh sách (email, pattern_name) phổ biến."""
    if not first or not domain:
        return []
    fl = first[0] if first else ""
    ll = last[0]  if last  else ""
    candidates = [
        (f"{first}@{domain}",                "first"),
        (f"{first}.{last}@{domain}",          "first.last"),
        (f"{first}{last}@{domain}",           "firstlast"),
        (f"{fl}{last}@{domain}",              "flast"),
        (f"{fl}.{last}@{domain}",             "f.last"),
        (f"{last}.{first}@{domain}",          "last.first"),
        (f"{last}{first}@{domain}",           "lastfirst"),
        (f"{first}_{last}@{domain}",          "first_last"),
    ]
    # Bỏ dòng có first/last rỗng
    return [(e, p) for e, p in candidates if "@" in e and ".@" not in e and "__@" not in e]


# ── MX check ─────────────────────────────────────────────────────────────────

def _has_mx(domain: str) -> bool:
    """Kiểm tra domain có MX record không (không cần thư viện ngoài)."""
    try:
        import dns.resolver  # dnspython nếu có
        dns.resolver.resolve(domain, "MX")
        return True
    except Exception:
        pass
    # Fallback: socket lookup
    try:
        socket.gethostbyname(domain)
        return True
    except Exception:
        return False


def _smtp_verify(email: str, domain: str) -> bool:
    """
    SMTP RCPT verify nhẹ — chỉ dùng khi không có Hunter key.
    Không gửi thư thật, chỉ check RCPT TO.
    Nhiều server chặn => chỉ coi là "heuristic".
    """
    try:
        mx_host = domain  # fallback nếu không resolve được MX
        try:
            import dns.resolver
            records = dns.resolver.resolve(domain, "MX")
            mx_host = str(sorted(records, key=lambda r: r.preference)[0].exchange).rstrip(".")
        except Exception:
            pass

        with smtplib.SMTP(mx_host, 25, timeout=5) as smtp:
            smtp.ehlo("check.local")
            smtp.mail("noreply@check.local")
            code, _ = smtp.rcpt(email)
            return code == 250
    except Exception:
        return False


# ── Hunter.io ────────────────────────────────────────────────────────────────

def _hunter_find(first: str, last: str, domain: str, api_key: str) -> Optional[dict]:
    """
    Gọi Hunter.io /email-finder.
    Trả về { email, score, sources } hoặc None.
    """
    url = "https://api.hunter.io/v2/email-finder"
    params = {
        "domain":     domain,
        "first_name": first,
        "last_name":  last,
        "api_key":    api_key,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json().get("data", {})
        email = data.get("email")
        if email:
            return {
                "email":      email,
                "confidence": data.get("score", 0),
                "source":     "hunter",
            }
    except Exception:
        pass
    return None


def _hunter_verify(email: str, api_key: str) -> int:
    """Trả về score (0-100) từ Hunter.io /email-verifier."""
    url = "https://api.hunter.io/v2/email-verifier"
    try:
        resp = requests.get(url, params={"email": email, "api_key": api_key}, timeout=10)
        return resp.json().get("data", {}).get("score", 0)
    except Exception:
        return 0


# ── Public API ────────────────────────────────────────────────────────────────

def find_email(full_name: str, domain: str) -> dict:
    """
    Tìm email tốt nhất cho (full_name, domain).

    Returns:
        {
            "email":      str | "",
            "confidence": int,   # 0-100
            "source":     str,   # "hunter" | "pattern" | "smtp" | "none"
            "alternatives": list[str]
        }
    """
    domain  = domain.strip().lower().lstrip("www.").split("/")[0]
    api_key = os.getenv("HUNTER_API_KEY", "")
    first, last = _split_name(full_name)

    # ── 1. Hunter.io ─────────────────────────────────────────────────────────
    if api_key:
        result = _hunter_find(first, last, domain, api_key)
        if result:
            return {**result, "alternatives": []}

    # ── 2. Pattern generation ─────────────────────────────────────────────────
    if not _has_mx(domain):
        return {"email": "", "confidence": 0, "source": "none", "alternatives": []}

    patterns = _email_patterns(first, last, domain)
    if not patterns:
        return {"email": "", "confidence": 0, "source": "none", "alternatives": []}

    # ── 3. SMTP verify từng pattern (tối đa 3 cái đầu) ───────────────────────
    verified_email = ""
    alternatives   = []
    for email, pname in patterns[:3]:
        if _smtp_verify(email, domain):
            if not verified_email:
                verified_email = email
            else:
                alternatives.append(email)

    if verified_email:
        return {
            "email":        verified_email,
            "confidence":   60,
            "source":       "smtp",
            "alternatives": alternatives,
        }

    # ── 4. Trả pattern đầu tiên với confidence thấp (best guess) ─────────────
    best_email = patterns[0][0]
    return {
        "email":        best_email,
        "confidence":   20,
        "source":       "pattern",
        "alternatives": [e for e, _ in patterns[1:4]],
    }


def find_emails_batch(rows: list[dict], name_col: str = "fullName", domain_col: str = "domain") -> list[dict]:
    """
    Tìm email cho danh sách rows.
    Mỗi row cần có: name_col (tên), domain_col (domain website công ty).
    Trả về list kết quả: [{index, email, confidence, source}]
    """
    results = []
    for i, row in enumerate(rows):
        name   = str(row.get(name_col, "") or "").strip()
        domain = str(row.get(domain_col, "") or "").strip()
        if not name or not domain:
            results.append({"index": i, "email": "", "confidence": 0, "source": "skip"})
            continue
        result = find_email(name, domain)
        results.append({"index": i, **result})
        print(f"[email-finder] [{i+1}/{len(rows)}] {name} @ {domain} → {result['email']} ({result['confidence']}%)")
    return results
