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
