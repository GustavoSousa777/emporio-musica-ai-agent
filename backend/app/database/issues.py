"""Registro de inconsistências encontradas durante ingestão e validação."""
from __future__ import annotations

from dataclasses import dataclass, field

SEVERITIES = ("error", "warning", "info")


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str
    entity: str
    entity_id: str | None
    message: str


@dataclass
class IssueLog:
    issues: list[Issue] = field(default_factory=list)

    def add(self, code: str, severity: str, entity: str, entity_id: object, message: str) -> None:
        assert severity in SEVERITIES, severity
        self.issues.append(
            Issue(code, severity, entity, None if entity_id is None else str(entity_id), message)
        )

    def by_severity(self, severity: str) -> list[Issue]:
        return [i for i in self.issues if i.severity == severity]

    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)
