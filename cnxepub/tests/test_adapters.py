# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
try:
    import html.parser as HTMLParser
except:
    import HTMLParser
import mimetypes
import os
import io
import tempfile
import shutil
import sys
import random
import re
import unittest
try:
    from unittest import mock
except ImportError:
    import mock

from lxml import etree


IS_PY3 = sys.version_info.major == 3
here = os.path.abspath(os.path.dirname(__file__))
TEST_DATA_DIR = os.path.join(here, 'data')


def unescape(html):
    p = HTMLParser.HTMLParser()
    if isinstance(html, bytes):
        html = html.decode('utf-8')
    return p.unescape(html)


def random_extension(*args, **kwargs):
    # mimetypes.guess_extension can return any of the values in
    # mimetypes.guess_all_extensions.  it depends on the system.
    # we're using this to make sure our code is robust enough to handle the
    # different possible extensions
    exts = mimetypes.guess_all_extensions(*args, **kwargs)
    return random.choice(exts)


def last_extension(*args, **kwargs):
    # Always return the last value of sorted mimetypes.guess_all_extensions
    exts = mimetypes.guess_all_extensions(*args, **kwargs)
    return sorted(exts)[-1]


class AdaptationTestCase(unittest.TestCase):
    maxDiff = None

    def make_package(self, file):
        from ..epub import Package
        return Package.from_file(file)

    def make_item(self, file, **kwargs):
        from ..epub import Item
        return Item.from_file(file, **kwargs)

    def test_to_binder(self):
        """Adapts a ``Package`` to a ``BinderItem``.
        Binders are native object representations of data,
        while the Package is merely a representation of EPUB structure.
        """
        # Easiest way to test this is using the ``model_to_tree`` utility
        # to analyze the structural equality.
        package_filepath = os.path.join(
            TEST_DATA_DIR, 'book',
            "9b0903d2-13c4-4ebe-9ffe-1ee79db28482@1.6.opf")
        package = self.make_package(package_filepath)
        expected_tree = {
            'id': '9b0903d2-13c4-4ebe-9ffe-1ee79db28482@1.6',
            'title': 'Book of Infinity',
            'contents': [
                {'id': 'subcol',
                 'title': 'Part One',
                 'contents': [
                     {'contents': [
                          {'id': 'e78d4f90-e078-49d2-beac-e95e8be70667@3', 'title': 'Document One'}],
                      'id': 'subcol',
                      'title': 'Chapter One'},
                     {'id': 'subcol',
                      'title': 'Chapter Two',
                      'contents': [{'id': 'e78d4f90-e078-49d2-beac-e95e8be70667@3',
                                    'title': 'Document One (again)'}],
                      }]},
                {'id': 'subcol',
                 'title': 'Part Two',
                 'contents': [
                     {'id': 'subcol',
                      'title': 'Chapter Three',
                      'contents': [
                          {'id': 'e78d4f90-e078-49d2-beac-e95e8be70667@3',
                           'title': 'Document One (...and again)'}]
                      }]}]}

        from ..adapters import adapt_package
        binder = adapt_package(package)
        self.assertEqual(binder.id, '9b0903d2-13c4-4ebe-9ffe-1ee79db28482@1.6')
        self.assertEqual(binder.ident_hash,
                         '9b0903d2-13c4-4ebe-9ffe-1ee79db28482@1.6')
        self.assertEqual(len(binder.resources), 1)
        self.assertEqual(binder.resources[0].id, 'cover.png')
        with open(os.path.join(
                TEST_DATA_DIR, 'book', 'resources', 'cover.png'), 'rb') as f:
            expected_cover = f.read()
        with binder.resources[0].open() as f:
            binder_cover = f.read()
        self.assertEqual(expected_cover, binder_cover)

        # This checks the binder structure, and only taps at the documents.
        from ..models import model_to_tree
        tree = model_to_tree(binder)
        self.assertEqual(tree, expected_tree)
        self.assertEqual(package.metadata['publication_message'], u'Nueva Versión')

    def test_to_translucent_binder(self):
        """Adapts a ``Package`` to a ``TranslucentBinder``.
        Translucent binders are native object representations of data,
        while the Package is merely a representation of EPUB structure.
        Furthermore, translucent binders are non-persistable objects,
        that contain the same behavior as binders, but lack metadata
        and material. They can be thought of as a protective sheath that
        is invisible, yet holds the contents together.
        """
        # Easiest way to test this is using the ``model_to_tree`` utility
        # to analyze the structural equality.
        package_filepath = os.path.join(
            TEST_DATA_DIR, 'loose-pages', "faux.opf")
        package = self.make_package(package_filepath)
        expected_tree = {
            'id': 'subcol',
            'title': "Loose Pages",
            'contents': [{'id': None, 'title': 'Yummy'},
                         {'id': None, 'title': 'Da bomb'},
                         {'id': 'pointer@1', 'title': 'Pointer'}],
            }

        from ..adapters import adapt_package
        binder = adapt_package(package)

        # This checks the binder structure, and only taps at the documents.
        from ..models import model_to_tree
        tree = model_to_tree(binder)
        self.assertEqual(tree, expected_tree)

    def test_to_document_wo_resources_o_references(self):
        """Adapts an ``Item`` to a ``DocumentItem``.
        Documents are native object representations of data,
        while the Item is merely a representation of an item
        in the EPUB structure.
        We are specifically testing for metadata parsing and
        resource discovery.
        """
        item_filepath = os.path.join(
            TEST_DATA_DIR, 'loose-pages', 'content',
            "fig-bush.xhtml")
        item = self.make_item(item_filepath, media_type='application/xhtml+xml')

        package = mock.Mock()
        # This would not typically be called outside the context of
        # a package, but in the case of a scoped test we use it.
        from ..adapters import adapt_item
        document = adapt_item(item, package)

        # Check the document metadata
        expected_metadata = {
            u'authors': [{u'id': u'https://github.com/marknewlyn',
                          u'name': u'Mark Horner',
                          u'type': u'github-id'},
                         {u'id': u'https://cnx.org/member_profile/sarblyth',
                          u'name': u'Sarah Blyth',
                          u'type': u'cnx-id'},
                         {u'id': u'https://example.org/profiles/charrose',
                          u'name': u'Charmaine St. Rose',
                          u'type': u'openstax-id'}],
            u'copyright_holders': [
                {u'id': u'https://cnx.org/member_profile/ream',
                 u'name': u'Ream',
                 u'type': u'cnx-id'}],
            u'created': u'2013/03/19 15:01:16 -0500',
            u'editors': [{u'id': None, u'name': u'I. M. Picky',
                          u'type': None}],
            u'illustrators': [{u'id': None, u'name': u'Francis Hablar',
                               u'type': None}],
            u'keywords': [u'South Africa'],
            u'license_text': u'CC-By 4.0',
            u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
            u'publishers': [{u'id': None, u'name': u'Ream', u'type': None}],
            u'revised': u'2013/06/18 15:22:55 -0500',
            u'subjects': [u'Science and Mathematics'],
            u'summary': u'\n        By the end of this section, you will be able to: \n        <ul xmlns="http://www.w3.org/1999/xhtml" xmlns:bib="http://bibtexml.sf.net/" xmlns:data="http://www.w3.org/TR/html5/dom.html#custom-data-attribute" xmlns:epub="http://www.idpf.org/2007/ops" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:lrmi="http://lrmi.net/the-specification" class="list">\n          <li class="item">Drive a car</li>\n          <li class="item">Purchase a watch</li>\n          <li class="item">Wear funny hats</li>\n          <li class="item">Eat cake</li>\n        </ul>\n      \n      ',
            u'title': u'Document One of Infinity',
            u'translators': [{u'id': None, u'name': u'Francis Hablar',
                              u'type': None}],
            u'derived_from_uri': u'http://example.org/contents/id@ver',
            u'derived_from_title': u'Wild Grains and Warted Feet',
            u'cnx-archive-uri': None,
            u'language': None,
            u'print_style': u'* print style *',
            }
        self.assertEqual(expected_metadata, document.metadata)

        # Check the document uri lookup
        uri = document.get_uri('cnx-archive')
        self.assertEqual(None, uri)

        # Check resource discovery.
        self.assertEqual([], document.references)

    def test_to_document_w_resources(self):
        """Adapts an ``Item`` to a ``DocumentItem``.
        Documents are native object representations of data,
        while the Item is merely a representation of an item
        in the EPUB structure.
        We are specifically testing for reference parsing and
        resource discovery.
        """
        content_filepath = os.path.join(
            TEST_DATA_DIR, 'loose-pages', 'content',
            "fig-bush.xhtml")
        file_pointer, item_filepath = tempfile.mkstemp()
        internal_uri = "../resources/openstax.png"
        with open(content_filepath, 'r') as fb:
            xml = etree.parse(fb)
            body = xml.xpath(
                '//xhtml:body',
                namespaces={'xhtml': "http://www.w3.org/1999/xhtml"})[0]
            elm = etree.SubElement(body, "img")
            elm.set('src', internal_uri)
        with open(item_filepath, 'wb') as fb:
            fb.write(etree.tostring(xml))
        item = self.make_item(item_filepath, media_type='application/xhtml+xml')

        package = mock.Mock()
        # This would not typically be called outside the context of
        # a package, but in the case of a scoped test we use it.

        resource_filepath = os.path.join(TEST_DATA_DIR, 'loose-pages',
                                         'resources', 'openstax.png')
        from ..models import Resource
        package.grab_by_name.side_effect = [
            self.make_item(resource_filepath, media_type='image/png'),
            ]
        from ..adapters import adapt_item
        document = adapt_item(item, package)

        # Check resource discovery.
        self.assertEqual([internal_uri],
                         [ref.uri for ref in document.references])
        # Check the resource was discovered.
        self.assertEqual(['openstax.png'],
                         [res.id for res in document.resources])
        # Check that the reference is bound to the resource
        ref = list(document.references)[0]
        res = list(document.resources)[0]
        self.assertEqual(ref._bound_model, res)

    def test_to_document_pointer(self):
        """Adapts an ``Item`` to a ``DocumentPointerItem``.
        Documents are native object representations of data,
        while the Item is merely a representation of an item
        in the EPUB structure.
        """
        item_filepath = os.path.join(
                TEST_DATA_DIR, 'loose-pages', 'content',
                'pointer.xhtml')

        package = mock.Mock()
        item = self.make_item(item_filepath, media_type='application/xhtml+xml')

        from ..adapters import adapt_item, DocumentPointerItem
        pointer = adapt_item(item, package)

        self.assertEqual(type(pointer), DocumentPointerItem)
        self.assertEqual(pointer.ident_hash, 'pointer@1')
        self.assertEqual(pointer.metadata['title'], 'Pointer')


