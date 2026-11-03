"""The menus in a real browser: an open one closes on a click outside it, on Escape, and when the other one opens; a
click inside it leaves it open."""
from web.tests.browser import BrowserTestCase, expect


class MenuTests(BrowserTestCase):
    def test_an_open_menu_closes(self):
        page = self.go('/')
        menu, user = page.locator('details.hamburger'), page.locator('details.menu:not(.hamburger)')
        page.click('details.hamburger summary')
        expect(menu).to_have_attribute('open', '')
        page.click('details.hamburger .menu-panel .label >> nth=0')            # inside: stays open
        expect(menu).to_have_attribute('open', '')
        page.mouse.click(700, 600)                                               # outside
        expect(menu).not_to_have_attribute('open', '')
        page.click('details.hamburger summary')
        page.keyboard.press('Escape')
        expect(menu).not_to_have_attribute('open', '')
        page.click('details.hamburger summary')
        page.click('details.menu:not(.hamburger) summary')                       # the other one
        expect(user).to_have_attribute('open', '')
        expect(menu).not_to_have_attribute('open', '')
