# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os
import io
import tempfile
import zipfile
from collections import Sequence

from lxml import etree


__all__ = ('EPUB', 'Package', 'Item',)


# ./mimetype
EPUB_MIMETYPE_RELATIVE_PATH = "mimetype"
EPUB_MIMETYPE_CONTENTS = "application/epub+zip"
# ./META-INF/container.xml
EPUB_CONTAINER_XML_RELATIVE_PATH = "META-INF/container.xml"
EPUB_CONTAINER_XML_NAMESPACES = {
    'ns': "urn:oasis:names:tc:opendocument:xmlns:container"
    }
# ./*.opf
EPUB_OPF_NAMESPACES = {
    'opf': "http://www.idpf.org/2007/opf",
    'dc': "http://purl.org/dc/elements/1.1/",
    'lrmi': "http://lrmi.net/the-specification",
    }


class MissingNavigationError(Exception):
    """Raised when a ``Package`` is missing a navigation document.
    http://www.idpf.org/epub/30/spec/epub30-overview.html#sec-nav
    """


class AdditionalNavigationError(Exception):
    """Raised when a ``Package`` has more then one navigation document."""


class MissingMetadataError(Exception):
    """Raised when a piece of required metadata is missing from the document.
    """


class EPUB(Sequence):
    """Represents an EPUB3 file structure in object form.
    It is designed to work with .epub files (zip files),
    but will uncompress them to a temporary location before working with them.

    """

    def __init__(self, packages=None, root=None):
        self._packages = packages is None and [] or packages
        self._root = root

    @classmethod
    def from_file(cls, file):
        """Create the object from a *file* or *file-like object*.
        The file can point to an ``.epub`` file or a directory
        (the contents of which reflect
        the internal struture of an ``.epub`` archive).
        If given an non-archive file,
        this structure will be used when reading in and parsing the epub.
        If an archive file is given,
        it will be extracted to the temporal filesystem.
        """
        root = None
        if zipfile.is_zipfile(file):
            unpack_dir = tempfile.mkdtemp('-epub')
            # Extract the epub to the current working directory.
            with zipfile.ZipFile(file, 'r') as zf:
                zf.extractall(path=unpack_dir)
            root = unpack_dir
        elif os.path.isdir(file):
            root = file
        else:
            raise TypeError("Can't decipher what should be done "
                            "with the given file.")

        # NOTE We ignore the mimetype file, as it's not extremely important
        #      to anything done here.

        # Build a blank epub object then parse the packages.
        container_xml_filepath = os.path.join(root,
                                              EPUB_CONTAINER_XML_RELATIVE_PATH)
        container_xml = etree.parse(container_xml_filepath)

        packages = []
        for pkg_filepath in container_xml.xpath(
                '//ns:rootfile/@full-path',
                namespaces=EPUB_CONTAINER_XML_NAMESPACES):
            filepath = os.path.join(root, pkg_filepath)
            packages.append(Package.from_file(filepath))
        return cls(packages=packages, root=root)

    def to_file(self, file):
        """Export to ``file``, which is a *file* or *file-like object*."""
        raise NotImplementedError()

    # ABC methods for MutableSequence
    def __getitem__(self, k):
        return self._packages[k]

    def __len__(self):
        return len(self._packages)


