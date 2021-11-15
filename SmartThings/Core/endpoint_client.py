from dataclasses import dataclass
import json
from typing import (
    Any,
    Dict,
    Generic,
    Iterable,
    List,
    Literal,
    Optional,
    TypedDict,
    Union,
    Final,
)
import contextlib

import aiohttp
from .authenticator import AbstractAuthenticator
from .types import T, Links
from copy import copy
import logging

HttpClientHeaders = Dict[str, str]
HttpClientParamValue = Union[str, Iterable[str], int]
HttpClientParams = Dict[str, HttpClientParamValue]
HttpClientMethod = Literal[
    "get", "GET", "post", "POST", "put", "PUT", "patch", "PATCH", "delete", "DELETE"
]


@dataclass
class SmartThingsURLProvider:
    baseURL: str
    authURL: str
    keyApiURL: str


defaultSmartThingsURLProvider: Final = SmartThingsURLProvider(
    baseURL="https://api.smartthings.com",
    authURL="https://auth-global.api.smartthings.com/oauth/token",
    keyApiURL="https://key.smartthings.com",
)


@dataclass
class EndpointClientConfig:
    authenticator: AbstractAuthenticator
    urlProvider: Optional[SmartThingsURLProvider] = None
    loggingId: Optional[str] = None
    version: Optional[str] = None
    headers: Optional[HttpClientHeaders] = None
    locationId: Optional[str] = None
    installedAppId: Optional[str] = None


class ItemsList(TypedDict):
    items: List[Any]
    _links: Optional[Links]


class EndpointClientRequestOptions(Generic[T]):
    headerOverrides: Optional[HttpClientHeaders]
    dryRun: Optional[bool]
    dryRunReturnValue: Optional[T]


class EndpointClient:
    logger = logging.getLogger("SmartThings.EndpointClient")

    def __init__(self, basePath: str, config: EndpointClientConfig) -> None:
        self.basePath = basePath
        self.config = config

    def setHeader(self, name: str, value: str) -> "EndpointClient":
        if not self.config.headers:
            self.config.headers = {}

        self.config.headers[name] = value
        return self

    def removeHeader(self, name: str) -> "EndpointClient":
        if self.config.headers:
            del self.config.headers[name]
        return self

    def __url(self, path: Optional[str]) -> str:
        if not self.config.urlProvider:
            raise Exception("No URL provider specified")

        if path:
            if path.startswith("/"):
                return f"{self.config.urlProvider.baseURL}{path}"
            elif path.startswith("https://"):
                return path
            return f"{self.config.urlProvider.baseURL}/{self.basePath}/{path}"
        return f"{self.config.urlProvider.baseURL}/{self.basePath}"

    async def request(
        self,
        method: HttpClientMethod,
        path: Optional[str] = None,
        params: Optional[HttpClientParams] = None,
        options: Optional[EndpointClientRequestOptions] = None,
        **kwargs,
    ):
        headers: HttpClientHeaders = (
            copy(self.config.headers) if self.config.headers else {}
        )

        if self.config.loggingId:
            headers["X-ST-CORRELATION"] = self.config.loggingId

        if self.config.version:
            versionString: Final = (
                f"application/vnd.smartthings+json;v={self.config.version}"
            )

            # Prepare the accept header
            if "Accept" not in headers or headers["Accept"] == "application/json":
                headers["Accept"] = versionString
            else:
                headers["Accept"] = f"{versionString}, {headers['Accept']}"

        if options and options.headerOverrides:
            headers.update(options.headerOverrides)

        headers = await self.config.authenticator.authenticate(headers)

        if options and options.dryRun:
            if options.dryRunReturnValue:
                return options.dryRunReturnValue
            raise Exception("skipping request; dry run mode")

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method, self.__url(path), headers=headers, params=params, **kwargs
            ) as resp:
                data = await resp.json()

                if 200 <= resp.status < 300:
                    return data

                if resp.status == 401:
                    try:
                        release = await self.config.authenticator.acquireRefreshMutex()
                    except NotImplementedError:
                        release = None

                    with contextlib.suppress(NotImplementedError):
                        await self.config.authenticator.refresh(headers, self.config)

                        async with session.request(
                            method,
                            self.__url(path),
                            headers=headers,
                            params=params,
                            **kwargs,
                        ) as resp:
                            return await resp.json()

                    if release:
                        release()

                raise Exception(json.dumps(data))  # TODO: refactor this line

    async def get(
        self,
        path: Optional[str] = None,
        params: Optional[HttpClientParams] = None,
        options: Optional[EndpointClientRequestOptions] = None,
    ):
        return await self.request("GET", path, params, options)

    async def post(
        self,
        path: Optional[str] = None,
        data: Optional[Any] = None,
        params: Optional[HttpClientParams] = None,
        options: Optional[EndpointClientRequestOptions] = None,
    ):
        return await self.request("POST", path, params, options, data=data)

    async def put(
        self,
        path: Optional[str] = None,
        data: Optional[Any] = None,
        params: Optional[HttpClientParams] = None,
        options: Optional[EndpointClientRequestOptions] = None,
    ):
        return await self.request("PUT", path, params, options, data=data)

    async def patch(
        self,
        path: Optional[str] = None,
        data: Optional[Any] = None,
        params: Optional[HttpClientParams] = None,
        options: Optional[EndpointClientRequestOptions] = None,
    ):
        return await self.request("PATCH", path, params, options, data=data)

    async def delete(
        self,
        path: Optional[str] = None,
        data: Optional[Any] = None,
        params: Optional[HttpClientParams] = None,
        options: Optional[EndpointClientRequestOptions] = None,
    ):
        return await self.request("DELETE", path, params, options, data=data)

    async def getPagedItems(
        self,
        path: Optional[str] = None,
        params: Optional[HttpClientParams] = None,
        options: Optional[EndpointClientRequestOptions] = None,
    ):
        itemsList: ItemsList = await self.get(path, params, options)
        result = itemsList["items"]
        while itemsList["_links"] and itemsList["_links"]["next"]:
            itemsList = await self.get(
                itemsList["_links"]["next"]["href"], None, options
            )
            result.extend(itemsList["items"])
        return result
