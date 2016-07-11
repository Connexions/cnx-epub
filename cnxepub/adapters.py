# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from __future__ import unicode_literals
import os
import io
import logging
import mimetypes
from copy import deepcopy

import jinja2
import lxml.html
from lxml import etree

from .epub import EPUB, Package, Item
from .formatters import HTMLFormatter
from .models import (
    flatten_model, flatten_to_documents,
    content_to_etree, etree_to_content,
    Binder, TranslucentBinder,
    Document, Resource, DocumentPointer, CompositeDocument,
    TRANSLUCENT_BINDER_ID,
    INTERNAL_REFERENCE_TYPE,
    INLINE_REFERENCE_TYPE,
    )
from .html_parsers import (parse_metadata, parse_navigation_html_to_tree,
                           parse_resources, DocumentPointerMetadataParser,
                           HTML_DOCUMENT_NAMESPACES)

from .data_uri import DataURI


logger = logging.getLogger('cnxepub')


__all__ = (
    'adapt_package', 'adapt_item',
    'get_model_extensions',
    'make_epub', 'make_publication_epub',
    'BinderItem',
    'DocumentItem',
    'adapt_single_html',
    )


class AdaptationError(Exception):
    """Raised when data is not able to be adapted to the requested format."""


def adapt_package(package):
    """Adapts ``.epub.Package`` to a ``BinderItem`` and cascades
    the adaptation downward to ``DocumentItem``
    and ``ResourceItem``.
    The results of this process provide the same interface as
    ``.models.Binder``, ``.models.Document`` and ``.models.Resource``.
    """
    navigation_item = package.navigation
    html = etree.parse(navigation_item.data)
    tree = parse_navigation_html_to_tree(html, navigation_item.name)
    return _node_to_model(tree, package)


def adapt_item(item, package, filename=None):
    """Adapts ``.epub.Item`` to a ``DocumentItem``.

    """
    if item.media_type == 'application/xhtml+xml':
        try:
            html = etree.parse(item.data)
        except Exception as exc:
            logger.error("failed parsing {}".format(item.name))
            raise
        metadata = DocumentPointerMetadataParser(
            html, raise_value_error=False)()
        item.data.seek(0)
        if metadata.get('is_document_pointer'):
            model = DocumentPointerItem(item, package)
        else:
            model = DocumentItem(item, package)
    else:
        model = Resource(item.name, item.data, item.media_type,
                         filename or item.name)
    return model


def make_epub(binders, file):
    """Creates an EPUB file from a binder(s)."""
    if not isinstance(binders, (list, set, tuple,)):
        binders = [binders]
    epub = EPUB([_make_package(binder) for binder in binders])
    epub.to_file(epub, file)


def make_publication_epub(binders, publisher, publication_message, file):
    """Creates an epub file from a binder(s). Also requires
    publication information, meant to be used in a EPUB publication
    request.
    """
    if not isinstance(binders, (list, set, tuple,)):
        binders = [binders]
    packages = []
    for binder in binders:
        metadata = binder.metadata
        binder.metadata = deepcopy(metadata)
        binder.metadata.update({'publisher': publisher,
                                'publication_message': publication_message})
        packages.append(_make_package(binder))
        binder.metadata = metadata
    epub = EPUB(packages)
    epub.to_file(epub, file)


def get_model_extensions(binder):
    extensions = {}
    # Set model identifier file extensions.
    for model in flatten_model(binder):
        if isinstance(model, (Binder, TranslucentBinder,)):
            continue
        ext = mimetypes.guess_extension(model.media_type, strict=False)
        if ext is None:
            raise ValueError("Can't apply an extension to media-type '{}'."
                             .format(model.media_type))
        extensions[model.id] = ext
        extensions[model.ident_hash] = ext
    return extensions