class OPFParser:
    """Parse an ``.opf`` xml document's metadata.
    This class is callable to respond as a function
    after inititiation as a singleton.
    The work for parsing the metadata is methodized to provide
    detailed exceptions.

    """
    namespaces = EPUB_OPF_NAMESPACES
    metadata_required_keys = (
        'publisher', 'publication_message',
        )
    metadata_optional_keys = (
        'title', 'identifier', 'language', 'license_text', 'license_url',
        )

    def __init__(self, opf_xml):
        """Given the opf_xml (an ``lxml.etree.ElementTree``),
        parse the metadata fields on access.
        """
        self._xml = opf_xml

    def parser(self, xpath, prefix="/opf:package/opf:metadata/"):
        metadata_prefix = "/opf:package/opf:metadata/"
        values = self._xml.xpath(metadata_prefix + xpath,
                                 namespaces=self.namespaces)
        return values

    @property
    def title(self):
        items = self.parser('dc:title/text()')
        try:
            value = items[0]
        except IndexError:
            value = None
        return value

    @property
    def publisher(self):
        items = self.parser('dc:creator/text()')
        try:
            value = items[0]
        except IndexError:
            value = None
        return value

    @property
    def publication_message(self):
        items = self.parser('opf:meta[@property="publicationMessage"]/text()')
        try:
            value = items[0]
        except IndexError:
            value = None
        return value

    @property
    def identifier(self):
        items = self.parser('dc:identifier/text()')
        try:
            value = items[0]
        except IndexError:
            value = None
        return value

    @property
    def language(self):
        items = self.parser('dc:language/text()')
        try:
            value = items[0]
        except IndexError:
            value = None
        return value

    @property
    def license_text(self):
        items = self.parser('dc:rights/text()')
        try:
            value = items[0]
        except IndexError:
            value = None
        return value

    @property
    def license_url(self):
        items = self.parser('opf:link[@rel="cc:license"]/@href')
        try:
            value = items[0]
        except IndexError:
            value = None
        return value

    @property
    def metadata(self):
        items = {}
        keyrings = (self.metadata_required_keys, self.metadata_optional_keys,)
        for keyring in keyrings:
            for key in keyring:
                # TODO On refactoring of the metadata properties,
                # required fields will raise MissingMetadataError,
                # but for now do that here.
                value = getattr(self, key)
                if key in self.metadata_required_keys and value is None:
                    raise MissingMetadataError(
                        "A value for '{}' could not be found.".format(key))
                elif value is None:
                    continue
                items[key] = value
        return items


class Package(Sequence):
    """EPUB3 package"""

    def __init__(self, items, metadata=None):
        self.metadata = metadata or {}
        self._items = items
        navigation_items = [i for i in self._items if i.is_navigation]
        if len(navigation_items) == 0:
            raise MissingNavigationError("Navigation item not found")
        elif len(navigation_items) > 1:
            raise AdditionalNavigationError(
                "Only one navigation item can exist "
                "per package. The given value is a second "
                "navigation item.")
        else:
            index = self._items.index(navigation_items[0])
            self._navigation_item_index = index

    @classmethod
    def from_file(cls, file):
        """Create the object from a *file* or *file-like object*."""
        opf_xml = etree.parse(file)
        # Check if ``file`` is file-like.
        if hasattr(file, 'read'):
            root = os.path.abspath(os.path.dirname(file.name))
        else:  # ...a filepath
            root = os.path.abspath(os.path.dirname(file))
        parser = OPFParser(opf_xml)

        # Roll through the item entries
        manifest = opf_xml.xpath('/opf:package/opf:manifest/opf:item',
                                 namespaces=EPUB_OPF_NAMESPACES)
        pkg_items = []
        for item in manifest:
            absolute_filepath = os.path.join(root, item.get('href'))
            properties = item.get('properties', '').split()
            is_navigation = 'nav' in properties
            media_type = item.get('media-type')
            pkg_items.append(Item.from_file(absolute_filepath,
                                          media_type=media_type,
                                          is_navigation=is_navigation,
                                          properties=properties))
        # Ignore spine ordering, because it is not important
        #   for our use cases.
        return cls(pkg_items, parser.metadata)

    @property
    def navigation(self):
        return self._items[self._navigation_item_index]

    def grab_by_name(self, name):
        try:
            return [i for i in self._items if i.name == name][0]
        except IndexError:
            raise KeyError("'{}' not found in package.".format(name))

    # ABC methods for Sequence
    def __getitem__(self, k):
        return self._items[k]

    def __len__(self):
        return len(self._items)


class Item:
    """Package item"""

    def __init__(self, name, data=None, media_type=None,
                 is_navigation=False, properties=[], **kwargs):
        self.name = name
        self.data = data
        self.media_type = media_type
        self.is_navigation = bool(is_navigation)
        self.properties = properties

    @classmethod
    def from_file(cls, filepath, **kwargs):
        name = os.path.basename(filepath)
        with open(filepath, 'rb') as fb:
            data = io.BytesIO(fb.read())
        return cls(name, data, **kwargs)
