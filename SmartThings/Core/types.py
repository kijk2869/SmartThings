from typing import TypeVar, TypedDict, Optional

T = TypeVar("T")


class Link(TypedDict):
    href: str


class Links(TypedDict):
    next: Optional[Link]
    previous: Optional[Link]
