import pytest
from rest_framework.test import APIClient
from users.models import User
from projects.models import Project, Membership, Task


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(email='meera@taskboard.dev', name='Meera Iyer', password='password123')


@pytest.fixture
def auth_client(client, user):
    response = client.post('/api/auth/login', {
        'email': 'meera@taskboard.dev',
        'password': 'password123',
    }, format='json')
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['token']}")
    return client


@pytest.mark.django_db
class TestProjects:
    def test_create_project(self, auth_client, user):
        response = auth_client.post('/api/projects', {'name': 'My Project'}, format='json')
        assert response.status_code == 201
        assert response.data['project']['name'] == 'My Project'

    def test_list_only_returns_member_projects(self, auth_client, user):
        p1 = Project.objects.create(name='Mine', owner=user)
        Membership.objects.create(user=user, project=p1, role='admin')
        other = User.objects.create_user(email='other@example.com', name='Other', password='password123')
        p2 = Project.objects.create(name='Not Mine', owner=other)
        Membership.objects.create(user=other, project=p2, role='admin')

        response = auth_client.get('/api/projects')
        assert response.status_code == 200
        names = [p['name'] for p in response.data['projects']]
        assert 'Mine' in names
        assert 'Not Mine' not in names

    def test_get_project_detail(self, auth_client, user):
        project = Project.objects.create(name='My Project', owner=user)
        Membership.objects.create(user=user, project=project, role='admin')

        response = auth_client.get(f'/api/projects/{project.id}')
        assert response.status_code == 200
        assert response.data['project']['name'] == 'My Project'

    def test_non_member_cannot_view_project(self, client, user):
        owner = User.objects.create_user(email='owner@example.com', name='Owner', password='password123')
        project = Project.objects.create(name='Private', owner=owner)
        Membership.objects.create(user=owner, project=project, role='admin')

        resp = client.post('/api/auth/login', {'email': 'meera@taskboard.dev', 'password': 'password123'}, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")

        response = client.get(f'/api/projects/{project.id}')
        assert response.status_code == 403


@pytest.mark.django_db
class TestTasks:
    def test_create_task(self, auth_client, user):
        project = Project.objects.create(name='P', owner=user)
        Membership.objects.create(user=user, project=project, role='admin')

        response = auth_client.post(f'/api/projects/{project.id}/tasks', {'title': 'Do a thing'}, format='json')
        assert response.status_code == 201
        assert response.data['task']['title'] == 'Do a thing'

    def test_viewers_cannot_create_tasks(self, client, user):
        owner = User.objects.create_user(email='owner@example.com', name='Owner', password='password123')
        project = Project.objects.create(name='P', owner=owner)
        Membership.objects.create(user=owner, project=project, role='admin')
        Membership.objects.create(user=user, project=project, role='viewer')

        resp = client.post('/api/auth/login', {'email': 'meera@taskboard.dev', 'password': 'password123'}, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")

        response = client.post(f'/api/projects/{project.id}/tasks', {'title': 'A task'}, format='json')
        assert response.status_code == 403

    def test_delete_task_requires_membership(self, client, user):
        owner = User.objects.create_user(email='owner@example.com', name='Owner', password='password123')
        project = Project.objects.create(name='P', owner=owner)
        Membership.objects.create(user=owner, project=project, role='admin')
        task = Task.objects.create(project=project, title='A task', created_by=owner)

        resp = client.post('/api/auth/login', {'email': 'meera@taskboard.dev', 'password': 'password123'}, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")

        response = client.delete(f'/api/tasks/{task.id}')
        assert response.status_code == 403

    def test_search_returns_matching_tasks_in_own_project(self, auth_client, user):
        project = Project.objects.create(name='Mine', owner=user)
        Membership.objects.create(user=user, project=project, role='admin')
        Task.objects.create(project=project, title='Set up analytics dashboards', created_by=user)
        Task.objects.create(project=project, title='Draft press release', created_by=user)

        response = auth_client.get(f'/api/projects/{project.id}/tasks', {'q': 'analytics'})
        assert response.status_code == 200
        titles = [t['title'] for t in response.data['tasks']]
        assert titles == ['Set up analytics dashboards']

    def test_search_injection_cannot_leak_other_project_tasks(self, auth_client, user):
        mine = Project.objects.create(name='Mine', owner=user)
        Membership.objects.create(user=user, project=mine, role='admin')
        Task.objects.create(project=mine, title='My only task', created_by=user)

        other = User.objects.create_user(email='other@example.com', name='Other', password='password123')
        theirs = Project.objects.create(name='Theirs', owner=other)
        Membership.objects.create(user=other, project=theirs, role='admin')
        Task.objects.create(project=theirs, title='Secret other project task', created_by=other)

        response = auth_client.get(
            f'/api/projects/{mine.id}/tasks',
            {'q': "x') OR 1=1 --"},
        )
        assert response.status_code == 200
        titles = [t['title'] for t in response.data['tasks']]
        assert 'Secret other project task' not in titles
        assert all(str(t['project_id']) == str(mine.id) for t in response.data['tasks'])


@pytest.mark.django_db
class TestComments:
    def test_member_can_post_and_list_chronologically(self, auth_client, user):
        project = Project.objects.create(name='P', owner=user)
        Membership.objects.create(user=user, project=project, role='admin')
        task = Task.objects.create(project=project, title='A task', created_by=user)

        first = auth_client.post(
            f'/api/tasks/{task.id}/comments',
            {'body': 'First note'},
            format='json',
        )
        assert first.status_code == 201
        assert first.data['comment']['body'] == 'First note'
        assert first.data['comment']['author']['email'] == 'meera@taskboard.dev'
        assert 'created_at' in first.data['comment']

        second = auth_client.post(
            f'/api/tasks/{task.id}/comments',
            {'body': 'Second note'},
            format='json',
        )
        assert second.status_code == 201

        listed = auth_client.get(f'/api/tasks/{task.id}/comments')
        assert listed.status_code == 200
        bodies = [c['body'] for c in listed.data['comments']]
        assert bodies == ['First note', 'Second note']

    def test_viewer_can_read_but_not_post(self, client, user):
        owner = User.objects.create_user(email='owner@example.com', name='Owner', password='password123')
        project = Project.objects.create(name='P', owner=owner)
        Membership.objects.create(user=owner, project=project, role='admin')
        Membership.objects.create(user=user, project=project, role='viewer')
        task = Task.objects.create(project=project, title='A task', created_by=owner)
        from projects.models import Comment
        Comment.objects.create(task=task, author=owner, body='Owner note')

        resp = client.post('/api/auth/login', {
            'email': 'meera@taskboard.dev',
            'password': 'password123',
        }, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")

        listed = client.get(f'/api/tasks/{task.id}/comments')
        assert listed.status_code == 200
        assert [c['body'] for c in listed.data['comments']] == ['Owner note']

        posted = client.post(
            f'/api/tasks/{task.id}/comments',
            {'body': 'Viewer attempt'},
            format='json',
        )
        assert posted.status_code == 403

    def test_non_member_cannot_read_or_post(self, client, user):
        owner = User.objects.create_user(email='owner@example.com', name='Owner', password='password123')
        project = Project.objects.create(name='P', owner=owner)
        Membership.objects.create(user=owner, project=project, role='admin')
        task = Task.objects.create(project=project, title='A task', created_by=owner)

        resp = client.post('/api/auth/login', {
            'email': 'meera@taskboard.dev',
            'password': 'password123',
        }, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")

        assert client.get(f'/api/tasks/{task.id}/comments').status_code == 403
        assert client.post(
            f'/api/tasks/{task.id}/comments',
            {'body': 'Nope'},
            format='json',
        ).status_code == 403

    def test_comments_are_append_only(self, auth_client, user):
        project = Project.objects.create(name='P', owner=user)
        Membership.objects.create(user=user, project=project, role='admin')
        task = Task.objects.create(project=project, title='A task', created_by=user)
        created = auth_client.post(
            f'/api/tasks/{task.id}/comments',
            {'body': 'Keep me'},
            format='json',
        )
        comment_id = created.data['comment']['id']

        assert auth_client.patch(
            f'/api/tasks/{task.id}/comments',
            {'body': 'edited'},
            format='json',
        ).status_code == 405
        assert auth_client.delete(f'/api/tasks/{task.id}/comments').status_code == 405
        assert auth_client.patch(
            f'/api/tasks/{comment_id}',
            {'body': 'edited'},
            format='json',
        ).status_code == 404
        assert auth_client.delete(f'/api/tasks/{comment_id}').status_code == 404


@pytest.mark.django_db
class TestExport:
    def test_viewer_cannot_export(self, client, user):
        owner = User.objects.create_user(email='owner@example.com', name='Owner', password='password123')
        project = Project.objects.create(name='P', owner=owner)
        Membership.objects.create(user=owner, project=project, role='admin')
        Membership.objects.create(user=user, project=project, role='viewer')

        resp = client.post('/api/auth/login', {
            'email': 'meera@taskboard.dev',
            'password': 'password123',
        }, format='json')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['token']}")

        response = client.post(f'/api/projects/{project.id}/export')
        assert response.status_code == 403

    def test_member_export_is_idempotent_with_mock_client(self, auth_client, user, monkeypatch):
        from projects.airtable_mock import MockAirtableClient
        from projects.airtable_export import export_project_tasks, call_with_retry

        mock = MockAirtableClient()
        monkeypatch.setattr('projects.airtable_export.get_airtable_client', lambda: mock)
        monkeypatch.setattr(
            'projects.airtable_export.call_with_retry',
            lambda fn, retries=3, delay=0.05: call_with_retry(fn, retries=retries, delay=0),
        )

        project = Project.objects.create(name='P', owner=user)
        Membership.objects.create(user=user, project=project, role='member')
        t1 = Task.objects.create(project=project, title='Task one', created_by=user)
        Task.objects.create(project=project, title='Task two', created_by=user)

        first = auth_client.post(f'/api/projects/{project.id}/export')
        assert first.status_code == 200
        assert first.data['exported'] == 2
        assert first.data['created'] == 2
        assert first.data['updated'] == 0
        assert first.data['failed'] == []
        assert mock.create_calls == 2

        t1.refresh_from_db()
        assert t1.airtable_record_id

        second = auth_client.post(f'/api/projects/{project.id}/export')
        assert second.status_code == 200
        assert second.data['exported'] == 2
        assert second.data['created'] == 0
        assert second.data['updated'] == 2
        assert mock.update_calls == 2
        assert len(mock.records) == 2

    def test_partial_failure_does_not_abort_export(self, user):
        from projects.airtable_mock import MockAirtableClient
        from projects.airtable_export import export_project_tasks

        project = Project.objects.create(name='P', owner=user)
        good = Task.objects.create(project=project, title='Good task', created_by=user)
        bad = Task.objects.create(project=project, title='Bad task', created_by=user)

        mock = MockAirtableClient()
        mock.fail_on_create_titles.add('Bad task')

        result = export_project_tasks(
            project,
            Task.objects.filter(project=project).order_by('created_at'),
            client=mock,
        )
        assert result['exported'] == 1
        assert result['created'] == 1
        assert len(result['failed']) == 1
        assert result['failed'][0]['task_id'] == str(bad.id)
        good.refresh_from_db()
        bad.refresh_from_db()
        assert good.airtable_record_id
        assert bad.airtable_record_id is None

    def test_retries_transient_errors_then_succeeds(self, user):
        from projects.airtable_mock import MockAirtableClient
        from projects.airtable_export import export_project_tasks
        import projects.airtable_export as export_mod

        project = Project.objects.create(name='P', owner=user)
        task = Task.objects.create(project=project, title='Flaky task', created_by=user)

        mock = MockAirtableClient()
        mock.transient_failures_before_success = 2

        original = export_mod.call_with_retry
        export_mod.call_with_retry = lambda fn, retries=3, delay=0.05: original(fn, retries=retries, delay=0)
        try:
            result = export_project_tasks(project, [task], client=mock)
        finally:
            export_mod.call_with_retry = original

        assert result['exported'] == 1
        assert result['failed'] == []
        assert mock.create_calls == 1
        task.refresh_from_db()
        assert task.airtable_record_id
