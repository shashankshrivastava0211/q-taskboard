import os
import time
from typing import Any, Callable, Protocol

from django.conf import settings

from .airtable_mock import PermanentAirtableError, TransientAirtableError
from .models import Project, Task


class AirtableClient(Protocol):
    def create(self, fields: dict) -> dict: ...
    def update(self, record_id: str, fields: dict) -> dict: ...


def _task_fields(task: Task, project_name: str) -> dict:
    notes_lines = [
        f'Task ID: {task.id}',
        f'Status: {task.status}',
        f'Assignee: {task.assignee.email if task.assignee_id else ""}',
        f'Project: {project_name}',
    ]
    if task.description:
        notes_lines.append(f'Description: {task.description}')
    return {
        'Name': task.title,
        'Notes': '\n'.join(notes_lines),
    }


def call_with_retry(fn: Callable[[], Any], *, retries: int = 3, delay: float = 0.05) -> Any:
    """Retry transient failures; do not retry permanent failures."""
    attempt = 0
    while True:
        try:
            return fn()
        except TransientAirtableError:
            if attempt >= retries:
                raise
            time.sleep(delay * (2 ** attempt))
            attempt += 1


def resolve_airtable_config() -> tuple[str, str, str]:
    api_key = (getattr(settings, 'AIRTABLE_API_KEY', None) or os.environ.get('AIRTABLE_API_KEY') or '').strip()
    raw_base = (getattr(settings, 'AIRTABLE_BASE_ID', None) or os.environ.get('AIRTABLE_BASE_ID') or '').strip()
    table_name = (getattr(settings, 'AIRTABLE_TABLE_NAME', None) or os.environ.get('AIRTABLE_TABLE_NAME') or 'Tasks').strip()

    base_id = raw_base
    if '/' in raw_base:
        parts = [p for p in raw_base.split('/') if p]
        if parts:
            base_id = parts[0]
        if len(parts) > 1 and parts[1].startswith('tbl'):
            table_name = parts[1]

    return api_key, base_id, table_name


class PyAirtableClient:
    """Thin wrapper around pyairtable with transient/permanent error mapping."""

    def __init__(self, api_key: str, base_id: str, table_name: str):
        from pyairtable import Api, retry_strategy
        import requests

        self._HTTPError = requests.exceptions.HTTPError
        retry = retry_strategy(status_forcelist=(429, 500, 502, 503, 504), total=5)
        api = Api(api_key, retry_strategy=retry)
        self._table = api.table(base_id, table_name)

    def create(self, fields: dict) -> dict:
        try:
            return self._table.create(fields)
        except self._HTTPError as exc:
            raise self._map_error(exc) from exc

    def update(self, record_id: str, fields: dict) -> dict:
        try:
            return self._table.update(record_id, fields)
        except self._HTTPError as exc:
            raise self._map_error(exc) from exc

    def _map_error(self, exc: Exception) -> Exception:
        status = getattr(exc, 'status_code', None)
        if status is None:
            response = getattr(exc, 'response', None)
            status = getattr(response, 'status_code', None)
        if status in (429, 500, 502, 503, 504):
            return TransientAirtableError(str(exc))
        return PermanentAirtableError(str(exc))


def get_airtable_client() -> AirtableClient:
    api_key, base_id, table_name = resolve_airtable_config()
    if not api_key or not base_id:
        raise PermanentAirtableError('Airtable is not configured')
    return PyAirtableClient(api_key, base_id, table_name)


def export_project_tasks(
    project: Project,
    tasks,
    client: AirtableClient | None = None,
) -> dict:
    """
    Export all tasks for a project to Airtable.

    Idempotent via Task.airtable_record_id (create once, update on re-export).
    One record failure does not abort the rest of the export.
    """
    if client is None:
        client = get_airtable_client()

    exported = 0
    updated = 0
    created = 0
    failed: list[dict] = []

    for task in tasks:
        fields = _task_fields(task, project.name)
        try:
            if task.airtable_record_id:
                record_id = task.airtable_record_id
                try:
                    call_with_retry(lambda rid=record_id, f=fields: client.update(rid, f))
                    updated += 1
                except PermanentAirtableError:
                    record = call_with_retry(lambda f=fields: client.create(f))
                    task.airtable_record_id = record['id']
                    task.save(update_fields=['airtable_record_id', 'updated_at'])
                    created += 1
            else:
                record = call_with_retry(lambda f=fields: client.create(f))
                task.airtable_record_id = record['id']
                task.save(update_fields=['airtable_record_id', 'updated_at'])
                created += 1
            exported += 1
        except (TransientAirtableError, PermanentAirtableError) as exc:
            failed.append({'task_id': str(task.id), 'error': str(exc)})
        except Exception as exc:  # noqa: BLE001 — isolate unexpected per-record failures
            failed.append({'task_id': str(task.id), 'error': str(exc)})

    return {
        'exported': exported,
        'created': created,
        'updated': updated,
        'failed': failed,
    }
