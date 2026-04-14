# LinkedIn Lead linkedUrl Enrichment Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Thêm cột `linkedUrl` (= `flagshipProfileUrl`) vào CSV export bằng cách gọi detail API cho từng lead sau khi đã fetch xong toàn bộ list.

**Architecture:**
- Script browser console (không có file, test, hay commit).
- Sau khi `fetchAllLeads()` thu thập đủ `allResults` từ list API, duyệt tuần tự từng lead → gọi detail API (`salesApiProfiles`) → lấy `flagshipProfileUrl` → gán vào `el.flagshipProfileUrl` → rồi mới `exportCSV`.
- Dùng `entityUrn` (có sẵn trong mỗi element) để build URL detail: parse 3 phần `profileId`, `authType`, `authToken`.

**Tech Stack:** Vanilla JS, browser Fetch API, LinkedIn Sales Navigator internal API.

---

## Phân tích entityUrn → URL detail

```
entityUrn = "urn:li:fs_salesProfile:(ACwAAAtabtsBein6Dlx9RX1KwCPWK_ptQNaPro4,NAME_SEARCH,F1yk)"
                                       └── profileId ──────────────────────────  └─authType─  └authToken
```

URL detail:
```
https://www.linkedin.com/sales-api/salesApiProfiles/(profileId:ACwAAAtabtsBein6Dlx9RX1KwCPWK_ptQNaPro4,authType:NAME_SEARCH,authToken:F1yk)?decoration=%28flagshipProfileUrl%29
```

Decoration tối giản: `%28flagshipProfileUrl%29` = `(flagshipProfileUrl)` — chỉ lấy field cần thiết, response nhỏ, nhanh hơn.

---

### Task 1: Thêm hàm `parseEntityUrn`

Thêm vào đầu script, sau `getCsrfToken`.

```js
function parseEntityUrn(entityUrn) {
  // "urn:li:fs_salesProfile:(profileId,authType,authToken)"
  const match = entityUrn?.match(/\(([^,)]+),([^,)]+),([^,)]*)\)/);
  if (!match) return null;
  return { profileId: match[1], authType: match[2], authToken: match[3] };
}
```

Kiểm tra nhanh trong console:
```js
parseEntityUrn("urn:li:fs_salesProfile:(ACwAAAtabtsBein6Dlx9RX1KwCPWK_ptQNaPro4,NAME_SEARCH,F1yk)")
// → { profileId: "ACwAAAtabtsBein6Dlx9RX1KwCPWK_ptQNaPro4", authType: "NAME_SEARCH", authToken: "F1yk" }
```

---

### Task 2: Thêm hàm `fetchFlagshipUrl`

Gọi detail API, chỉ decode `flagshipProfileUrl`. Trả `''` nếu lỗi để không chặn flow.

