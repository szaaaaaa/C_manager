import importlib.util
import io
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

spec = importlib.util.spec_from_file_location("search", Path(__file__).with_name("ddgs_search.py"))
search = importlib.util.module_from_spec(spec)
spec.loader.exec_module(search)

query = "ext4.vhdx 用途 site:learn.microsoft.com"
row = {"title": "WSL", "href": "https://learn.microsoft.com/wsl", "body": "Virtual disk"}
with patch.object(search, "DDGS") as client, patch.object(search, "urlopen") as rss:
    client.return_value.text.return_value = [row]
    assert search.search(query)["results"][0]["url"] == row["href"]
    rss.assert_not_called()

xml = b"<rss><channel><item><title>Disk</title><link>https://example.org/disk</link><description>Disk guide</description></item></channel></rss>"
for failure in (RuntimeError("rate limited"), []):
    with patch.object(search, "DDGS") as client, patch.object(search, "urlopen", return_value=io.BytesIO(xml)) as rss:
        if isinstance(failure, Exception):
            client.return_value.text.side_effect = failure
        else:
            client.return_value.text.return_value = failure
        result = search.search(query)["results"][0]
        assert result["title"] == "[Bing RSS] Disk"
        assert result["content"] == "Disk guide"
        sent = parse_qs(urlsplit(rss.call_args.args[0].full_url).query)
        assert sent["q"] == [query]

with patch.object(search, "DDGS") as client, patch.object(search, "urlopen", side_effect=TimeoutError("timed out")):
    client.return_value.text.side_effect = RuntimeError("rate limited")
    result = search.search(query)
    assert "results" not in result
    assert "rate limited" in result["error"] and "timed out" in result["error"]

for bad_response in (b"<html>challenge</html>", b"<rss>", b"x" * 1_048_577):
    with patch.object(search, "DDGS") as client, patch.object(search, "urlopen", return_value=io.BytesIO(bad_response)):
        client.return_value.text.return_value = []
        assert "error" in search.search(query)

rows = [{"title": "bad", "url": u, "content": "text"} for u in
        ("file:///C:/secret", "javascript:alert(1)", "https://user:pass@example.org/")]
assert search.usable(rows) == []
valid = {"title": "ok", "url": "https://example.org/", "content": "text"}
assert search.usable([valid, valid]) == [valid]
print("PASS: DDGS success, empty/failed search fallback, exact query, provenance, total failure, invalid/oversized RSS, URL validation")
