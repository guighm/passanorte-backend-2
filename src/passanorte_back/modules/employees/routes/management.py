"""HTTP routes of the ``employees`` module (contracts/employees.md; US4/US5).

Admin-only panel endpoints (require_admin — FR-008) mounted on the
canonical router (prefix /api/v1/employees).
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from passanorte_back.core.db import get_session
from passanorte_back.core.routers import MODULE_ROUTERS
from passanorte_back.modules.auth.services.security import (
    AuthenticatedUser,
    require_admin,
)
from passanorte_back.modules.employees.schemas import (
    EmployeeCreatedResponse,
    EmployeeCreateRequest,
    EmployeeListResponse,
    EmployeeUpdateRequest,
    EmployeeView,
)
from passanorte_back.modules.employees.services.management import (
    DuplicateUsernameError,
    EmployeeMissingError,
    StatusTransitionError,
    create_employee,
    revoke_employee,
    update_employee,
)

router = MODULE_ROUTERS["employees"]


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="employee not found")


@router.post("", response_model=EmployeeCreatedResponse, status_code=status.HTTP_201_CREATED)
def post_employee(
    payload: EmployeeCreateRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> EmployeeCreatedResponse:
    """Create an employee (system-generated one-time initial password —
    clar. Q3-s4; 409 on globally taken username — FR-011)."""
    try:
        employee, initial_password = create_employee(
            session, actor=admin.username, name=payload.name, username=payload.username
        )
    except DuplicateUsernameError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return EmployeeCreatedResponse.from_internal(
        id=employee.id,
        name=employee.name,
        username=employee.username,
        status=employee.status,
        created_at=employee.created_at,
        updated_at=employee.updated_at,
        initial_password=initial_password,
    )


@router.get("", response_model=EmployeeListResponse)
def get_employee_list(
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> EmployeeListResponse:
    from passanorte_back.modules.employees.services import list_employees

    employees = list_employees(session)
    return EmployeeListResponse(
        items=[EmployeeView.model_validate(employee) for employee in employees],
        total=len(employees),
    )


@router.get("/{employee_id}", response_model=EmployeeView)
def get_employee_detail(
    employee_id: int,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> EmployeeView:
    from passanorte_back.modules.employees.services import get_employee

    employee = get_employee(session, employee_id)
    if employee is None:
        raise _not_found()
    return EmployeeView.model_validate(employee)


@router.patch("/{employee_id}", response_model=EmployeeView)
def patch_employee(
    employee_id: int,
    payload: EmployeeUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> EmployeeView:
    """Edit data; reactivates when status=active (clar. Q3-s3; 422 when
    status=revoked is attempted here — revoke is route-only)."""
    try:
        employee = update_employee(
            session,
            actor=admin.username,
            employee_id=employee_id,
            name=payload.name,
            username=payload.username,
            status=payload.status,
        )
    except EmployeeMissingError as error:
        raise _not_found() from error
    except DuplicateUsernameError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except StatusTransitionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    return EmployeeView.model_validate(employee)


@router.post("/{employee_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def post_employee_revoke(
    employee_id: int,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_admin)],
) -> None:
    """Revoke access (idempotent; effective immediately — FR-013)."""
    try:
        revoke_employee(session, actor=admin.username, employee_id=employee_id)
    except EmployeeMissingError as error:
        raise _not_found() from error
