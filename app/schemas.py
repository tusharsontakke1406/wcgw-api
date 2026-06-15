from __future__ import annotations
from pydantic import BaseModel
from typing import Optional, List


class AttributeSchema(BaseModel):
    id: Optional[str] = None
    name: str
    dataType: str = "STRING"
    description: Optional[str] = None
    isRequired: bool = False
    isPrimaryKey: bool = False
    sensitivityClassification: str = "INTERNAL"
    defaultValue: Optional[str] = None


class EntityCreate(BaseModel):
    name: str
    type: str
    description: Optional[str] = None
    primaryKey: str
    dataOwner: str
    complianceTag: str = "NONE"
    dataSourceRegistryId: str
    status: str = "DRAFT"
    attributes: List[AttributeSchema] = []


class EntityUpdate(EntityCreate):
    pass


class EntityResponse(BaseModel):
    id: str
    name: str
    type: str
    description: Optional[str] = None
    primaryKey: str
    dataOwner: str
    complianceTag: str
    dataSourceRegistryId: str
    status: str
    version: int
    createdAt: str
    updatedAt: str
    attributes: List[AttributeSchema]


class EntityStats(BaseModel):
    total: int
    published: int
    draft: int
    pendingApproval: int


class CustomParamSchema(BaseModel):
    id: Optional[str] = None
    key: str
    value: str


class DefinitionCreate(BaseModel):
    name: str
    description: str = ""
    category: str = "Operational"
    wcgwEntity: str = ""
    severity: str = "Medium"
    status: str = "Draft"
    customParams: List[CustomParamSchema] = []


class DefinitionUpdate(DefinitionCreate):
    pass


class DefinitionResponse(BaseModel):
    id: str
    name: str
    description: str
    category: str
    wcgwEntity: str
    severity: str
    status: str
    version: int
    customParams: List[CustomParamSchema]
    createdAt: str
    updatedAt: str
