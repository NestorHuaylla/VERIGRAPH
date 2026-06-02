class ExternalSourceClient:
    async def check_url(self, url: str) -> dict:
        return {"url": url, "sources": {}, "status": "pending"}

