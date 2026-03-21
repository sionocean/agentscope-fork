import httpx
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock
from config import BRAVE_API_KEY


async def brave_search(query: str, count: int = 5) -> ToolResponse:
    """Search the web using Brave Search API.

    Args:
        query: The search query string.
        count: Number of results to return (max 20, default 5).

    Returns:
        ToolResponse containing search results with titles, URLs and descriptions.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(count, 20)},
            headers={"X-Subscription-Token": BRAVE_API_KEY},
            timeout=15,
        )

    if resp.status_code != 200:
        return ToolResponse(
            content=[TextBlock(type="text", text=f"Search failed: {resp.status_code}")],
        )

    data = resp.json()
    results = data.get("web", {}).get("results", [])

    if not results:
        return ToolResponse(
            content=[TextBlock(type="text", text="No results found.")],
        )

    lines = []
    for r in results:
        lines.append(f"**{r['title']}**")
        lines.append(f"URL: {r['url']}")
        lines.append(f"{r.get('description', '')}")
        lines.append("")

    return ToolResponse(
        content=[TextBlock(type="text", text="\n".join(lines))],
    )
