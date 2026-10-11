import json, sys
from ddgs import DDGS
sys.stdout.reconfigure(encoding="utf-8")
try:
    results = DDGS(timeout=8).text(sys.argv[1], max_results=5, region="cn-zh")
    output = {"results": [{"title": r.get("title", ""), "url": r.get("href", ""), "content": r.get("body", "")} for r in results]}
except Exception as exc:
    output = {"error": f"DDGS {type(exc).__name__}: {str(exc)[:200]}"}
print(json.dumps(output, ensure_ascii=False))
