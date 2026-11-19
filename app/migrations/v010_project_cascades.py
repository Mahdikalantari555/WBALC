"""Make `DELETE /projects/{id}` remove the scene/research records of that project.

The ORM already cascades the Phase 1-2 children through explicit relationships.
Phases 3-5 added tables whose rows only carried a `project_id` foreign key, so a
project delete used to leave orphaned analyses, fusions and research records
behind. Nothing is altered in the tables themselves: the cascade is declared on
the relationship, and this migration only re-creates the indexes it relies on
(none are dropped). It exists so the schema version records the behaviour change.
"""

from __future__ import annotations


async def upgrade(connection) -> None:
    # The cascade is enforced by SQLAlchemy at the ORM level, so there is no DDL
    # to run. Keeping the step makes the cascade an explicit, versioned change
    # rather than a silent behavioural difference between schema versions.
    return None
