from abc import ABC, abstractmethod
from typing import Final
import base64
from dataclasses import dataclass
import aiohttp
from .endpoint_client import EndpointClientConfig, HttpClientHeaders


class AbstractAuthenticator(ABC):
    """
    Implement this interface to implement a process for handling authentication.
    This is not meant to be a "service" in the traditional sense because
    implementors are not expected to be stateless.
    """

    @staticmethod
    @abstractmethod
    async def login():
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    async def logout():
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    async def refresh(headers: HttpClientHeaders, clientConfig: EndpointClientConfig):
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    async def acquireRefreshMutex():
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    async def authenticate(headers: HttpClientHeaders):
        """
        Performs required authentication steps to add credentials to the headers, typically via Bearer Auth headers.
        Expected to call other functions such as @see refresh as needed to return valid credentials.
        """

        raise NotImplementedError

    @staticmethod
    @abstractmethod
    async def authenticateGeneric() -> str:
        """
        Performs required authentication steps and returns credentials as a string value.
        Expected to perform any required steps (such as token refresh) needed to return valid credentials.
        """

        raise NotImplementedError


class NoOpAuthenticator(AbstractAuthenticator):
    """
    For use in tests or on endpoints that don't need any authentication.
    """

    @staticmethod
    async def authenticate(headers: HttpClientHeaders) -> HttpClientHeaders:
        return headers

    @staticmethod
    async def authenticateGeneric() -> str:
        return ""


class BearerTokenAuthenticator(AbstractAuthenticator):
    """
    A simple bearer token authenticator that knows nothing about refreshing
    or logging in our out. If the token is expired, it simply won't work.
    """

    def __init__(self, token: str) -> None:
        self.token = token

    async def authenticate(self, headers: HttpClientHeaders) -> HttpClientHeaders:
        return {**headers, "Authorization": f"Bearer {self.token}"}

    async def authenticateGeneric(self) -> str:
        return self.token


@dataclass
class AuthData:
    authToken: str
    refreshToken: str


@dataclass
class RefreshData:
    refreshToken: str
    clientId: str
    clientSecret: str


class RefreshTokenStore(ABC):
    @staticmethod
    @abstractmethod
    async def getRefreshData() -> RefreshData:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    async def putAuthData(data: AuthData) -> None:
        raise NotImplementedError


class RefreshTokenAuthenticator(AbstractAuthenticator):
    """
    An authenticator that supports refreshing of the access token using a refresh token by loading the refresh token,
    client ID, and client secret from a token store, performing the refresh, and storing the new tokens.
    """

    def __init__(self, token: str, tokenStore: RefreshTokenStore) -> None:
        self.token = token
        self.tokenStore = tokenStore

    async def authenticate(self, headers: HttpClientHeaders) -> HttpClientHeaders:
        return {**headers, "Authorization": f"Bearer {self.token}"}

    async def refresh(
        self, originHeaders: HttpClientHeaders, clientConfig: EndpointClientConfig
    ):
        refreshData: Final[RefreshData] = await self.tokenStore.getRefreshData()
        headers: Final[HttpClientHeaders] = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": "Basic "
            + base64.b64encode(
                f"${refreshData.clientId}:${refreshData.clientSecret}".encode("ascii")
            ).decode(),
            "Accept": "application/json",
        }

        if not clientConfig.urlProvider:
            raise Exception("No URL provider specified")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                clientConfig.urlProvider.authURL,
                headers=headers,
                data={
                    "grant_type": "refresh_token",
                    "client_id": refreshData.clientId,
                    "refresh_token": refreshData.refreshToken,
                },
            ) as resp:
                data = await resp.json()

                if resp.status > 199 and resp.status < 300:
                    authData: Final = AuthData(
                        authToken=data["access_token"],
                        refreshToken=data["refresh_token"],
                    )
                    self.token = authData.authToken
                    originHeaders["Authorization"] = f"Bearer {self.token}"
                    return await self.tokenStore.putAuthData(authData)

                raise Exception(
                    f"error {resp.status} refreshing token, with message {data}"
                )
