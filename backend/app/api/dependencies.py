from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from ..domain.models import TenantPrincipal
from ..security import authenticate_token

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_job_service(request: Request):
    return request.app.state.job_service


def authenticated_principal(
    request: Request,
    token: Annotated[str | None, Depends(api_key_header)],
) -> TenantPrincipal:
    principal = getattr(request.state, "principal", None)
    if principal is not None:
        return principal
    return authenticate_token(token, request.app.state.settings)
