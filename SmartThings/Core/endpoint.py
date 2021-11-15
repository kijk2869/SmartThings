from typing import Final, Optional
from .endpoint_client import EndpointClient


class Endpoint:
    def __init__(self, client: EndpointClient) -> None:
        self.client = client

    def locationId(self, id: Optional[str] = None) -> str:
        result: Final = id or self.client.config.locationId
        if result:
            return result
        raise ValueError("Location ID not defined")

    def installedAppId(self, id: Optional[str] = None) -> str:
        result: Final = id or self.client.config.installedAppId
        if result:
            return result
        raise ValueError("Installed App ID not defined")