@mock.patch('mimetypes.guess_extension', new=random_extension)
class ModelsToEPUBTestCase(unittest.TestCase):

    def test_loose_pages_wo_resources(self):
        """Create a publication EPUB from a loose set of pages."""
        from ..models import TranslucentBinder, Document
        binder = TranslucentBinder(metadata={'title': "Kraken"})

        base_metadata = {
            'publishers': [],
            'created': '2013/03/19 15:01:16 -0500',
            'revised': '2013/06/18 15:22:55 -0500',
            'authors': [
                {'type': 'cnx-id',
                 'name': 'Sponge Bob',
                 'id': 'sbob'}],
            'editors': [],
            'copyright_holders': [],
            'illustrators': [],
            'subjects': ['Science and Mathematics'],
            'translators': [],
            'keywords': ['Bob', 'Sponge', 'Rock'],
            'title': "Goofy Goober Rock",
            'license_text': 'CC-By 4.0',
            'license_url': 'http://creativecommons.org/licenses/by/4.0/',
            'summary': "<p>summary</p>",
            'version': 'draft',
            }

        # Build test documents
        metadata = base_metadata.copy()
        metadata.update({'title': "entrée"})
        binder.append(Document('ingress', io.BytesIO(b'<p>Hello.</p>'),
                               metadata=metadata))
        metadata = base_metadata.copy()
        metadata.update({'title': "egress"})
        binder.append(Document('egress', io.BytesIO(u'<p>hüvasti.</p>'.encode('utf-8')),
                               metadata=metadata))

        # Call the target.
        fs_pointer, epub_filepath = tempfile.mkstemp('.epub')
        self.addCleanup(os.remove, epub_filepath)
        from ..adapters import make_publication_epub
        with open(epub_filepath, 'wb') as epub_file:
            make_publication_epub(binder, 'krabs', '$.$', epub_file)

        # Verify the results.
        epub_path = tempfile.mkdtemp('-epub')
        self.addCleanup(shutil.rmtree, epub_path)
        from ..epub import unpack_epub
        unpack_epub(epub_filepath, epub_path)

        # Because a TranslucentBinder doesn't has an id of ``None``,
        # we uniquely create one using the object's hash.
        binder_hash = str(hash(binder))
        opf_filename = "{}.opf".format(binder_hash)

        # Check filenames, generated by id and media-type.
        self.assertEqual(
            [opf_filename, 'META-INF', 'contents', 'mimetype'],
            sorted(os.listdir(epub_path)))
        filenames = sorted(os.listdir(os.path.join(epub_path, 'contents')))
        self.assertEqual(
            [binder_hash, 'egress@draft', 'ingress@draft'],
            [os.path.splitext(filename)[0] for filename in filenames])
        self.assertEqual(
            ['application/xhtml+xml', 'application/xhtml+xml', 'application/xhtml+xml'],
            [mimetypes.guess_type(filename)[0] for filename in filenames])
        navdoc_filename, egress_filename, ingress_filename = filenames

        # Check the opf file
        with open(os.path.join(epub_path, opf_filename)) as f:
            opf = unescape(f.read())
        self.assertTrue(u'<dc:publisher>krabs</dc:publisher>' in opf)
        self.assertTrue(u'<meta property="publicationMessage">$.$</meta>' in opf)

        # Check the nav
        with open(os.path.join(epub_path, 'contents', navdoc_filename)) as f:
            nav = unescape(f.read())
        expected_nav = (
                u'<nav id="toc"><ol><li>'
                u'<a href="{}">entrée</a>'
                u'</li><li>'
                u'<a href="{}">egress</a>'
                u'</li></ol></nav>'.format(ingress_filename, egress_filename))
        self.assertTrue(expected_nav in nav)

        # Check that translucent is set
        self.assertTrue('<span data-type="binding" data-value="translucent" />' in nav)

        # Check the title and content
        self.assertTrue('<title>Kraken</title>' in nav)
        with open(os.path.join(epub_path, 'contents', egress_filename)) as f:
            egress = unescape(f.read())
        self.assertFalse('<div data-type="resources"' in egress)
        self.assertTrue('<title>egress</title>' in egress)
        self.assertTrue(u'<p>hüvasti.</p>' in egress)

        # Adapt epub back to documents and binders
        from cnxepub import EPUB
        from cnxepub.adapters import adapt_package
        from cnxepub.models import flatten_model
        epub = EPUB.from_file(epub_path)
        self.assertEqual(len(epub), 1)
        binder = adapt_package(epub[0])
        self.assertEqual(len(list(flatten_model(binder))), 3)

    def test_loose_pages_w_resources(self):
        """Create a publication EPUB from a loose set of pages."""
        from ..models import TranslucentBinder, Document, Resource
        binder = TranslucentBinder(metadata={'title': "Kraken"})

        base_metadata = {
            'publishers': [],
            'created': '2013/03/19 15:01:16 -0500',
            'revised': '2013/06/18 15:22:55 -0500',
            'authors': [
                {'type': 'cnx-id',
                 'name': 'Sponge Bob',
                 'id': 'sbob'}],
            'editors': [],
            'copyright_holders': [],
            'illustrators': [],
            'subjects': ['Science and Mathematics'],
            'translators': [],
            'keywords': ['Bob', 'Sponge', 'Rock',
                         # Invalid xml in keywords
                         '</emphasis>horizontal line'],
            'title': "Goofy Goober Rock",
            'license_text': 'CC-By 4.0',
            'license_url': 'http://creativecommons.org/licenses/by/4.0/',
            'summary': "<p>summary</p>",
            'version': 'draft',
            }

        # Build test documents
        metadata = base_metadata.copy()
        metadata.update({'title': "entrée"})
        binder.append(Document('ingress', io.BytesIO(
            b'<p><a href="http://cnx.org/">Hello.</a><a id="nohref">Goodbye</a></p>'),
                               metadata=metadata))
        metadata = base_metadata.copy()
        metadata.update({'title': "egress"})
        with open(os.path.join(TEST_DATA_DIR, '1x1.jpg'), 'rb') as f:
            jpg = Resource('1x1.jpg', io.BytesIO(f.read()), 'image/jpeg')
        binder.append(Document('egress', io.BytesIO(
            u'<p><img src="1x1.jpg" />hüvasti.</p>'.encode('utf-8')),
                               metadata=metadata,
                               resources=[jpg]))

        # Call the target.
        fs_pointer, epub_filepath = tempfile.mkstemp('.epub')
        self.addCleanup(os.remove, epub_filepath)
        from ..adapters import make_publication_epub
        with open(epub_filepath, 'wb') as epub_file:
            make_publication_epub(binder, 'krabs', '$.$', epub_file)

        # Verify the results.
        epub_path = tempfile.mkdtemp('-epub')
        self.addCleanup(shutil.rmtree, epub_path)
        from ..epub import unpack_epub
        unpack_epub(epub_filepath, epub_path)

        # Because a TranslucentBinder doesn't has an id of ``None``,
        # we uniquely create one using the object's hash.
        binder_hash = str(hash(binder))
        opf_filename = "{}.opf".format(binder_hash)

        # Check filenames, generated by id and media-type.
        self.assertEqual(
            [opf_filename, 'META-INF', 'contents', 'mimetype', 'resources'],
            sorted(os.listdir(epub_path)))
        filenames = sorted(os.listdir(os.path.join(epub_path, 'contents')))
        self.assertEqual(
            [binder_hash, 'egress@draft', 'ingress@draft'],
            [os.path.splitext(filename)[0] for filename in filenames])
        self.assertEqual(
            ['application/xhtml+xml', 'application/xhtml+xml', 'application/xhtml+xml'],
            [mimetypes.guess_type(filename)[0] for filename in filenames])
        self.assertEqual(os.listdir(os.path.join(epub_path, 'resources')),
                         ['1x1.jpg'])
        navdoc_filename, egress_filename, ingress_filename = filenames

        # Check the opf file
        with open(os.path.join(epub_path, opf_filename)) as f:
            opf = unescape(f.read())
        self.assertTrue(u'<dc:publisher>krabs</dc:publisher>' in opf)
        self.assertTrue(u'<meta property="publicationMessage">$.$</meta>' in opf)

        # Check the nav
        with open(os.path.join(epub_path, 'contents', navdoc_filename)) as f:
            nav = unescape(f.read())
        expected_nav = (
                u'<nav id="toc"><ol><li>'
                u'<a href="{}">entrée</a>'
                u'</li><li>'
                u'<a href="{}">egress</a>'
                u'</li></ol></nav>'.format(ingress_filename, egress_filename))
        self.assertIn(expected_nav, nav)

        # Check that translucent is set
        self.assertTrue('<span data-type="binding" data-value="translucent" />' in nav)

        # Check the title and content
        self.assertTrue('<title>Kraken</title>' in nav)
        with open(os.path.join(epub_path, 'contents', egress_filename)) as f:
            egress = unescape(f.read())
        self.assertTrue('<title>egress</title>' in egress)
        self.assertFalse('<span data-type="cnx-archive-uri"' in egress)
        self.assertTrue(re.search(
            '<div data-type="resources"[^>]*>\s*<ul>\s*'
            '<li>1x1.jpg</li>\s*</ul>\s*</div>', egress))
        self.assertTrue(u'<p><img src="../resources/1x1.jpg"/>hüvasti.</p>' in egress)

        # Adapt epub back to documents and binders
        from cnxepub import EPUB
        from cnxepub.adapters import adapt_package
        from cnxepub.models import flatten_model
        epub = EPUB.from_file(epub_path)
        self.assertEqual(len(epub), 1)
        binder = adapt_package(epub[0])
        self.assertEqual(len(list(flatten_model(binder))), 3)

        document = binder[0]
        self.assertEqual(document.metadata['keywords'],
                         base_metadata['keywords'])

    def test_binder(self):
        """Create an EPUB from a binder with a few documents."""
        from ..models import Binder, Document, DocumentPointer, Resource
        binder_name = 'rock'
        with open(os.path.join(TEST_DATA_DIR, 'cover.png'), 'rb') as f:
            cover = Resource('cover.png', io.BytesIO(f.read()), 'image/png')
        binder = Binder(binder_name, metadata={'title': "Kraken (Nueva Versión)"},
                        resources=[cover])

        base_metadata = {
            'publishers': [],
            'created': '2013/03/19 15:01:16 -0500',
            'revised': '2013/06/18 15:22:55 -0500',
            'authors': [
                {'type': 'cnx-id',
                 'name': 'Sponge Bob',
                 'id': 'sbob'}],
            'editors': [],
            'copyright_holders': [],
            'illustrators': [],
            'subjects': ['Science and Mathematics'],
            'translators': [],
            'keywords': ['Bob', 'Sponge', 'Rock'],
            'title': "Goofy Goober Rock",
            'license_text': 'CC-By 4.0',
            'license_url': 'http://creativecommons.org/licenses/by/4.0/',
            'summary': "<p>summary</p>",
            'version': 'draft',
            }

        # Build test documents
        metadata = base_metadata.copy()
        metadata.update({
            'title': "entrée",
            'derived_from_uri': 'http://cnx.org/contents/dd68a67a-11f4-4140-a49f-b78e856e2262@1',
            'derived_from_title': "Taking Customers' Orders",
            })
        binder.append(Document('ingress', io.BytesIO(b'<p>Hello.</p>'),
                               metadata=metadata))
        metadata = base_metadata.copy()
        metadata.update({'title': "egress",
                         'cnx-archive-uri': 'e78d4f90-e078-49d2-beac-e95e8be70667'})
        binder.append(Document('egress', io.BytesIO(u'<p>hüvasti.</p>'.encode('utf-8')),
                               metadata=metadata))
        binder.append(DocumentPointer('pointer@1', {
            'title': 'Pointer',
            'cnx-archive-uri': 'pointer@1',
            'url': 'http://cnx.org/contents/pointer@1'}))

        # Call the target.
        fs_pointer, epub_filepath = tempfile.mkstemp('.epub')
        self.addCleanup(os.remove, epub_filepath)
        from ..adapters import make_publication_epub
        with open(epub_filepath, 'wb') as epub_file:
            make_publication_epub(binder, 'krabs', '$.$', epub_file)

        # Verify the results.
        epub_path = tempfile.mkdtemp('-epub')
        self.addCleanup(shutil.rmtree, epub_path)
        from ..epub import unpack_epub
        unpack_epub(epub_filepath, epub_path)

        opf_filename = "{}.opf".format(binder_name)

        # Check filenames, generated by id and media-type.
        self.assertEqual(
            ['META-INF', 'contents', 'mimetype', 'resources', opf_filename],
            sorted(os.listdir(epub_path)))

        # Check resources
        self.assertEqual(['cover.png'],
                         os.listdir(os.path.join(epub_path, 'resources')))
        with open(os.path.join(epub_path, 'resources', 'cover.png'), 'rb') as f:
            epub_cover = f.read()
        with open(os.path.join(TEST_DATA_DIR, 'cover.png'), 'rb') as f:
            expected_cover = f.read()
        self.assertEqual(expected_cover, epub_cover)

        filenames = sorted(os.listdir(os.path.join(epub_path, 'contents')))
        self.assertEqual(
            ['egress@draft', 'ingress@draft', 'pointer@1', binder_name],
            [os.path.splitext(filename)[0] for filename in filenames])
        self.assertEqual(
            ['application/xhtml+xml', 'application/xhtml+xml',
                'application/xhtml+xml', 'application/xhtml+xml'],
            [mimetypes.guess_type(filename)[0] for filename in filenames])
        egress_filename, ingress_filename, pointer_filename, navdoc_filename = filenames

        # Check the opf file
        with open(os.path.join(epub_path, opf_filename)) as f:
            opf = unescape(f.read())
        self.assertTrue(u'<dc:publisher>krabs</dc:publisher>' in opf)
        self.assertTrue(u'<meta property="publicationMessage">$.$</meta>' in opf)
        self.assertTrue(u'href="resources/cover.png"' in opf)

        # Check the nav
        with open(os.path.join(epub_path, 'contents', navdoc_filename)) as f:
            nav = unescape(f.read())
        expected_nav = (
                u'<nav id="toc"><ol><li>'
                u'<a href="{}">entrée</a>'
                u'</li><li>'
                u'<a href="{}">egress</a>'
                u'</li><li>'
                u'<a href="{}">Pointer</a>'
                u'</li></ol></nav>'.format(ingress_filename, egress_filename,
                                           pointer_filename))
        self.assertTrue(expected_nav in nav)

        # Check the resources
        self.assertTrue(u'<li>cover.png</li>' in nav)

        # Check that translucent is not set
        self.assertFalse('<span data-type="binding" data-value="translucent" />' in nav)

        # Check the title and content
        self.assertTrue(u'<title>Kraken (Nueva Versión)</title>' in nav)
        with open(os.path.join(epub_path, 'contents', egress_filename)) as f:
            egress = unescape(f.read())
        with open(os.path.join(epub_path, 'contents', ingress_filename)) as f:
            ingress = unescape(f.read())
        self.assertTrue('<title>egress</title>' in egress)
        self.assertTrue('<span data-type="cnx-archive-uri" '
                        'data-value="e78d4f90-e078-49d2-beac-e95e8be70667" />' in egress)
        self.assertTrue(u'<p>hüvasti.</p>' in egress)
        self.assertFalse('Derived from:' in egress)
        self.assertTrue('Derived from:' in ingress)
        self.assertTrue('http://cnx.org/contents/dd68a67a-11f4-4140-a49f-b78e856e2262@1' in ingress)
        self.assertTrue("Taking Customers' Orders" in ingress)

        # Check the content of the document pointer file
        with open(os.path.join(epub_path, 'contents', pointer_filename)) as f:
            pointer = unescape(f.read())
        self.assertTrue('<title>Pointer</title>' in pointer)
        self.assertTrue('<span data-type="document" data-value="pointer" />' in pointer)
        self.assertTrue('<span data-type="cnx-archive-uri" '
                        'data-value="pointer@1" />' in pointer)
        self.assertTrue('<a href="http://cnx.org/contents/pointer@1">here</a>' in pointer)

        # Adapt epub back to documents and binders
        from cnxepub import EPUB
        from cnxepub.adapters import adapt_package
        from cnxepub.models import flatten_model
        epub = EPUB.from_file(epub_path)
        self.assertEqual(len(epub), 1)
        binder = adapt_package(epub[0])
        self.assertEqual(len(list(flatten_model(binder))), 4)


