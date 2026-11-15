"""Official lookup websites that the texts tell people to search.

When a text names one of these sites (e.g. 「口腔癌確認診斷及治療醫院名單」), the API
returns a link for it so the frontend can turn that name into a hyperlink. Only
sites a person would go and look something up on are listed here; sources and
citations are never linked.

The handbook (第 65～71 頁) is where these come from. Its own URLs were checked on
2026-11-16; dead ones were replaced by the agency that now runs the service
(oral cancer screening moved from 國健署 to 衛福部口腔健康司 in 2023).
"""

from __future__ import annotations

from typing import Dict, List

NHI_PROVIDER_SEARCH = "https://info.nhi.gov.tw/INAE1000/INAE1000S01"
ORAL_CANCER_HOSPITALS = "https://dep.mohw.gov.tw/DOOH/cp-6543-87456-124.html"

# Each entry: the names that may appear in a text, and where they link to.
LOOKUP_LINKS: List[Dict] = [
    {
        "label": "健保特約醫療機構查詢（衛福部中央健康保險署）",
        "url": NHI_PROVIDER_SEARCH,
        # The handbook also names 國健署's 「全國健保特約醫療機構查詢」; that page is
        # gone, and the NHI search covers the same thing (進階查詢 → 口腔黏膜檢查).
        "names": ["全國健保特約醫療機構查詢", "健保特約醫療機構查詢", "健保特約醫事機構查詢"],
    },
    {
        "label": "口腔癌確認診斷及治療醫院名單（衛福部口腔健康司）",
        "url": ORAL_CANCER_HOSPITALS,
        "names": ["口腔癌確認診斷及治療醫院名單", "確認診斷及治療醫院名單"],
    },
    {
        "label": "菸害防制（衛福部國民健康署）",
        "url": "https://www.hpa.gov.tw/Pages/List.aspx?nodeid=41",
        "names": ["菸害防制"],
    },
    {
        "label": "口腔扁平苔癬病人口腔保健須知（衛福部口腔健康司）",
        "url": "https://dep.mohw.gov.tw/DOOH/cp-6545-71351-124.html",
        "names": ["病人口腔保健須知"],
    },
]


def find_links(*texts: str) -> List[Dict[str, str]]:
    """Links for the lookup sites named in the texts.

    Returns [{"text", "url", "label"}], where "text" is the exact name found, so the
    frontend can turn every occurrence of it into a link. Longer names win, so
    「全國健保特約醫療機構查詢」 is not also matched as 「健保特約醫療機構查詢」.
    """
    joined = "\n".join(texts)
    names = sorted(
        ((name, entry) for entry in LOOKUP_LINKS for name in entry["names"]),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    found: List[Dict[str, str]] = []
    for name, entry in names:
        if name in joined and not any(name in item["text"] for item in found):
            found.append({"text": name, "url": entry["url"], "label": entry["label"]})
    return found
