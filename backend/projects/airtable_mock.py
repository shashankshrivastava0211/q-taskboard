# Test double for Airtable — use in unit tests, not in production code.


class TransientAirtableError(Exception):
    """Retryable Airtable failure (rate limit / 5xx)."""


class PermanentAirtableError(Exception):
    """Non-retryable Airtable failure (4xx other than 429)."""


class MockAirtableClient:
    def __init__(self):
        self.records = {}
        self.create_calls = 0
        self.update_calls = 0
        self.fail_on_create_titles = set()
        self.transient_failures_before_success = 0
        self._next_id = 1

    def create(self, fields: dict) -> dict:
        title = fields.get('Name') or fields.get('Title')
        if title in self.fail_on_create_titles:
            raise PermanentAirtableError(f'permanent failure for {title}')
        if self.transient_failures_before_success > 0:
            self.transient_failures_before_success -= 1
            raise TransientAirtableError('rate limited')
        self.create_calls += 1
        record_id = f'recMOCK{self._next_id:04d}'
        self._next_id += 1
        self.records[record_id] = {'id': record_id, 'fields': dict(fields)}
        return self.records[record_id]

    def update(self, record_id: str, fields: dict) -> dict:
        if record_id not in self.records:
            raise PermanentAirtableError(f'record not found: {record_id}')
        if self.transient_failures_before_success > 0:
            self.transient_failures_before_success -= 1
            raise TransientAirtableError('rate limited')
        self.update_calls += 1
        self.records[record_id]['fields'] = dict(fields)
        return self.records[record_id]