class DocumentContentFormatterTestCase(unittest.TestCase):
    def test_document(self):
        from ..models import Document
        from ..adapters import DocumentContentFormatter

        base_metadata = {
            'publishers': [],
            'created': '2013/03/19 15:01:16 -0500',
            'revised': '2013/06/18 15:22:55 -0500',
            'authors': [
                {'type': 'cnx-id',
                 'name': 'Sponge Bob',
                 'id': 'sbob'}],
            'editors': [],
            'copyright_holders': [],
            'illustrators': [],
            'subjects': ['Science and Mathematics'],
            'translators': [],
            'keywords': ['Bob', 'Sponge', 'Rock'],
            'title': "Goofy Goober Rock",
            'license_text': 'CC-By 4.0',
            'license_url': 'http://creativecommons.org/licenses/by/4.0/',
            'summary': "<p>summary</p>",
            'version': 'draft',
            }

        # Build test document.
        metadata = base_metadata.copy()
        document = Document('title',
                            io.BytesIO(u'<p>コンテンツ...</p>'.encode('utf-8')),
                            metadata=metadata)
        html = str(DocumentContentFormatter(document))
        expected_html = u"""\
<html xmlns="http://www.w3.org/1999/xhtml">
  <body><p>コンテンツ...</p></body>
</html>"""
        self.assertEqual(expected_html, unescape(html))


