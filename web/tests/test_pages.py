"""The website itself: the first run makes the administrator, then Home, notifications and logging out work."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from web import middleware
from web.models import Notification
from web.notify import notify


class FirstRunTests(TestCase):
    def setUp(self):
        middleware._ready = False

    def test_everything_waits_for_the_administrator(self):
        self.assertRedirects(self.client.get('/'), reverse('web:setup'), fetch_redirect_response=False)
        page = self.client.post(reverse('web:setup'), {'username': 'ada', 'password1': 'short', 'password2': 'short'})
        self.assertContains(page, 'too short')                                  # Django's password rules
        response = self.client.post(reverse('web:setup'), {
            'username': 'ada', 'first_name': 'Ada', 'password1': 'a long secret 123', 'password2': 'a long secret 123'})
        self.assertRedirects(response, reverse('web:home'))
        ada = get_user_model().objects.get(username='ada')
        self.assertTrue(ada.is_superuser)
        self.assertRedirects(self.client.get(reverse('web:setup')), reverse('web:home'))   # only once


class PageTests(TestCase):
    def setUp(self):
        self.ada = get_user_model().objects.create_superuser('ada', 'ada@example.com', 'pw')
        self.client.force_login(self.ada)

    def test_home_notifications_and_logging_out(self):
        self.assertContains(self.client.get('/'), 'still to come')
        notify([self.ada], 'Place the order is waiting for you.', url='/notifications/')
        page = self.client.get(reverse('web:notifications'))
        self.assertContains(page, 'Place the order is waiting for you.')
        note = Notification.objects.get()
        self.client.get(reverse('web:notification_open', args=[note.pk]))
        self.assertTrue(Notification.objects.get().read)
        self.assertContains(self.client.get(reverse('accounts:profile')), 'Your profile')
        self.client.post(reverse('accounts:logout'))
        self.assertRedirects(self.client.get('/'), reverse('accounts:login') + '?next=/')


from inventory.tests.test_inventory import Base  # noqa: E402


class HomeReportTests(Base):
    """Home: its reports picked by each person (taken off, put back, as it comes again)."""
    def test_reports_taken_off_and_added(self):
        from django.urls import reverse
        page = self.client.get('/')
        self.assertEqual([key for key, _, _ in page.context['reports']],
                         ['glance', 'harness_requests', 'waiting', 'to_order', 'assets_due', 'received'])
        self.assertContains(page, 'At a glance')
        self.assertNotContains(page, 'Take it off Home')                                   # only while editing
        self.assertContains(self.client.get('/', {'edit': 1}), 'Take it off Home')
        back = self.client.post(reverse('web:home_reports'), {'action': 'remove', 'key': 'waiting'})
        self.assertRedirects(back, '/?edit=1')
        self.client.post(reverse('web:home_reports'), {'action': 'add', 'key': 'my_assets'})
        page = self.client.get('/')
        self.assertEqual([key for key, _, _ in page.context['reports']], ['glance', 'harness_requests', 'to_order', 'assets_due', 'received', 'my_assets'])
        self.assertContains(page, 'What I have out')
        self.assertNotContains(page, 'Nothing on its way.')
        self.assertIn(('waiting', 'Still to come'), page.context['addable'])
        self.client.post(reverse('web:home_reports'), {'action': 'reset'})
        self.assertEqual(len(self.client.get('/').context['reports']), 6)


class BrowserTests(TestCase):
    """The lists with a tree on the left and the details of the row picked on the right: each opens, with the demo
    data, and shows the details of one of its things."""
    def test_every_list_and_its_details(self):
        from django.apps import apps
        from web import demo
        middleware._ready = False
        ada = get_user_model().objects.create_superuser('ada', 'ada@example.com', 'pw')
        self.client.force_login(ada)
        demo.switch_on(ada)
        pages = [('inventory:parts', 'part', 'inventory.Part', None), ('assets:list', 'asset', 'assets.Asset', None),
                 ('harnesses:list', 'harness', 'harnesses.Harness', None), ('inventory:families', 'family', 'inventory.Family', None),
                 ('devices:list', 'device', 'devices.Device', 'device'), ('orders:list', 'order', 'orders.Order', 'order'),
                 ('inventory:vendors', 'vendor', 'inventory.Vendor', 'vendor'), ('projects:list', 'diagram', 'projects.Project', 'diagram'),
                 ('work:list', 'project', 'work.Project', 'project'), ('budgets:list', 'budget', 'budgets.Budget', 'budget'),
                 ('accounts:users', 'user', 'accounts.User', 'user'), ('inventory:locations', 'part', 'inventory.Part', None)]
        for name, param, model, kind in pages:
            with self.subTest(page=name):
                thing = apps.get_model(model).objects.first()
                page = self.client.get(reverse(name), {param: thing.pk})
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, 'parts-browser')
                self.assertContains(page, 'data-brief="%d"' % thing.pk)                     # its details, already open
                if kind:
                    for other in apps.get_model(model).objects.all()[:5]:
                        self.assertEqual(self.client.get(reverse('web:brief', args=[kind, other.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('web:brief', args=['nothing', 1])).status_code, 404)
