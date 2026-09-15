"""Single source of truth for role-aware policy discovery paths."""
from __future__ import annotations


DISCOVERY_PATHS = (
    "theme_search",
    "department_documents",
    "normative_documents",
    "application_notices",
    "award_publicity",
    "invalidity_catalog",
    "document_graph",
)
CORE_DISCOVERY_PATHS = (
    "theme_search",
    "department_documents",
    "normative_documents",
    "invalidity_catalog",
)
ROLE_DISCOVERY_PATHS = {
    "primary_regulator": ("application_notices",),
    "funding_authority": ("application_notices", "award_publicity"),
    "application_authority": ("application_notices",),
    "execution_authority": ("application_notices",),
    "co_issuer": (),
    "provincial_counterpart": (),
    "municipal_counterpart": (),
}
DEPARTMENT_ROLES = frozenset(ROLE_DISCOVERY_PATHS)


def required_paths_for_role(role: str) -> tuple[str, ...]:
    """Return only material evidence routes for the department role."""
    return tuple(dict.fromkeys((*CORE_DISCOVERY_PATHS, *ROLE_DISCOVERY_PATHS.get(role, ()))))


def required_paths_for_roles(roles: set[str]) -> tuple[str, ...]:
    required: list[str] = []
    for role in roles:
        required.extend(required_paths_for_role(role))
    return tuple(path for path in DISCOVERY_PATHS if path in set(required))
