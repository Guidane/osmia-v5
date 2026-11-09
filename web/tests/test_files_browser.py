"""The Files card in a real browser: a picked file and a dropped one go in without leaving the page, the first picture
becomes the preview (shown on the page), another one is starred instead, and one is deleted."""
from inventory.models import Part
from web.tests.browser import BrowserTestCase, expect
from web.tests.test_files_pages import PNG
from web.things import files_of, preview_of


class FilesCardTests(BrowserTestCase):
    def test_adding_starring_and_deleting_files(self):
        part = Part.objects.create(number='R-10K', description='Resistor 10 kΩ')
        page = self.go(part.get_absolute_url())
        card = page.locator('.files-card')
        card.locator('[data-pick]').set_input_files([{'name': 'front.png', 'mimeType': 'image/png', 'buffer': PNG},
                                                     {'name': 'values.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4'}])
        expect(page.locator('.main-image img')).to_be_visible()                       # the first picture: its preview
        expect(page.locator('.files-card .file-tile')).to_have_count(2)
        page.evaluate("""png => {
            const bytes = Uint8Array.from(atob(png), c => c.charCodeAt(0));
            const data = new DataTransfer();
            data.items.add(new File([bytes], 'back.png', { type: 'image/png' }));
            const card = document.querySelector('.files-card');
            card.dispatchEvent(new DragEvent('dragover', { dataTransfer: data, bubbles: true }));
            card.dispatchEvent(new DragEvent('drop', { dataTransfer: data, bubbles: true }));
        }""", __import__('base64').b64encode(PNG).decode())
        expect(page.locator('.files-card .file-tile')).to_have_count(3)               # dropped on the card
        page.locator('.file-tile', has_text='back.png').hover()
        page.locator('.file-tile', has_text='back.png').locator('.star').click()
        expect(page.locator('.file-tile.is-preview')).to_contain_text('back.png')
        self.assertEqual(preview_of(part).name, 'back.png')
        page.locator('.file-tile', has_text='values.pdf').hover()
        page.locator('.file-tile', has_text='values.pdf').locator('[data-ask]').click()
        expect(page.locator('.files-card .file-tile')).to_have_count(2)
        self.assertEqual(sorted(files_of(part).values_list('name', flat=True)), ['back.png', 'front.png'])
