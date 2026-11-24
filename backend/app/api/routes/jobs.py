from typing import Annotated
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, Request, UploadFile, status
from fastapi.responses import FileResponse

from ...domain.models import TenantPrincipal
from ...schemas.jobs import JobResponse
from ...services.job_service import JobService
from ..dependencies import authenticated_principal, get_job_service

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


def xlsx_result_response(path: Path) -> FileResponse:
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="resultado.xlsx",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("", response_model=JobResponse, status_code=status.HTTP_200_OK)
def create_job(
    request: Request,
    file: Annotated[UploadFile, File()],
    drive_file_id: Annotated[str, Header(alias="X-Drive-File-Id", min_length=1, max_length=1024)],
    principal: Annotated[TenantPrincipal, Depends(authenticated_principal)],
    service: Annotated[JobService, Depends(get_job_service)],
    drive_revision: Annotated[
        str | None, Header(alias="X-Drive-Revision", max_length=255)
    ] = None,
) -> JobResponse:
    job = service.create_job(
        principal=principal,
        drive_file_id=drive_file_id,
        drive_revision=drive_revision,
        upload=file,
    )
    request.state.job_id = job.id
    return JobResponse.from_view(
        job, result_available=service.result_available(job)
    )


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: UUID,
    principal: Annotated[TenantPrincipal, Depends(authenticated_principal)],
    service: Annotated[JobService, Depends(get_job_service)],
) -> JobResponse:
    job = service.get_job(principal, job_id)
    return JobResponse.from_view(
        job, result_available=service.result_available(job)
    )


@router.get("/{job_id}/result")
def get_result(
    job_id: UUID,
    principal: Annotated[TenantPrincipal, Depends(authenticated_principal)],
    service: Annotated[JobService, Depends(get_job_service)],
) -> FileResponse:
    path = service.result_path(principal, job_id)
    return xlsx_result_response(path)