def _make_package(binder):
    """Makes an ``.epub.Package`` from a  Binder'ish instance."""
    package_id = binder.id
    if package_id is None:
        package_id = hash(binder)

    package_name = "{}.opf".format(package_id)

    extensions = get_model_extensions(binder)

    template_env = jinja2.Environment(trim_blocks=True, lstrip_blocks=True)

    # Build the package item list.
    items = []
    # Build the binder as an item, specifically a navigation item.
    navigation_document = bytes(HTMLFormatter(binder, extensions))
    navigation_document_name = "{}{}".format(
        package_id,
        mimetypes.guess_extension('application/xhtml+xml', strict=False))
    item = Item(str(navigation_document_name),
                io.BytesIO(navigation_document),
                'application/xhtml+xml',
                is_navigation=True, properties=['nav'])
    items.append(item)
    resources = {}
    # Roll through the model list again, making each one an item.
    for model in flatten_model(binder):
        for resource in getattr(model, 'resources', []):
            resources[resource.id] = resource
            with resource.open() as data:
                item = Item(resource.id, data, resource.media_type)
            items.append(item)

        if isinstance(model, (Binder, TranslucentBinder,)):
            continue
        if isinstance(model, DocumentPointer):
            content = bytes(HTMLFormatter(model))
            item = Item(''.join([model.ident_hash, extensions[model.id]]),
                        io.BytesIO(content),
                        model.media_type)
            items.append(item)
            continue
        for reference in model.references:
            if reference.remote_type == INLINE_REFERENCE_TYPE:
                # has side effects - converts ref type to INTERNAL w/
                # appropriate uri, so need to replicate resource treatment from
                # above
                resource = _make_resource_from_inline(reference)
                model.resources.append(resource)
                resources[resource.id] = resource
                with resource.open() as data:
                    item = Item(resource.id, data, resource.media_type)
                items.append(item)
                reference.bind(resource, '../resources/{}')

            elif reference.remote_type == INTERNAL_REFERENCE_TYPE:
                filename = os.path.basename(reference.uri)
                resource = resources.get(filename)
                if resource:
                    reference.bind(resource, '../resources/{}')

        complete_content = bytes(HTMLFormatter(model))
        item = Item(''.join([model.ident_hash, extensions[model.id]]),
                    io.BytesIO(complete_content),
                    model.media_type)
        items.append(item)

    # Build the package.
    package = Package(package_name, items, binder.metadata)
    return package


def _make_resource_from_inline(reference):
    """Makes an ``models.Resource`` from a ``models.Reference``
       of type INLINE. That is, a data: uri"""
    uri = DataURI(reference.uri)
    data = io.BytesIO(uri.data)
    mimetype = uri.mimetype
    res = Resource('dummy', data, mimetype)
    res.id = res.filename
    return res


def _make_item(model):
    """Makes an ``.epub.Item`` from
    a ``.models.Document`` or ``.models.Resource``
    """
    item = Item(model.id, model.content, model.media_type)
    return item


def _node_to_model(tree_or_item, package, parent=None,
                   lucent_id=TRANSLUCENT_BINDER_ID):
    """Given a tree, parse to a set of models"""
    if 'contents' in tree_or_item:
        # It is a binder.
        tree = tree_or_item
        if tree['id'] == lucent_id:
            binder = TranslucentBinder(metadata={'title': tree['title']})
        else:
            package_item = package.grab_by_name(tree['id'])
            binder = BinderItem(package_item, package)
        for item in tree['contents']:
            node = _node_to_model(item, package, parent=binder,
                                  lucent_id=lucent_id)
            if node.metadata['title'] != item['title']:
                binder.set_title_for_node(node, item['title'])
        result = binder
    else:
        # It is a document.
        item = tree_or_item
        package_item = package.grab_by_name(item['id'])
        result = adapt_item(package_item, package)
    if parent is not None:
        parent.append(result)
    return result


def _id_from_metadata(metadata):
    """Given an item's metadata, discover the id."""
    # FIXME Where does the system identifier come from?
    system = 'cnx-archive'
    identifier = "{}-uri".format(system)
    return metadata.get(identifier)


class BinderItem(Binder):

    def __init__(self, item, package):
        self._item = item
        self._package = package
        html = etree.parse(self._item.data)
        metadata = parse_metadata(html)
        resources = [
            adapt_item(package.grab_by_name(resource['id']),
                       package, resource['filename'])
            for resource in parse_resources(html)]
        id = _id_from_metadata(metadata)
        super(BinderItem, self).__init__(
            id, metadata=metadata, resources=resources)


class DocumentPointerItem(DocumentPointer):

    def __init__(self, item, package):
        self._item = item
        self._package = package
        self._html = etree.parse(self._item.data)

        metadata = DocumentPointerMetadataParser(self._html)()
        id = _id_from_metadata(metadata)
        super(DocumentPointerItem, self).__init__(id, metadata=metadata)


class DocumentItem(Document):

    def __init__(self, item, package):
        self._item = item
        self._package = package
        self._html = etree.parse(self._item.data)

        metadata = parse_metadata(self._html)
        body = self._html.xpath('//xhtml:body',
                                namespaces=HTML_DOCUMENT_NAMESPACES)[0]
        metadata_nodes = self._html.xpath(
                                    "//xhtml:body/*[@data-type='metadata']",
                                    namespaces=HTML_DOCUMENT_NAMESPACES)
        for node in metadata_nodes:
            body.remove(node)
        for key in body.keys():
            if key in ('itemtype', 'itemscope'):
                body.attrib.pop(key)

        content = etree.tostring(self._html)

        id = _id_from_metadata(metadata)
        resources = None
        super(DocumentItem, self).__init__(id, content, metadata)

        # Based on the reference list, make a best effort
        # to acquire resources.
        resources = []
        for ref in self.references:
            if ref.remote_type == 'external':
                continue
            elif not ref.uri.find('../resources') >= 0:
                continue
            name = os.path.basename(ref.uri)
            try:
                resource = adapt_item(package.grab_by_name(name), package)
                ref.bind(resource, '../resources/{}')
                resources.append(resource)
            except KeyError:
                # When resources are missing, the problem is pushed off
                # to the rendering process, which will
                # raise a missing reference exception when necessary.
                pass
        self.resources = resources


