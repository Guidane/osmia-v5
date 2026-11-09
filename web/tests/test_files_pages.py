"""Files of anything (the first picture its preview; one made the preview; deleted from the disk too) and documentation
pages (cleaned, under each other, of a thing or general, every save kept, an old version brought back, deleted with the
pages under them; what belongs to something deleted goes with it)."""
import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from inventory.models import Part
from inventory.tests.test_inventory import Base
from web.models import Attachment, Page
from web.things import files_of, pages_of, preview_of

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\r'
       b'IDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')


class MediaBase(Base):
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.settings = override_settings(MEDIA_ROOT=self.media)
        self.settings.enable()

    def tearDown(self):
        self.settings.disable()
        shutil.rmtree(self.media, ignore_errors=True)


class FileTests(MediaBase):
    def test_files_of_a_part_its_preview_and_deleting(self):
        url = reverse('web:files', args=['part', self.plug.pk])
        self.client.post(url, {'file': [SimpleUploadedFile('sheet.pdf', b'%PDF-1.4', 'application/pdf'),
                                        SimpleUploadedFile('front.png', PNG, 'image/png')]})
        self.client.post(url, {'file': SimpleUploadedFile('back.png', PNG, 'image/png')})
        self.assertEqual(sorted(files_of(self.plug).values_list('name', flat=True)), ['back.png', 'front.png', 'sheet.pdf'])
        self.assertEqual(preview_of(self.plug).name, 'front.png')                       # the first picture
        page = self.client.get(self.plug.get_absolute_url())
        self.assertContains(page, 'class="main-image"')
        self.assertContains(page, 'sheet.pdf')
        self.assertContains(self.client.get(reverse('inventory:parts')), 'class="thumb-sm"')   # in the list too
        back = Attachment.objects.get(name='back.png')
        card = self.client.post(reverse('web:file_preview', args=[back.pk]), HTTP_X_FILES_CARD='1')
        self.assertContains(card, 'files-card')                                          # the card, drawn again
        self.assertEqual(preview_of(self.plug), back)
        shown = self.client.get(reverse('web:file', args=[back.pk]))
        self.assertEqual(b''.join(shown.streaming_content), PNG)
        self.assertIn('sandbox', shown['Content-Security-Policy'])
        on_disk = Path(self.media) / back.file.name
        self.assertTrue(on_disk.exists())
        self.client.post(reverse('web:file_remove', args=[back.pk]))
        self.assertFalse(on_disk.exists())
        self.assertIsNone(preview_of(self.plug))

    def test_files_and_pages_go_with_what_is_deleted(self):
        part = Part.objects.create(number='GONE-1')
        self.client.post(reverse('web:files', args=['part', part.pk]), {'file': SimpleUploadedFile('x.png', PNG, 'image/png')})
        stored = Path(self.media) / Attachment.objects.get().file.name
        Page.objects.create(title='How', content_type_id=Attachment.objects.get().content_type_id, object_id=part.pk)
        part.delete()
        self.assertFalse(Attachment.objects.exists())
        self.assertFalse(stored.exists())
        self.assertFalse(Page.objects.exists())

    def test_every_kind_has_its_cards(self):
        from orders.models import Order
        order = Order.objects.create(vendor=self.acme)
        for thing in (self.plug, self.acme, self.store, order):
            page = self.client.get(thing.get_absolute_url())
            self.assertContains(page, 'files-card', msg_prefix=str(thing))
            self.assertContains(page, 'docs-card', msg_prefix=str(thing))


class PageTests(MediaBase):
    def test_a_page_of_a_part_cleaned_with_a_page_under_it(self):
        response = self.client.post(f"{reverse('web:page_new')}?kind=part&pk={self.plug.pk}", {
            'title': 'Crimping', 'body': '<h2>Use</h2><p onclick="x()">Crimp <b>first</b></p><script>alert(1)</script>'
                                         '<a href="javascript:x()">bad</a>'})
        page = Page.objects.get()
        self.assertRedirects(response, page.get_absolute_url())
        self.assertEqual((page.owner, page.body), (self.plug, '<h2>Use</h2><p>Crimp <b>first</b></p><a rel="noopener noreferrer">bad</a>'))
        self.assertContains(self.client.get(self.plug.get_absolute_url()), 'Crimping')      # on the part's page
        self.client.post(f"{reverse('web:page_new')}?parent={page.pk}", {'title': 'Tools', 'body': '<p>The crimper</p>', 'parent': page.pk})
        under = Page.objects.get(title='Tools')
        self.assertEqual((under.parent, under.owner), (page, self.plug))                    # in the same place
        self.assertEqual([p.title for p, _ in pages_of(self.plug)], ['Crimping', 'Tools'])
        shown = self.client.get(page.get_absolute_url())
        self.assertContains(shown, 'Tools')
        self.assertContains(self.client.get(reverse('web:docs')), 'Crimping')
        self.assertContains(self.client.get(reverse('web:docs'), {'q': 'crimper'}), 'Tools')

    def test_history_and_bringing_an_old_version_back(self):
        self.client.post(reverse('web:page_new'), {'title': 'Lab rules', 'body': '<p>One</p>'})
        page = Page.objects.get()
        self.assertIsNone(page.owner)                                                        # general
        self.client.post(reverse('web:page_edit', args=[page.pk]), {'title': 'Lab rules', 'body': '<p>Two</p>'})
        self.client.post(reverse('web:page_edit', args=[page.pk]), {'title': 'Lab rules', 'body': '<p>Two</p>'})   # unchanged
        self.assertEqual(list(page.versions.values_list('number', flat=True)), [2, 1])
        self.assertContains(self.client.get(reverse('web:page_history', args=[page.pk]), {'v': 1}), '<p>One</p>', html=True)
        self.client.post(reverse('web:page_restore', args=[page.pk, 1]))
        page.refresh_from_db()
        self.assertEqual((page.body, page.versions.count()), ('<p>One</p>', 3))

    def test_a_page_cant_go_under_itself_and_deleting_takes_the_pages_under_it(self):
        top = Page.objects.create(title='Top')
        mid = Page.objects.create(title='Mid', parent=top)
        Page.objects.create(title='Low', parent=mid)
        response = self.client.post(reverse('web:page_edit', args=[top.pk]), {'title': 'Top', 'body': '', 'parent': mid.pk})
        self.assertEqual(response.status_code, 200)                                          # refused
        self.client.post(reverse('web:files', args=['page', mid.pk]), {'file': SimpleUploadedFile('a.png', PNG, 'image/png')})
        self.assertIsNone(preview_of(mid))                                                   # pages have no preview
        self.client.post(reverse('web:page_delete', args=[top.pk]))
        self.assertFalse(Page.objects.exists())
        self.assertFalse(Attachment.objects.exists())
