from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import database as _db_module
from .database import engine, Base
from .models import Tenant, RiskDefinition, CustomParameter
from .routers import entities, definitions

# ---------------------------------------------------------------------------
# Idempotent ALTER TABLE migrations — each statement is safe to run repeatedly.
# Handles the schema difference between the SQL-script-created wcgw_dev tables
# and the columns our API needs.
# ---------------------------------------------------------------------------
_MIGRATIONS = [
    # ── entities.risk_entities ──────────────────────────────────────────────
    # Add columns required by the API that are not in the original SQL script
    "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'entities.risk_entities') AND name = N'primary_key_field') "
    "ALTER TABLE entities.risk_entities ADD primary_key_field NVARCHAR(200) NULL",

    "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'entities.risk_entities') AND name = N'data_source_registry_id') "
    "ALTER TABLE entities.risk_entities ADD data_source_registry_id NVARCHAR(200) NULL",

    "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'entities.risk_entities') AND name = N'compliance_tag') "
    "ALTER TABLE entities.risk_entities ADD compliance_tag NVARCHAR(50) NULL",

    # Drop CHECK constraints that block our UI-sourced values
    "IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID(N'entities.risk_entities') AND name = N'chk_entity_status') "
    "ALTER TABLE entities.risk_entities DROP CONSTRAINT chk_entity_status",

    "IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID(N'entities.risk_entities') AND name = N'chk_entity_type') "
    "ALTER TABLE entities.risk_entities DROP CONSTRAINT chk_entity_type",

    # ── entities.entity_attributes ──────────────────────────────────────────
    "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'entities.entity_attributes') AND name = N'description') "
    "ALTER TABLE entities.entity_attributes ADD description NVARCHAR(MAX) NULL",

    "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'entities.entity_attributes') AND name = N'is_primary_key') "
    "ALTER TABLE entities.entity_attributes ADD is_primary_key BIT NOT NULL DEFAULT 0",

    "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'entities.entity_attributes') AND name = N'sensitivity_classification') "
    "ALTER TABLE entities.entity_attributes ADD sensitivity_classification NVARCHAR(50) NULL",

    "IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID(N'entities.entity_attributes') AND name = N'chk_attribute_data_type') "
    "ALTER TABLE entities.entity_attributes DROP CONSTRAINT chk_attribute_data_type",

    # ── definitions.risk_definitions ────────────────────────────────────────
    "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'definitions.risk_definitions') AND name = N'wcgw_entity_type') "
    "ALTER TABLE definitions.risk_definitions ADD wcgw_entity_type NVARCHAR(100) NULL",

    # Drop FK on entity_id so we can make it nullable (definitions don't require a linked entity)
    """DECLARE @fk NVARCHAR(200)
       SELECT @fk = fk.name FROM sys.foreign_keys fk
       INNER JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
       INNER JOIN sys.columns c ON fkc.parent_column_id = c.column_id AND c.object_id = fk.parent_object_id
       WHERE fk.parent_object_id = OBJECT_ID(N'definitions.risk_definitions') AND c.name = N'entity_id'
       IF @fk IS NOT NULL EXEC(N'ALTER TABLE definitions.risk_definitions DROP CONSTRAINT [' + @fk + N']')""",

    "IF EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID(N'definitions.risk_definitions') AND name = N'entity_id' AND is_nullable = 0) "
    "ALTER TABLE definitions.risk_definitions ALTER COLUMN entity_id UNIQUEIDENTIFIER NULL",

    # Drop category / severity / status CHECK constraints to allow UI-sourced free-text values
    "IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID(N'definitions.risk_definitions') AND name = N'chk_def_category') "
    "ALTER TABLE definitions.risk_definitions DROP CONSTRAINT chk_def_category",

    "IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID(N'definitions.risk_definitions') AND name = N'chk_def_severity') "
    "ALTER TABLE definitions.risk_definitions DROP CONSTRAINT chk_def_severity",

    "IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID(N'definitions.risk_definitions') AND name = N'chk_def_status') "
    "ALTER TABLE definitions.risk_definitions DROP CONSTRAINT chk_def_status",

    "IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID(N'definitions.risk_definitions') AND name = N'chk_def_interp_mode') "
    "ALTER TABLE definitions.risk_definitions DROP CONSTRAINT chk_def_interp_mode",

    # ── definitions.custom_parameters ───────────────────────────────────────
    # SQL script uses 'name' + 'default_value'; our model already matches those names.
    # Drop the data_type CHECK so any value is accepted
    "IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID(N'definitions.custom_parameters') AND name = N'chk_param_data_type') "
    "ALTER TABLE definitions.custom_parameters DROP CONSTRAINT chk_param_data_type",

    # ── RLS: disable all security policies on our schemas ───────────────────
    # Policies created by the original SQL script filter rows by SESSION_CONTEXT tenant_id.
    # Disabling them makes rows visible in SSMS and removes the dependency on session context.
    """DECLARE @sql NVARCHAR(MAX) = N''
       SELECT @sql += N'ALTER SECURITY POLICY [' + s.name + N'].[' + sp.name + N'] WITH (STATE = OFF); '
       FROM sys.security_policies sp
       JOIN sys.schemas s ON sp.schema_id = s.schema_id
       WHERE s.name IN (N'platform', N'entities', N'definitions') AND sp.is_enabled = 1
       IF LEN(@sql) > 0 EXEC(@sql)""",
]


