from typing import Generic, List
from .endpoint_client import EndpointClient
from .types import Links, T
from typing import Optional


class PagedResult(Generic[T]):
    items: List[T]
    _links: Optional[Links]


class PaginatedListIterator(Generic[T]):
    index: int

    def __init__(self, client: EndpointClient, page: PagedResult[T]):
        self.client = client
        self.page = page
        self.index = 0

    async def next(self):
        if self.index < len(self.page.items):
            done = False
            self.index += 1
            value = self.page.items[self.index]
            if self.index == len(self.page.items):
                if self.page._links and (
                    href := self.page._links.get("_next", {}).get("href")
                ):
                    self.index = 0
                    self.page = await self.client.get(href)
                else:
                    done = True
            return {"done": done, "value": value}
        return {"done": True, "value": None}
