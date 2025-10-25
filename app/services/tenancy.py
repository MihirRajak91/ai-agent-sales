from app.models.auth import TenantClaims


def build_tenant_namespace(tenant: TenantClaims) -> str:
    """
    Return the Pinecone namespace derived from the tenant identifiers.
    """
    return f"org_{tenant.org_id}__branch_{tenant.branch_id}"
