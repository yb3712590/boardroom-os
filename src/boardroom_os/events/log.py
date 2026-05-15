from collections.abc import Iterable

from boardroom_os.events.record import EventRecord
from boardroom_os.events.types import EventType, ProjectRef


class EventLogAppendError(ValueError):
    pass


class InMemoryEventLog:
    def __init__(self, events: Iterable[EventRecord] = ()) -> None:
        self._events: list[EventRecord] = []
        self._event_ids: set[str] = set()
        self._latest_graph_versions_by_project: dict[str, int] = {}
        for event in events:
            self.append(event)

    def append(self, event: EventRecord) -> None:
        if not isinstance(event.event_type, EventType):
            raise EventLogAppendError("event_type must be a known EventType")

        event_id = event.event_id.value
        if event_id in self._event_ids:
            raise EventLogAppendError(f"event_id already exists: {event_id}")

        project_ref = event.project_ref.value
        latest_graph_version = self._latest_graph_versions_by_project.get(project_ref, 0)
        if event.graph_version <= latest_graph_version:
            raise EventLogAppendError(
                "graph_version must strictly increase within the same project_ref"
            )

        self._events.append(event)
        self._event_ids.add(event_id)
        self._latest_graph_versions_by_project[project_ref] = event.graph_version

    def read(
        self,
        project_ref: ProjectRef,
        *,
        from_graph_version: int | None = None,
        to_graph_version: int | None = None,
    ) -> tuple[EventRecord, ...]:
        matching_events = [
            event
            for event in self._events
            if event.project_ref == project_ref
            and (
                from_graph_version is None
                or event.graph_version >= from_graph_version
            )
            and (to_graph_version is None or event.graph_version <= to_graph_version)
        ]
        return tuple(sorted(matching_events, key=lambda event: event.graph_version))
