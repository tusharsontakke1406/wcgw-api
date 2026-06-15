from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List

from ..database import get_db
from ..models import RiskEntity, EntityAttribute, Tenant
from ..schemas import EntityCreate, EntityUpdate, EntityResponse, EntityStats, AttributeSchema

router = APIRouter(prefix="/api/entities", tags=["entities"])


def _get_demo_tenant_id(db: Session) -> str:
    tenant = db.query(Tenant).filter(Tenant.name == "demo").first()
    if not tenant:
        raise HTTPException(status_code=500, detail="Demo tenant not initialised")
    return tenant.tenant_id


def _fmt_dt(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z" if dt else ""


def _to_response(entity: RiskEntity) -> EntityResponse:
    return EntityResponse(
        id=str(entity.entity_id),
        name=entity.name,
        type=entity.entity_type,
        description=entity.description,
        primaryKey=entity.primary_key_field or "",
        dataOwner=entity.data_owner,
        complianceTag=entity.compliance_tag or "NONE",
        dataSourceRegistryId=entity.data_source_registry_id or "",
        status=entity.status,
        version=entity.current_version,
        createdAt=_fmt_dt(entity.created_at),
        updatedAt=_fmt_dt(entity.updated_at),
        attributes=[
            AttributeSchema(
                id=str(a.attribute_id),
                name=a.name,
                dataType=a.data_type,
                description=a.description,
                isRequired=bool(a.required),          # DB column: 'required'
                isPrimaryKey=bool(a.is_primary_key),
                sensitivityClassification=a.sensitivity_classification or "INTERNAL",
                defaultValue=a.default_value,
            )
            for a in entity.attributes
        ],
    )


@router.get("", response_model=List[EntityResponse])
def list_entities(
    search: Optional[str] = None,
    status: Optional[str] = None,
    compliance: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(RiskEntity)
    if search:
        term = f"%{search}%"
        q = q.filter(
            RiskEntity.name.ilike(term)
            | RiskEntity.data_owner.ilike(term)
            | RiskEntity.entity_type.ilike(term)
        )
    if status:
        q = q.filter(RiskEntity.status == status)
    if compliance:
        q = q.filter(RiskEntity.compliance_tag == compliance)
    return [_to_response(e) for e in q.order_by(RiskEntity.updated_at.desc()).all()]


@router.get("/stats", response_model=EntityStats)
def get_stats(db: Session = Depends(get_db)):
    all_entities = db.query(RiskEntity).all()
    return EntityStats(
        total=len(all_entities),
        published=sum(1 for e in all_entities if e.status == "Published"),
        draft=sum(1 for e in all_entities if e.status == "Draft"),
        pendingApproval=sum(1 for e in all_entities if e.status == "Pending Approval"),
    )


@router.get("/{entity_id}", response_model=EntityResponse)
def get_entity(entity_id: str, db: Session = Depends(get_db)):
    entity = db.query(RiskEntity).filter(RiskEntity.entity_id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return _to_response(entity)


@router.post("", response_model=EntityResponse, status_code=201)
def create_entity(payload: EntityCreate, db: Session = Depends(get_db)):
    tenant_id = _get_demo_tenant_id(db)
    entity = RiskEntity(
        tenant_id=tenant_id,
        name=payload.name,
        entity_type=payload.type,
        description=payload.description,
        primary_key_field=payload.primaryKey,
        data_owner=payload.dataOwner,
        compliance_tag=payload.complianceTag,
        data_source_registry_id=payload.dataSourceRegistryId,
        status=payload.status,
    )
    db.add(entity)
    db.flush()

    for i, attr in enumerate(payload.attributes):
        db.add(
            EntityAttribute(
                entity_id=entity.entity_id,
                tenant_id=tenant_id,
                name=attr.name,
                data_type=attr.dataType,
                description=attr.description,
                required=attr.isRequired,           # DB column: 'required'
                is_primary_key=attr.isPrimaryKey,
                sensitivity_classification=attr.sensitivityClassification,
                default_value=attr.defaultValue,
                sort_order=i,
            )
        )

    db.commit()
    db.refresh(entity)
    return _to_response(entity)


@router.put("/{entity_id}", response_model=EntityResponse)
def update_entity(entity_id: str, payload: EntityUpdate, db: Session = Depends(get_db)):
    entity = db.query(RiskEntity).filter(RiskEntity.entity_id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity.name = payload.name
    entity.entity_type = payload.type
    entity.description = payload.description
    entity.primary_key_field = payload.primaryKey
    entity.data_owner = payload.dataOwner
    entity.compliance_tag = payload.complianceTag
    entity.data_source_registry_id = payload.dataSourceRegistryId
    entity.status = payload.status
    entity.current_version = (entity.current_version or 1) + 1

    for attr in list(entity.attributes):
        db.delete(attr)
    db.flush()

    tenant_id = entity.tenant_id
    for i, attr in enumerate(payload.attributes):
        db.add(
            EntityAttribute(
                entity_id=entity.entity_id,
                tenant_id=tenant_id,
                name=attr.name,
                data_type=attr.dataType,
                description=attr.description,
                required=attr.isRequired,           # DB column: 'required'
                is_primary_key=attr.isPrimaryKey,
                sensitivity_classification=attr.sensitivityClassification,
                default_value=attr.defaultValue,
                sort_order=i,
            )
        )

    db.commit()
    db.refresh(entity)
    return _to_response(entity)


@router.delete("/{entity_id}", status_code=204)
def delete_entity(entity_id: str, db: Session = Depends(get_db)):
    entity = db.query(RiskEntity).filter(RiskEntity.entity_id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    db.delete(entity)
    db.commit()