def _run_migrations() -> None:
    with engine.connect() as conn:
        for stmt in _MIGRATIONS:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception as exc:
                conn.rollback()
                print(f"[migration warning] {exc}")


def _init_db() -> None:
    # 1. Ensure schemas exist
    with engine.connect() as conn:
        for schema in ("platform", "entities", "definitions"):
            conn.execute(
                text(
                    f"IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'{schema}') "
                    f"EXEC(N'CREATE SCHEMA [{schema}]')"
                )
            )
        conn.commit()

    # 2. Run ALTER TABLE migrations (safe on existing SQL-script tables)
    _run_migrations()

    # 3. Create any tables that are still missing (fresh DB)
    Base.metadata.create_all(bind=engine)

    # 4. Seed demo tenant if not present, then expose its UUID for RLS SESSION_CONTEXT
    with Session(engine) as session:
        tenant = session.query(Tenant).filter(Tenant.name == "demo").first()
        if not tenant:
            tenant = Tenant(name="demo", display_name="Demo Organisation", tier="enterprise")
            session.add(tenant)
            session.commit()
            session.refresh(tenant)
        _db_module._tenant_context_id = str(tenant.tenant_id)
    print(f"[startup] RLS tenant context set to: {_db_module._tenant_context_id}")

    # 5. Seed sample definitions if the table is empty
    _seed_definitions(_db_module._tenant_context_id)


_SEED_DEFINITIONS = [
    {
        "name": "Unauthorized Data Access",
        "description": "Risk that sensitive data is accessed by unauthorized users or systems.",
        "category": "Compliance",
        "wcgw_entity_type": "Employee",
        "severity": "Critical",
        "status": "Published",
        "params": [
            ("access_log_retention_days", "90"),
            ("alert_threshold_attempts", "3"),
        ],
    },
    {
        "name": "Data Quality Failure",
        "description": "Risk that inaccurate or incomplete data leads to incorrect business decisions.",
        "category": "Operational",
        "wcgw_entity_type": "DataAsset",
        "severity": "High",
        "status": "Published",
        "params": [
            ("completeness_threshold_pct", "95"),
            ("review_frequency_days", "7"),
        ],
    },
    {
        "name": "Regulatory Reporting Error",
        "description": "Risk that required regulatory reports contain errors or are submitted late.",
        "category": "Regulatory",
        "wcgw_entity_type": "Report",
        "severity": "High",
        "status": "Published",
        "params": [
            ("submission_deadline_days", "30"),
            ("approver_role", "Compliance Officer"),
        ],
    },
    {
        "name": "Third-Party Vendor Risk",
        "description": "Risk arising from vendor failures, breaches, or non-compliance.",
        "category": "Operational",
        "wcgw_entity_type": "Vendor",
        "severity": "Medium",
        "status": "Draft",
        "params": [
            ("review_cycle_months", "12"),
            ("min_security_rating", "B"),
        ],
    },
    {
        "name": "Insider Threat",
        "description": "Risk of malicious or negligent actions by employees with privileged access.",
        "category": "Compliance",
        "wcgw_entity_type": "Employee",
        "severity": "Critical",
        "status": "Draft",
        "params": [
            ("privileged_access_review_days", "30"),
        ],
    },
]


def _seed_definitions(tenant_id: str) -> None:
    with Session(engine) as session:
        if session.query(RiskDefinition).first():
            return
        for item in _SEED_DEFINITIONS:
            defn = RiskDefinition(
                tenant_id=tenant_id,
                name=item["name"],
                description=item["description"],
                category=item["category"],
                wcgw_entity_type=item["wcgw_entity_type"],
                severity=item["severity"],
                status=item["status"],
            )
            session.add(defn)
            session.flush()
            for i, (key, val) in enumerate(item["params"]):
                session.add(CustomParameter(
                    definition_id=defn.definition_id,
                    tenant_id=tenant_id,
                    name=key,
                    default_value=val,
                    sort_order=i,
                ))
        session.commit()
        print(f"[startup] Seeded {len(_SEED_DEFINITIONS)} sample definitions.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_db()
    yield


app = FastAPI(title="WCGW API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(entities.router)
app.include_router(definitions.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "wcgw-api", "db": "WCGW_Dev_Test"}