def adapt_single_html(html):
    """Adapts a single html document generated by
    ``.formatters.SingleHTMLFormatter`` to a ``models.Binder``
    """
    html_root = etree.fromstring(html)
    # parse_metadata, parse_navigation_html_to_tree,
    # parse_resources, DocumentPointerMetadataParser

    metadata = parse_metadata(html_root.xpath('//*[@data-type="metadata"]')[0])
    id_ = metadata['cnx-archive-uri'] or 'book'

    binder = Binder(id_, metadata=metadata)
    nav_tree = parse_navigation_html_to_tree(html_root, id_)

    body = html_root.xpath('//xhtml:body', namespaces=HTML_DOCUMENT_NAMESPACES)
    _adapt_single_html_tree(binder, body[0], nav_tree)

    return binder


def _adapt_single_html_tree(parent, elem, nav_tree, pages_by_id=None, depth=0):
    title_overrides = [i.get('title') for i in nav_tree['contents']]

    def fix_generated_ids(page, content):
        for i in content.xpath('.//*[starts-with(@id, "auto_")]'):
            i.attrib['id'] = i.attrib['id'].split('_', 2)[-1]
        for i in content.xpath('.//*[starts-with(@href, "#auto_")]',
                               namespaces=HTML_DOCUMENT_NAMESPACES):
            _, page_id, target = i.attrib['href'].split('_', 2)
            target_page = pages_by_id[page_id]
            if target_page is page:
                i.attrib['href'] = '#{}'.format(target)
            else:
                i.attrib['href'] = '/contents/{}#{}'.format(
                    target_page.id, target)
        page_id_xpath = ' or '.join([
            '@href = "#{}"'.format(page_id)
            for page_id in pages_by_id])
        for i in content.xpath('.//*[{}]'.format(page_id_xpath)):
            i.attrib['href'] = '/contents/{}'.format(
                i.attrib['href'].split('#')[-1])

    # A dictionary to allow look up a document using the page id (the id
    # attribute of <div data-type="page|composite-page">)
    if pages_by_id is None:
        pages_by_id = {}

    # Adapt each <div data-type="unit|chapter|page|composite-page"> into
    # translucent binders, documents and composite documents
    for child in elem.getchildren():
        if child.attrib.get('data-type') in ['unit', 'chapter']:
            title = child.xpath('*[@data-type="document-title"]/text()',
                                namespaces=HTML_DOCUMENT_NAMESPACES)[0]
            tbinder = TranslucentBinder(metadata={'title': title})
            _adapt_single_html_tree(tbinder, child,
                                    nav_tree['contents'].pop(0),
                                    pages_by_id=pages_by_id, depth=depth+1)
            parent.append(tbinder)
        elif child.attrib.get('data-type') in ['page', 'composite-page']:
            nav_tree['contents'].pop(0)
            metadata = parse_metadata(child)
            id_ = metadata.get('cnx-archive-uri') or child.attrib.get('id')
            metadata_nodes = child.xpath("*[@data-type='metadata']",
                                         namespaces=HTML_DOCUMENT_NAMESPACES)
            for node in metadata_nodes:
                child.remove(node)
            for key in child.keys():
                if key in ('itemtype', 'itemscope'):
                    child.attrib.pop(key)

            contents = etree.tostring(child)
            model = {
                'page': Document,
                'composite-page': CompositeDocument,
                }[child.attrib['data-type']]
            document = model(id_, contents, metadata=metadata)
            parent.append(document)

            pages_by_id[child.attrib.get('id', document.id)] = document

    # Assign title overrides
    if len(parent) != len(title_overrides):
        logger.error('Skipping title overrides -'
                     'mismatched numbers: parent: {}, titles: {}'.format(
                         len(parent), len(title_overrides)))
        raise AdaptationError

    for i, node in enumerate(parent):
        parent.set_title_for_node(node, title_overrides[i])

    # For each page in the book, look for links to #auto_ and replace it with
    # either the value without #auto_{id} or /contents/{id}#target
    # only fixup links at top, for whole book
    if depth == 0:
        for page in flatten_to_documents(parent):
            etree_ = content_to_etree(page.content)
            fix_generated_ids(page, etree_)
            string_types = (type(u''), type(b''))
            page.content = etree_to_content(etree_)
