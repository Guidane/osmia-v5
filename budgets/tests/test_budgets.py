"""Budgets: what an order charged to one counts as (planned while a draft, spent once placed: arrived or still to
come), other costs, everything rolling up through the budgets above, the owner told when it is overspent, the warning
before placing, Home, Excel."""
from decimal import Decimal

from django.urls import reverse

from budgets import money
from budgets.models import Budget, Cost
from inventory.tests.test_inventory import Base
from orders import service
from orders.models import Order
from web.models import Notification


class BudgetTests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.year = Budget.objects.create(number='FY26', name='2026', amount=1000, owner=cls.ada)
        cls.test = Budget.objects.create(number='FY26-TE', name='Test equipment', parent=cls.year, amount=100, owner=cls.ada)

    def order(self, budget, quantity, price='2.50'):
        order = Order.objects.create(vendor=self.acme, budget=budget, created_by=self.ada)
        line = order.lines.create(part=self.plug, quantity=quantity, price=Decimal(price))
        return order, line

    def test_drafts_are_planned_placed_orders_are_spent_and_it_rolls_up(self):
        order, line = self.order(self.test, 20)                                 # 50.00
        t = money.totals()[self.test.pk]
        self.assertEqual((t.planned, t.spent), (50, 0))
        service.place(order, self.ada)
        service.receive(order, [(line, 8, self.shelf)], self.ada)
        t = money.totals()[self.test.pk]
        self.assertEqual((t.received, t.coming, t.spent, t.remaining, t.used), (20, 30, 50, 50, 50))
        Cost.objects.create(budget=self.year, spent_on='2026-01-10', description='Calibration', amount=Decimal('300'))
        year = money.totals()[self.year.pk]
        self.assertEqual((year.spent, year.remaining), (350, 650))              # its own cost and what is under it
        self.assertEqual(money.own_totals(self.year).spent, 300)

    def test_the_owner_hears_when_it_is_overspent(self):
        order, _ = self.order(self.test, 60)                                    # 150.00 of 100
        response = self.client.get(reverse('orders:order', args=[order.pk]))
        self.assertContains(response, 'takes FY26-TE Test equipment over its budget by 50.00')
        service.place(order, self.ada)
        self.assertTrue(Notification.objects.filter(user=self.ada, message='FY26-TE Test equipment is overspent: 150.00 of 100.00.').exists())
        self.assertFalse(Notification.objects.filter(message__startswith='FY26 2026').exists())   # the year still has room
        self.assertContains(self.client.get('/'), '1</b> budget overspent')

    def test_costs_from_the_page_and_the_pages(self):
        self.client.post(reverse('budgets:cost_add', args=[self.year.pk]), {'description': 'Travel', 'amount': '120,50', 'spent_on': '2026-03-01'})
        self.assertEqual(Cost.objects.get().amount, Decimal('120.50'))
        self.client.post(reverse('budgets:cost_add', args=[self.year.pk]), {'description': '', 'amount': '5'})
        self.assertEqual(Cost.objects.count(), 1)
        page = self.client.get(reverse('budgets:list'))
        self.assertContains(page, 'Test equipment')
        self.assertContains(page, '879.50')                                     # left of the year
        page = self.client.get(reverse('budgets:budget', args=[self.year.pk]))
        self.assertContains(page, 'Travel')
        response = self.client.get(reverse('budgets:list'), {'export': 1})
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        page = self.client.post(reverse('budgets:edit', args=[self.year.pk]), {'name': '2026', 'parent': self.test.pk, 'amount': 1})
        self.assertContains(page, 'part of itself')

    def test_a_closed_budget_isn_t_offered_for_new_orders(self):
        Budget.objects.filter(pk=self.test.pk).update(active=False)
        page = self.client.get(reverse('orders:new'))
        self.assertContains(page, 'FY26 2026')
        self.assertNotContains(page, 'Test equipment')
