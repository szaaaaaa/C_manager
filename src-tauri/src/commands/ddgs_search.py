"""Bounded search with a public RSS channel when DDGS returns no usable results."""
import json
import sys
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from ddgs import DDGS


def usable(rows):
    results = []
    seen = set()
    for row in rows:
        url = row.get("url", "")
        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme in ("http", "https") and parsed.hostname
                     and not parsed.username and not parsed.password)
        except ValueError:
            valid = False
        if (not valid or not row.get("title", "").strip()
                or not row.get("content", "").strip() or url in seen):
            continue
        seen.add(url)
        results.append(row)
        if len(results) == 5:
            break
    return results


def bing_rss(query):
    request = Request(
        "https://www.bing.com/search?" + urlencode({"q": query, "format": "rss"}),
        headers={"User-Agent": "C-manager/0.2", "Accept": "application/rss+xml"},
    )
    with urlopen(request, timeout=8) as response:
        data = response.read(1_048_577)
    if len(data) > 1_048_576:
        raise ValueError("搜索响应超过1MiB上限")
    root = ElementTree.fromstring(data)
    return usable([{
        "title": "[Bing RSS] " + (item.findtext("title") or ""),
        "url": item.findtext("link") or "",
        "content": item.findtext("description") or "",
    } for item in root.findall("./channel/item")])


def search(query):
    try:
        # Explicit backends keep the entire search within the Rust 30-second limit.
        rows = DDGS(timeout=8).text(
            query, max_results=5, region="cn-zh", backend="yahoo,duckduckgo",
        )
        results = usable([{"title": row.get("title", ""), "url": row.get("href", ""),
                           "content": row.get("body", "")} for row in rows])
        if results:
            return {"results": results}
        ddgs_error = "没有有效结果（可能受到限流或验证码限制）"
    except Exception as exc:
        ddgs_error = f"{type(exc).__name__}: {str(exc)[:160]}"
    try:
        results = bing_rss(query)
        if not results:
            raise ValueError("没有有效结果")
        return {"results": results}
    except Exception as exc:
        return {"error": f"DDGS：{ddgs_error}；Bing RSS：{type(exc).__name__}: {str(exc)[:160]}"}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(search(sys.argv[1]), ensure_ascii=False))
