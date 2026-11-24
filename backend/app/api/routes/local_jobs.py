from typing import Annotated, Literal
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse

from ...domain.errors import InvalidUpload
from ...domain.models import TenantPrincipal
from ...schemas.jobs import ExportConfigRequest, ExportResponse, JobResponse, ReviewDecisionRequest, ReviewDecisionResponse, ReviewResponse, ReviewTableResponse
from ...services.job_service import JobService
from ..dependencies import get_job_service
from .jobs import xlsx_result_response

router = APIRouter(prefix="/api/v1/local/jobs", tags=["local-jobs"])
LOCAL_PRINCIPAL = TenantPrincipal("local-pilot")


def source_pdf_response(path: Path) -> FileResponse:
    return FileResponse(
        path,
        media_type="application/pdf",
        filename="source.pdf",
        content_disposition_type="inline",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("", response_model=JobResponse, status_code=status.HTTP_200_OK)
def create_local_job(
    request: Request,
    file: Annotated[UploadFile, File()],
    document_type: Annotated[str, Form()],
    service: Annotated[JobService, Depends(get_job_service)],
) -> JobResponse:
    if document_type != "budget":
        raise InvalidUpload("INVALID_DOCUMENT_TYPE")

    job = service.create_job(
        principal=LOCAL_PRINCIPAL,
        drive_file_id="local-upload",
        drive_revision=None,
        upload=file,
        local_identity=True,
    )
    request.state.job_id = job.id
    return JobResponse.from_view(
        job, result_available=service.result_available(job)
    )


@router.get("/{job_id}", response_model=JobResponse)
def get_local_job(
    job_id: UUID,
    service: Annotated[JobService, Depends(get_job_service)],
) -> JobResponse:
    job = service.get_job(LOCAL_PRINCIPAL, job_id)
    return JobResponse.from_view(
        job, result_available=service.result_available(job)
    )


@router.get("/{job_id}/result")
def get_local_result(
    job_id: UUID,
    service: Annotated[JobService, Depends(get_job_service)],
) -> FileResponse:
    return xlsx_result_response(service.result_path(LOCAL_PRINCIPAL, job_id))


@router.get("/{job_id}/source")
def get_local_source(
    job_id: UUID,
    service: Annotated[JobService, Depends(get_job_service)],
) -> FileResponse:
    return source_pdf_response(service.source_path(LOCAL_PRINCIPAL, job_id))


@router.get("/{job_id}/review", response_model=ReviewResponse)
def get_local_review(
    job_id: UUID,
    response: Response,
    service: Annotated[JobService, Depends(get_job_service)], offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=50),
) -> ReviewResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return ReviewResponse.model_validate(service.review_payload(LOCAL_PRINCIPAL, job_id, offset=offset, limit=limit))


@router.get("/{job_id}/review/table", response_model=ReviewTableResponse)
def get_local_review_table(
    job_id: UUID, response: Response,
    service: Annotated[JobService, Depends(get_job_service)],
    offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=50),
    filter: Literal["pending", "resolved", "all"] = "pending",
) -> ReviewTableResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return ReviewTableResponse.model_validate(service.review_table_payload(LOCAL_PRINCIPAL, job_id, offset=offset, limit=limit, filter_name=filter))


@router.put("/{job_id}/review/decisions", response_model=ReviewDecisionResponse)
def put_local_decisions(job_id: UUID, body: ReviewDecisionRequest, service: Annotated[JobService, Depends(get_job_service)]) -> ReviewDecisionResponse:
    return ReviewDecisionResponse.model_validate(service.save_decisions(LOCAL_PRINCIPAL, job_id, revision=body.review_revision, decisions=[item.model_dump() for item in body.decisions]))


@router.get("/{job_id}/export", response_model=ExportResponse)
def get_local_export(job_id: UUID, response: Response, service: Annotated[JobService, Depends(get_job_service)]) -> ExportResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return ExportResponse.model_validate(service.export_payload(LOCAL_PRINCIPAL, job_id))


@router.put("/{job_id}/export/config", response_model=ExportResponse)
def put_local_export_config(job_id: UUID, body: ExportConfigRequest, service: Annotated[JobService, Depends(get_job_service)]) -> ExportResponse:
    return ExportResponse.model_validate(service.save_export_config(LOCAL_PRINCIPAL, job_id, revision=body.export_revision, columns=[item.model_dump() for item in body.columns]))


@router.post("/{job_id}/export")
def post_local_export(job_id: UUID, service: Annotated[JobService, Depends(get_job_service)]) -> dict[str, bool]:
    service.generate_export(LOCAL_PRINCIPAL, job_id)
    return {"generated": True}


@router.get("/{job_id}/export/result")
def get_local_export_result(job_id: UUID, service: Annotated[JobService, Depends(get_job_service)]) -> FileResponse:
    return xlsx_result_response(service.export_result_path(LOCAL_PRINCIPAL, job_id))
