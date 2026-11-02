"""Administrators making and changing users and departments, putting people in a department; everyone else sees the
departments but not the users page; nobody locks themselves out."""
from django.test import TestCase
from django.urls import reverse

from accounts.models import Department, User
from budgets.models import Budget


class PeopleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ada = User.objects.create_superuser('ada', 'ada@example.com', 'pw', first_name='Ada')
        cls.bob = User.objects.create_user('bob', password='pw', first_name='Bob')
        cls.engineering = Department.objects.create(name='Engineering')
        cls.test = Department.objects.create(name='Test', parent=cls.engineering, manager=cls.ada)

    def setUp(self):
        self.client.force_login(self.ada)

    def test_making_a_user(self):
        response = self.client.post(reverse('accounts:user_new'), {
            'username': 'carla', 'first_name': 'Carla', 'department': self.test.pk, 'is_active': 'on',
            'password1': 'a long secret 123', 'password2': 'a long secret 123'})
        self.assertRedirects(response, reverse('accounts:users'))
        carla = User.objects.get(username='carla')
        self.assertEqual(carla.department, self.test)
        self.assertTrue(carla.check_password('a long secret 123'))
        page = self.client.post(reverse('accounts:user_new'), {'username': 'dave', 'is_active': 'on'})
        self.assertContains(page, 'Give them a password')
        page = self.client.post(reverse('accounts:user_new'), {'username': 'dave', 'password1': '123', 'password2': '123'})
        self.assertContains(page, 'too short')

    def test_changing_someone_keeps_their_password_and_admins_can_t_lock_themselves_out(self):
        self.client.post(reverse('accounts:user_edit', args=[self.bob.pk]), {
            'username': 'bob', 'first_name': 'Bob', 'job_title': 'Technician', 'is_superuser': 'on', 'is_active': 'on'})
        bob = User.objects.get(pk=self.bob.pk)
        self.assertEqual((bob.job_title, bob.is_superuser, bob.is_staff), ('Technician', True, True))
        self.assertTrue(bob.check_password('pw'))
        page = self.client.post(reverse('accounts:user_edit', args=[self.ada.pk]), {'username': 'ada', 'is_active': 'on'})
        self.assertContains(page, 'own administrator rights')
        self.assertTrue(User.objects.get(pk=self.ada.pk).is_superuser)

    def test_the_users_page_is_for_administrators(self):
        page = self.client.get(reverse('accounts:users'), {'department': self.engineering.pk})
        self.assertNotContains(page, '>Bob<')
        User.objects.filter(pk=self.bob.pk).update(department=self.test)
        self.assertContains(self.client.get(reverse('accounts:users'), {'department': self.engineering.pk}), 'Bob')   # in one under it
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(reverse('accounts:users')).status_code, 404)
        self.assertEqual(self.client.post(reverse('accounts:assign', args=[self.test.pk]), {'users': [self.bob.pk]}).status_code, 404)
        self.assertContains(self.client.get(reverse('accounts:departments')), 'Engineering')
        self.assertNotContains(self.client.get(reverse('accounts:department', args=[self.test.pk])), 'Put in Test')

    def test_putting_people_in_a_department_and_taking_them_out(self):
        carla = User.objects.create_user('carla', first_name='Carla', department=self.engineering)
        self.client.post(reverse('accounts:assign', args=[self.test.pk]), {'users': [self.bob.pk, carla.pk]})
        self.assertEqual(set(self.test.members.values_list('username', flat=True)), {'bob', 'carla'})
        self.client.post(reverse('accounts:assign', args=[self.test.pk]), {'remove': self.bob.pk})
        self.assertIsNone(User.objects.get(pk=self.bob.pk).department)
        Budget.objects.create(name='Test rigs', amount=500, department=self.test)
        page = self.client.get(reverse('accounts:department', args=[self.test.pk]))
        self.assertContains(page, 'Carla')
        self.assertContains(page, 'Test rigs')

    def test_departments_as_a_tree(self):
        page = self.client.post(reverse('accounts:department_edit', args=[self.engineering.pk]), {'name': 'Engineering', 'parent': self.test.pk})
        self.assertContains(page, 'part of itself')
        response = self.client.post(reverse('accounts:department_delete', args=[self.engineering.pk]), follow=True)
        self.assertContains(response, 'has departments under it')
        User.objects.filter(pk=self.bob.pk).update(department=self.test)
        self.client.post(reverse('accounts:department_delete', args=[self.test.pk]))
        self.assertIsNone(User.objects.get(pk=self.bob.pk).department)
