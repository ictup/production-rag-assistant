import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.workflow import run_support_triage_skeleton
from backend.app.api.security import (
    ApiPrincipal,
    require_api_key,
    require_api_role,
    resolve_workspace_id,
)
from backend.app.api.workspace_validation import (
    get_workspace_repository,
    require_active_workspace,
)
from backend.app.core.request_id import get_request_id
from backend.app.core.tracing import get_trace_id
from backend.app.db.repositories import (
    AgentApprovalRepository,
    SupportTicketRepository,
    WorkspaceRepository,
)
from backend.app.db.session import get_db_session
from backend.app.rag.pipeline import RagPipeline
from backend.app.schemas.agent import (
    AgentApprovalDecisionRequest,
    AgentApprovalResponse,
    AgentApprovalsResponse,
    AgentApprovalStatus,
    AgentTriageResponse,
    SupportTicketRequest,
)

router = APIRouter(prefix="/agent", tags=["agent"])


async def get_agent_rag_pipeline(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RagPipeline:
    return RagPipeline(session=session)


async def get_support_ticket_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SupportTicketRepository:
    return SupportTicketRepository(session=session)


async def get_agent_approval_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AgentApprovalRepository:
    return AgentApprovalRepository(session=session)


@router.post("/support-triage", response_model=AgentTriageResponse)
async def support_triage(
    ticket_request: SupportTicketRequest,
    raw_request: Request,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    rag_pipeline: Annotated[RagPipeline, Depends(get_agent_rag_pipeline)],
    support_ticket_repository: Annotated[
        SupportTicketRepository,
        Depends(get_support_ticket_repository),
    ],
    workspace_repository: Annotated[
        WorkspaceRepository,
        Depends(get_workspace_repository),
    ],
) -> AgentTriageResponse:
    workspace_id = resolve_workspace_id(principal, ticket_request.workspace_id)
    await require_active_workspace(
        workspace_id=workspace_id,
        repository=workspace_repository,
    )
    normalized_request = ticket_request.model_copy(
        update={"workspace_id": workspace_id},
    )
    return await run_support_triage_skeleton(
        normalized_request,
        rag_pipeline=rag_pipeline,
        support_ticket_repository=support_ticket_repository,
        request_id=get_request_id(raw_request),
        trace_id=get_trace_id(),
    )


@router.get("/approvals", response_model=AgentApprovalsResponse)
async def list_agent_approvals(
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    approval_repository: Annotated[
        AgentApprovalRepository,
        Depends(get_agent_approval_repository),
    ],
    workspace_id: Annotated[str | None, Query()] = None,
    approval_status: Annotated[
        AgentApprovalStatus | None,
        Query(alias="status"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AgentApprovalsResponse:
    require_api_role(principal, "operator")
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
    result = await approval_repository.list_agent_approvals(
        workspace_id=normalized_workspace_id,
        status=approval_status,
        limit=limit,
        offset=offset,
    )
    return AgentApprovalsResponse.from_result(
        limit=limit,
        offset=offset,
        result=result,
    )


@router.get("/approvals/{approval_id}", response_model=AgentApprovalResponse)
async def get_agent_approval(
    approval_id: uuid.UUID,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    approval_repository: Annotated[
        AgentApprovalRepository,
        Depends(get_agent_approval_repository),
    ],
    workspace_id: Annotated[str | None, Query()] = None,
) -> AgentApprovalResponse:
    require_api_role(principal, "operator")
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
    approval = await approval_repository.get_agent_approval(
        approval_id=approval_id,
        workspace_id=normalized_workspace_id,
    )
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="agent approval not found",
        )
    return AgentApprovalResponse.from_model(approval)


@router.post(
    "/approvals/{approval_id}/decision",
    response_model=AgentApprovalResponse,
)
async def decide_agent_approval(
    approval_id: uuid.UUID,
    decision_request: AgentApprovalDecisionRequest,
    principal: Annotated[ApiPrincipal, Depends(require_api_key)],
    approval_repository: Annotated[
        AgentApprovalRepository,
        Depends(get_agent_approval_repository),
    ],
    workspace_id: Annotated[str | None, Query()] = None,
) -> AgentApprovalResponse:
    require_api_role(principal, "admin")
    normalized_workspace_id = resolve_workspace_id(principal, workspace_id)
    try:
        approval = await approval_repository.decide_agent_approval(
            approval_id=approval_id,
            workspace_id=normalized_workspace_id,
            decision=decision_request.decision,
            human_feedback=decision_request.human_feedback,
            commit=True,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="agent approval is not pending",
        ) from exc
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="agent approval not found",
        )
    return AgentApprovalResponse.from_model(approval)