```js
async function fetchFlagshipUrl(entityUrn, csrfToken) {
  const parsed = parseEntityUrn(entityUrn);
  if (!parsed) return '';
  const { profileId, authType, authToken } = parsed;
  const url = `https://www.linkedin.com/sales-api/salesApiProfiles/(profileId:${profileId},authType:${authType},authToken:${authToken})?decoration=%28flagshipProfileUrl%29`;
  try {
    const res = await fetch(url, {
      headers: {
        'accept': '*/*',
        'csrf-token': csrfToken,
        'x-li-lang': 'en_US',
        'x-restli-protocol-version': '2.0.0',
      },
      credentials: 'include',
    });
    if (!res.ok) return '';
    const data = await res.json();
    return data.flagshipProfileUrl ?? '';
  } catch {
    return '';
  }
}
```

---

### Task 3: Cập nhật `mapLead` — thêm field `linkedUrl`

```js
function mapLead(el) {
  const pos         = el.currentPositions?.[0] ?? {};
  const companyId   = pos.companyUrn?.split(':').pop() ?? '';
  const salesNavUrl = el.entityUrn
    ? `https://www.linkedin.com/sales/lead/${encodeURIComponent(el.entityUrn)}`
    : '';
  const avatar = el.profilePictureDisplayImage?.artifacts?.find(a => a.width === 200)
    ?? el.profilePictureDisplayImage?.artifacts?.[0];
  const profilePictureUrl = avatar
    ? `${el.profilePictureDisplayImage.rootUrl}${avatar.fileIdentifyingUrlPathSegment}`
    : '';

  return {
    firstName:         el.firstName ?? '',
    lastName:          el.lastName ?? '',
    fullName:          el.fullName ?? '',
    job_title:         pos.title ?? '',
    location:          el.geoRegion ?? '',
    country:           el.geoRegion?.includes(',') ? el.geoRegion.split(',').pop().trim() : el.geoRegion ?? '',
    salesNavigatorUrl: salesNavUrl,
    linkedUrl:         el.flagshipProfileUrl ?? '',   // ← MỚI
    company_name:      pos.companyName ?? '',
    company_linkedin:  companyId ? `https://www.linkedin.com/company/${companyId}` : '',
    premium:           el.premium ? 'true' : 'false',
    openToWork:        el.openToOpportunities ? 'true' : 'false',
    occupation:        el.summary?.split('\n')[0]?.slice(0, 100) ?? '',
    profilePicture:    profilePictureUrl,
    entityUrn:         el.entityUrn ?? '',
    importDate:        new Date().toISOString().split('T')[0],
  };
}
```

---

### Task 4: Cập nhật `fetchAllLeads` — enrich từng lead sau khi fetch xong list

Thêm bước enrich **sau vòng lặp while**, **trước khi gọi `exportCSV`**.

```js
async function fetchAllLeads() {
  const COUNT = 25;
  let start = 0, allResults = [], totalFound = null;

  let csrfToken;
  try { csrfToken = getCsrfToken(); }
  catch (e) { console.error(e.message); return; }

  console.log('csrf-token:', csrfToken);

  // --- Phase 1: fetch list ---
  while (true) {
    const url = `https://www.linkedin.com/sales-api/salesApiLeadSearch?q=searchQuery&query=...&start=${start}&count=${COUNT}&...`;

    const res = await fetch(url, {
      headers: {
        'accept': '*/*',
        'csrf-token': csrfToken,
        'x-li-lang': 'en_US',
        'x-restli-protocol-version': '2.0.0',
      },
      credentials: 'include',
    });

    if (!res.ok) { console.error(`HTTP ${res.status}`, await res.text()); break; }

    const data = await res.json();

    if (totalFound === null) {
      totalFound = data.paging?.total ?? 0;
      console.log(`Total leads: ${totalFound}`);
    }

    const elements = data.elements ?? [];
    allResults.push(...elements);
    console.log(`Fetched ${allResults.length} / ${totalFound}`);

    if (elements.length === 0 || allResults.length >= totalFound) break;

    start += COUNT;
    await new Promise(r => setTimeout(r, 1000));
  }

  // --- Phase 2: enrich linkedUrl cho từng lead ---
  console.log(`Enriching ${allResults.length} leads with linkedUrl...`);
  for (let i = 0; i < allResults.length; i++) {
    const el = allResults[i];
    el.flagshipProfileUrl = await fetchFlagshipUrl(el.entityUrn, csrfToken);
    console.log(`[${i + 1}/${allResults.length}] ${el.fullName} → ${el.flagshipProfileUrl || '(no url)'}`);
    await new Promise(r => setTimeout(r, 600)); // tránh rate limit
  }

  console.log('Done! Exporting CSV...');
  exportCSV(allResults);
  return allResults;
}
```

**Lưu ý rate limit:**
- 600ms giữa mỗi detail call là safe. Nếu bị 429, tăng lên 1000–1500ms.
- Không dùng parallel vì LinkedIn sẽ block nhanh.

---

## Tóm tắt thay đổi

| Hàm | Thay đổi |
|---|---|
| `parseEntityUrn` (mới) | Parse `entityUrn` → `{profileId, authType, authToken}` |
| `fetchFlagshipUrl` (mới) | Gọi detail API, trả `flagshipProfileUrl` hoặc `''` |
| `mapLead` | Thêm `linkedUrl: el.flagshipProfileUrl ?? ''` |
| `fetchAllLeads` | Sau phase list → phase enrich → export |

## Thứ tự cột CSV (sau thay đổi)

```
firstName, lastName, fullName, job_title, location, country,
salesNavigatorUrl, linkedUrl, company_name, company_linkedin,
premium, openToWork, occupation, profilePicture, entityUrn, importDate
```

## Rủi ro & xử lý

| Rủi ro | Xử lý |
|---|---|
| Detail API 429 rate limit | `try/catch` → `''`, tăng delay nếu cần |
| `entityUrn` format lạ | `parseEntityUrn` trả `null` → `fetchFlagshipUrl` trả `''` |
| `flagshipProfileUrl` vắng trong response | `?? ''` |
| Mạng yếu / timeout | `try/catch` trong `fetchFlagshipUrl` → `''` |