class DocumentSummaryFormatterTestCase(unittest.TestCase):
    def test_summary_w_one_tag(self):
        from ..adapters import DocumentSummaryFormatter
        from ..models import Document

        document = Document('title', io.BytesIO(b'contents'),
                            metadata={'summary': '<p>résumé</p>'})
        html = str(DocumentSummaryFormatter(document))
        self.assertEqual('<p>résumé</p>', html)

    def test_summary_w_just_text(self):
        from ..adapters import DocumentSummaryFormatter
        from ..models import Document

        document = Document('title', io.BytesIO(b'contents'),
                            metadata={'summary': 'résumé'})
        html = str(DocumentSummaryFormatter(document))
        expected = """\
<div class="description" data-type="description"\
 xmlns="http://www.w3.org/1999/xhtml">
  résumé
</div>"""
        self.assertEqual(expected, html)

    def test_summary_w_text_and_tags(self):
        from ..adapters import DocumentSummaryFormatter
        from ..models import Document

        document = Document('title', io.BytesIO(b'contents'),
                            metadata={'summary': 'résumé<p>etc</p><p>...</p>'})
        html = str(DocumentSummaryFormatter(document))
        expected = """\
<div class="description" data-type="description"\
 xmlns="http://www.w3.org/1999/xhtml">
  résumé<p>etc</p><p>...</p>
</div>"""
        self.assertEqual(expected, html)


