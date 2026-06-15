from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List

from ..database import get_db
from ..models import RiskDefinition, CustomParameter, Tenant
from ..schemas import DefinitionCreate, DefinitionUpdate, DefinitionResponse, CustomParamSchema

router = APIRouter(prefix="/api/definitions", tags=["definitions"])


def _get_demo_tenant_id(db: Session) -> str:
    tenant = db.query(Tenant).filter(Tenant.name == "demo").first()
    if not tenant:
        raise HTTPException(status_code=500, detail="Demo tenant not initialised")
    return tenant.tenant_id


def _fmt_dt(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if dt else ""


def _to_response(d: RiskDefinition) -> DefinitionResponse:
    return DefinitionResponse(
        id=str(d.definition_id),
        name=d.name,
        description=d.description or "",
        category=d.category,
        wcgwEntity=d.wcgw_entity_type or "",
        severity=d.severity,
        status=d.status,
        version=d.version,
        customParams=[
            CustomParamSchema(
                id=str(p.parameter_id),
                key=p.name,            # DB column 'name' maps to UI 'key'
                value=p.default_value or "",  # DB column 'default_value' maps to UI 'value'
            )
            for p in d.custom_parameters
        ],
        createdAt=_fmt_dt(d.created_at),
        updatedAt=_fmt_dt(d.updated_at),
    )


@router.get("", response_model=List[DefinitionResponse])
def list_definitions(search: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(RiskDefinition)
    if search:
        term = f"%{search}%"
        q = q.filter(
            RiskDefinition.name.ilike(term)
            | RiskDefinition.category.ilike(term)
            | RiskDefinition.description.ilike(term)
            | RiskDefinition.wcgw_entity_type.ilike(term)
        )
    return [_to_response(d) for d in q.order_by(RiskDefinition.updated_at.desc()).all()]


@router.get("/{definition_id}", response_model=DefinitionResponse)
def get_definition(definition_id: str, db: Session = Depends(get_db)):
    d = db.query(RiskDefinition).filter(RiskDefinition.definition_id == definition_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Definition not found")
    return _to_response(d)


@router.post("", response_model=DefinitionResponse, status_code=201)
def create_definition(payload: DefinitionCreate, db: Session = Depends(get_db)):
    tenant_id = _get_demo_tenant_id(db)
    d = RiskDefinition(
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
        category=payload.category,
        wcgw_entity_type=payload.wcgwEntity,
        severity=payload.severity,
        status=payload.status,
    )
    db.add(d)
    db.flush()

    for i, p in enumerate(payload.customParams):
        db.add(
            CustomParameter(
                definition_id=d.definition_id,
                tenant_id=tenant_id,
                name=p.key,              # UI 'key' → DB 'name'
                default_value=p.value,   # UI 'value' → DB 'default_value'
                sort_order=i,
            )
        )

    db.commit()
    db.refresh(d)
    return _to_response(d)


@router.put("/{definition_id}", response_model=DefinitionResponse)
def update_definition(definition_id: str, payload: DefinitionUpdate, db: Session = Depends(get_db)):
    d = db.query(RiskDefinition).filter(RiskDefinition.definition_id == definition_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Definition not found")

    d.name = payload.name
    d.description = payload.description
    d.category = payload.category
    d.wcgw_entity_type = payload.wcgwEntity
    d.severity = payload.severity
    d.status = payload.status
    d.version = (d.version or 1) + 1

    for p in list(d.custom_parameters):
        db.delete(p)
    db.flush()

    for i, p in enumerate(payload.customParams):
        db.add(
            CustomParameter(
                definition_id=d.definition_id,
                tenant_id=d.tenant_id,
                name=p.key,
                default_value=p.value,
                sort_order=i,
            )
        )

    db.commit()
    db.refresh(d)
    return _to_response(d)


@router.post("/{definition_id}/publish", response_model=DefinitionResponse)
def publish_definition(definition_id: str, db: Session = Depends(get_db)):
    d = db.query(RiskDefinition).filter(RiskDefinition.definition_id == definition_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Definition not found")
    d.status = "Published"
    db.commit()
    db.refresh(d)
    return _to_response(d)


@router.delete("/{definition_id}", status_code=204)
def delete_definition(definition_id: str, db: Session = Depends(get_db)):
    d = db.query(RiskDefinition).filter(RiskDefinition.definition_id == definition_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Definition not found")
    db.delete(d)
    db.commit()
