from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...dependencies import get_repository
from ...schemas import CustomerMerge, CustomerMutationOut, CustomerOut, CustomerUpsert, StatusResponse


router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("", response_model=list[CustomerOut])
def customers() -> list[CustomerOut]:
    return [CustomerOut.model_validate(item) for item in get_repository().get_profiles_map().values()]


@router.post("", response_model=CustomerMutationOut)
def create_customer(payload: CustomerUpsert) -> CustomerMutationOut:
    repository = get_repository()
    data = payload.model_dump()
    data["name"] = payload.name
    saved = repository.save_profile(data)
    return CustomerMutationOut.model_validate({"customer": saved, "bootstrap": repository.bootstrap_payload()})


@router.put("/{customer_id}", response_model=CustomerMutationOut)
def update_customer(customer_id: int, payload: CustomerUpsert) -> CustomerMutationOut:
    repository = get_repository()
    data = payload.model_dump()
    data["id"] = customer_id
    data["name"] = payload.name
    saved = repository.save_profile(data)
    return CustomerMutationOut.model_validate({"customer": saved, "bootstrap": repository.bootstrap_payload()})


@router.post("/{customer_id}/merge", response_model=StatusResponse)
def merge_customer(customer_id: int, payload: CustomerMerge) -> StatusResponse:
    try:
        get_repository().merge_customers(customer_id, payload.source_customer_ids)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return StatusResponse(status="merged")


@router.delete("/{customer_id}", response_model=StatusResponse)
def delete_customer(customer_id: int) -> StatusResponse:
    repository = get_repository()
    with repository.engine.begin() as connection:
        connection.execute(repository.customers.delete().where(repository.customers.c.id == customer_id))
    return StatusResponse(status="deleted")