class HTMLFormatterTestCase(unittest.TestCase):
    base_metadata = {
        'publishers': [],
        'created': '2013/03/19 15:01:16 -0500',
        'revised': '2013/06/18 15:22:55 -0500',
        'authors': [
            {'type': 'cnx-id',
             'name': 'Sponge Bob',
             'id': 'sbob'}],
        'editors': [],
        'copyright_holders': [],
        'illustrators': [],
        'subjects': ['Science and Mathematics'],
        'translators': [],
        'keywords': ['Bob', 'Sponge', 'Rock'],
        'title': 'タイトル',
        'license_text': 'CC-By 4.0',
        'license_url': 'http://creativecommons.org/licenses/by/4.0/',
        'summary': "<p>summary</p>",
        'version': 'draft',
        }

    def xpath(self, path):
        from ..html_parsers import HTML_DOCUMENT_NAMESPACES

        return self.root.xpath(path, namespaces=HTML_DOCUMENT_NAMESPACES)

    def test_document(self):
        from ..models import Document
        from ..adapters import HTMLFormatter

        # Build test document.
        metadata = self.base_metadata.copy()
        document = Document(
            metadata['title'],
            io.BytesIO(u'<p>コンテンツ...</p>'.encode('utf-8')),
            metadata=metadata)

        html = str(HTMLFormatter(document))
        html = unescape(html)
        self.root = etree.fromstring(html.encode('utf-8'))

        self.assertIn(u'<title>タイトル</title>', html)
        self.assertIn(u'<p>コンテンツ...</p>', html)

        self.assertEqual(
            u'タイトル',
            self.xpath('//*[@data-type="document-title"]/text()')[0])

        self.assertEqual(
            'summary',
            self.xpath('//*[@class="description"]/xhtml:p/text()')[0])

        self.assertEqual(
            metadata['created'],
            self.xpath('//xhtml:meta[@itemprop="dateCreated"]/@content')[0])

        self.assertEqual(
            metadata['revised'],
            self.xpath('//xhtml:meta[@itemprop="dateModified"]/@content')[0])

    def test_document_pointer(self):
        from ..models import DocumentPointer
        from ..adapters import HTMLFormatter

        # Build test document pointer.
        pointer = DocumentPointer('pointer@1', {
            'title': self.base_metadata['title'],
            'cnx-archive-uri': 'pointer@1',
            'url': 'https://cnx.org/contents/pointer@1',
            })

        html = str(HTMLFormatter(pointer))
        html = unescape(html)
        self.root = etree.fromstring(html.encode('utf-8'))

        self.assertIn(u'<title>タイトル</title>', html)
        self.assertIn(
            u'<a href="https://cnx.org/contents/pointer@1">', html)

        self.assertEqual(
            u'タイトル',
            self.xpath('//*[@data-type="document-title"]/text()')[0])

        self.assertEqual(
            'pointer@1',
            self.xpath('//*[@data-type="cnx-archive-uri"]/@data-value')[0])

    def test_binder(self):
        from ..models import (Binder, TranslucentBinder, Document,
                              DocumentPointer)
        from ..adapters import HTMLFormatter

        # Build test binder.
        binder = Binder(self.base_metadata['title'], metadata={
            'title': self.base_metadata['title'],
            })

        metadata = self.base_metadata.copy()
        metadata.update({
            'title': "entrée",
            'derived_from_uri': 'http://cnx.org/contents/'
                                'dd68a67a-11f4-4140-a49f-b78e856e2262@1',
            'derived_from_title': "Taking Customers' Orders",
            })

        binder.append(Document('ingress', io.BytesIO(b'<p>Hello.</p>'),
                               metadata=metadata))

        translucent_binder = TranslucentBinder(metadata={'title': 'Kranken'})
        binder.append(translucent_binder)

        metadata = self.base_metadata.copy()
        metadata.update({
            'title': "egress",
            'cnx-archive-uri': 'e78d4f90-e078-49d2-beac-e95e8be70667'})
        translucent_binder.append(
            Document('egress', io.BytesIO(u'<p>hüvasti.</p>'.encode('utf-8')),
                     metadata=metadata))

        binder.append(DocumentPointer('pointer@1', {
            'title': 'Pointer',
            'cnx-archive-uri': 'pointer@1',
            'url': 'http://cnx.org/contents/pointer@1'}))

        html = str(HTMLFormatter(binder))
        html = unescape(html)
        self.root = etree.fromstring(html.encode('utf-8'))

        self.assertIn(u'<title>タイトル</title>', html)

        lis = self.xpath('//xhtml:nav/xhtml:ol/xhtml:li')
        self.assertEqual(3, len(lis))
        self.assertIn(lis[0][0].attrib['href'],
                      ['ingress@draft.xhtml', 'ingress@draft.xht'])
        self.assertEqual(u'entrée', lis[0][0].text)
        self.assertEqual('Kranken', lis[1][0].text)
        self.assertIn(lis[2][0].attrib['href'],
                      ['pointer@1.xhtml', 'pointer@1.xht'])
        self.assertEqual('Pointer', lis[2][0].text)

        lis = self.xpath('//xhtml:nav/xhtml:ol/xhtml:li[2]/xhtml:ol/xhtml:li')
        self.assertEqual(1, len(lis))
        self.assertIn(lis[0][0].attrib['href'],
                      ['egress@draft.xhtml', 'egress@draft.xht'])
        self.assertEqual('egress', lis[0][0].text)

    def test_translucent_binder(self):
        from ..models import (TranslucentBinder, Document)
        from ..adapters import HTMLFormatter

        # Build test translucent binder.
        binder = TranslucentBinder(metadata={
            'title': self.base_metadata['title'],
            })

        metadata = self.base_metadata.copy()
        metadata.update({
            'title': "entrée",
            'derived_from_uri': 'http://cnx.org/contents/'
                                'dd68a67a-11f4-4140-a49f-b78e856e2262@1',
            'derived_from_title': "Taking Customers' Orders",
            })

        binder.append(Document('ingress', io.BytesIO(b'<p>Hello.</p>'),
                               metadata=metadata))

        html = str(HTMLFormatter(binder))
        html = unescape(html)
        self.root = etree.fromstring(html.encode('utf-8'))

        self.assertIn(u'<title>タイトル</title>', html)

        lis = self.xpath('//xhtml:nav/xhtml:ol/xhtml:li')
        self.assertEqual(1, len(lis))
        self.assertIn(lis[0][0].attrib['href'],
                      ['ingress@draft.xhtml', 'ingress@draft.xht'])
        self.assertEqual(u'entrée', lis[0][0].text)


