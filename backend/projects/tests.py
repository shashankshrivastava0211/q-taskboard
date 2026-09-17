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
