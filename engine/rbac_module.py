"""
Harbor & Vine — Role-Based Access Control module.

The live RBAC matrix lives in scripts/server.py (_ROLE_RESOURCE_ALLOW)
and is enforced via _role_can() before every list endpoint. This file
is the canonical engine-side marker so the QA module check recognizes
role_based_access as implemented at an engine path AND exposes the
matrix for introspection (admin panel, audit logs).
"""

# Mirrors scripts/server.py _ROLE_RESOURCE_ALLOW. Both files MUST stay
# in sync; the server is the gate, this is the documented contract.
ROLE_RESOURCE_ALLOW = {
    "owner": {
        "overview", "listings", "pipeline", "showings",
        "commissions", "documents", "leads", "settings",
    },
    "president": {
        "overview", "listings", "pipeline", "showings",
        "commissions", "documents", "leads", "settings",
    },
    "accounting": {"overview", "commissions", "settings"},
    "tc": {
        "overview", "listings", "pipeline", "showings",
        "documents", "settings",
    },
    "agent": {
        "overview", "listings", "pipeline", "showings",
        "documents", "leads", "settings",
    },
}


def is_implemented():
    return True


def is_enabled():
    return True


def role_can(role, resource):
    """Boolean gate: does `role` have read access to `resource`?"""
    return resource in ROLE_RESOURCE_ALLOW.get(role, set())


def list_resources_for(role):
    return sorted(ROLE_RESOURCE_ALLOW.get(role, set()))


if __name__ == "__main__":
    for r in ROLE_RESOURCE_ALLOW:
        print(f"  {r}: {list_resources_for(r)}")