@mock.patch('mimetypes.guess_extension', last_extension)
class SingleHTMLFormatterTestCase(unittest.TestCase):
    base_metadata = {
        'publishers': [],
        'created': '2016/03/04 17:05:20 -0500',
        'revised': '2013/03/05 09:35:24 -0500',
        'authors': [
            {'type': 'cnx-id',
             'name': 'Good Food',
             'id': 'yum'}],
        'editors': [],
        'copyright_holders': [],
        'illustrators': [],
        'subjects': ['Humanities'],
        'translators': [],
        'keywords': ['Food', 'デザート', 'Pudding'],
        'title': 'チョコレート',
        'license_text': 'CC-By 4.0',
        'license_url': 'http://creativecommons.org/licenses/by/4.0/',
        'summary': "<p>summary</p>",
        'version': 'draft',
        }

    maxDiff = None

    def setUp(self):
        from ..models import TranslucentBinder, Binder, Document, Resource

        with open(os.path.join(TEST_DATA_DIR, '1x1.jpg'), 'rb') as f:
            jpg = Resource('1x1.jpg', io.BytesIO(f.read()), 'image/jpeg')

        metadata = self.base_metadata.copy()
        contents = io.BytesIO(u"""\
<h1>Chocolate Desserts</h1>
<p>List of desserts to try:</p>
<ul><li>Chocolate Orange Tart,</li>
    <li>Hot Mocha Puddings,</li>
    <li>Chocolate and Banana French Toast,</li>
    <li>Chocolate Truffles...</li>
</ul><img src="/resources/1x1.jpg" /><p>チョコレートデザート</p>
""".encode('utf-8'))
        self.chocolate = Document('chocolate', contents, metadata=metadata,
                                  resources=[jpg])

        metadata = self.base_metadata.copy()
        metadata['title'] = 'Apple'
        contents = io.BytesIO(b"""\
<h1>Apple Desserts</h1>
<p>Here are some examples:</p>
<ul><li>Apple Crumble,</li>
    <li>Apfelstrudel,</li>
    <li>Caramel Apple,</li>
    <li>Apple Pie,</li>
    <li>Apple sauce...</li>
</ul>
""")
        self.apple = Document('apple', contents, metadata=metadata)

        metadata = self.base_metadata.copy()
        metadata['title'] = 'Lemon'
        contents = io.BytesIO(b"""\
<h1>Lemon Desserts</h1>
<p>Yum! <img src="/resources/1x1.jpg" /></p>
<ul><li>Lemon &amp; Lime Crush,</li>
    <li>Lemon Drizzle Loaf,</li>
    <li>Lemon Cheesecake,</li>
    <li>Raspberry &amp; Lemon Polenta Cake...</li>
</ul>
""")
        self.lemon = Document('lemon', contents, metadata=metadata,
                              resources=[jpg])

        metadata = self.base_metadata.copy()
        metadata['title'] = 'Citrus'
        self.citrus = TranslucentBinder([self.lemon], metadata=metadata)

        self.fruity = TranslucentBinder([self.apple, self.lemon, self.citrus],
                                        metadata={'title': 'Fruity'},
                                        title_overrides=[
                                            self.apple.metadata['title'],
                                            u'レモン', 'citrus'])

        with open(os.path.join(TEST_DATA_DIR, 'cover.png'), 'rb') as f:
            cover_png = Resource(
                'cover.png', io.BytesIO(f.read()), 'image/png')

        self.desserts = Binder(
            'Desserts', [self.fruity, self.chocolate],
            metadata={'title': 'Desserts'}, resources=[cover_png])

    def test_binder(self):
        from ..adapters import SingleHTMLFormatter

        page_path = os.path.join(TEST_DATA_DIR, 'desserts-single-page.html')
        with open(page_path, 'r') as f:
            self.assertMultiLineEqual(
                f.read(), str(SingleHTMLFormatter(self.desserts)))

    def test_str_unicode_bytes(self):
        from ..adapters import SingleHTMLFormatter

        html = bytes(SingleHTMLFormatter(self.desserts))
        if IS_PY3:
            self.assertEqual(
                html, str(SingleHTMLFormatter(self.desserts)).encode('utf-8'))
        else:
            self.assertEqual(
                html, str(SingleHTMLFormatter(self.desserts)))
            self.assertEqual(
                html,
                unicode(SingleHTMLFormatter(self.desserts)).encode('utf-8'))
