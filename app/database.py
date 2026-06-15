from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from urllib.parse import quote_plus

_conn_str = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=(localdb)\\MSSQLLocalDB;"
    "DATABASE=WCGW_Dev_Test;"
    "Trusted_Connection=yes;"
    "Encrypt=no;"
)

SQLALCHEMY_DATABASE_URL = f"mssql+pyodbc:///?odbc_connect={quote_plus(_conn_str)}"

engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Set by main.py after the demo tenant is seeded.
# Every checked-out connection receives the tenant context so RLS returns data.
_tenant_context_id: str | None = None


@event.listens_for(engine, "checkout")
def _set_tenant_context(dbapi_conn, connection_record, connection_proxy):
    if _tenant_context_id:
        cursor = dbapi_conn.cursor()
        cursor.execute(
            "EXEC sp_set_session_context N'tenant_id', ?", _tenant_context_id
        )
        cursor.close()


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
