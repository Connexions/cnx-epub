# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os
import io
import unittest


class TreeUtilityTestCase(unittest.TestCase):

    def make_binder(self, id=None, nodes=None, metadata=None):
        """Make a ``Binder`` instance.
        If ``id`` is not supplied, a ``FauxBinder`` is made.
        """
        from ..models import Binder, TranslucentBinder
        if id is None:
            binder = TranslucentBinder(nodes, metadata)
        else:
            binder = Binder(id, nodes, metadata)
        return binder

    def make_document(self, id, metadata={}):
        from ..models import Document
        return Document(id, io.BytesIO(b''), metadata=metadata)

    def test_binder_to_tree(self):
        binder = self.make_binder(
            '8d75ea29',
            metadata={'version': '3', 'title': "Book One"},
            nodes=[
                self.make_binder(
                    None,
                    metadata={'title': "Part One"},
                    nodes=[
                        self.make_binder(
                            None,
                            metadata={'title': "Chapter One"},
                            nodes=[
                                self.make_document(
                                    id="e78d4f90",
                                    metadata={'version': '3',
                                              'title': "Document One"})]),
                        self.make_binder(
                            None,
                            metadata={'title': "Chapter Two"},
                            nodes=[
                                self.make_document(
                                    id="3c448dc6",
                                    metadata={'version': '1',
                                              'title': "Document Two"})])]),
                self.make_binder(
                    None,
                    metadata={'title': "Part Two"},
                    nodes=[
                        self.make_binder(
                            None,
                            metadata={'title': "Chapter Three"},
                            nodes=[
                                self.make_document(
                                    id="ad17c39c",
                                    metadata={'version': '2',
                                              'title': "Document Three"})])]),
                self.make_binder(
                    None,
                    metadata={'title': "Part Three"},
                    nodes=[
                        self.make_binder(
                            None,
                            metadata={'title': "Chapter Four"},
                            nodes=[
                                self.make_document(
                                    id="7c52af05",
                                    metadata={'version': '1',
                                              'title': "Document Four"})])])])

        expected_tree = {
            'id': '8d75ea29@3',
            'contents': [
                {'id': 'subcol',
                 'contents': [
                     {'id': 'subcol',
                      'contents': [
                          {'id': 'e78d4f90@3',
                           'title': 'Document One'}],
                      'title': 'Chapter One'},
                     {'id': 'subcol',
                      'contents': [
                          {'id': '3c448dc6@1',
                           'title': 'Document Two'}],
                      'title': 'Chapter Two'}],
                 'title': 'Part One'},
                {'id': 'subcol',
                 'contents': [
                    {'id': 'subcol',
                     'contents': [
                         {'id': 'ad17c39c@2',
                          'title': 'Document Three'}],
                     'title': 'Chapter Three'}],
                 'title': 'Part Two'},
                {'id': 'subcol',
                 'contents': [
                     {'id': 'subcol',
                      'contents': [
                          {'id': '7c52af05@1',
                           'title': 'Document Four'}],
                      'title': 'Chapter Four'}],
                 'title': 'Part Three'}],
            'title': 'Book One'}

        from ..models import model_to_tree
        tree = model_to_tree(binder)
        self.assertEqual(tree, expected_tree)

    def test_flatten_model(self):
        binder = self.make_binder(
            '8d75ea29',
            metadata={'version': '3', 'title': "Book One"},
            nodes=[
                self.make_binder(
                    None,
                    metadata={'title': "Part One"},
                    nodes=[
                        self.make_binder(
                            None,
                            metadata={'title': "Chapter One"},
                            nodes=[
                                self.make_document(
                                    id="e78d4f90",
                                    metadata={'version': '3',
                                              'title': "Document One"})]),
                        self.make_binder(
                            None,
                            metadata={'title': "Chapter Two"},
                            nodes=[
                                self.make_document(
                                    id="3c448dc6",
                                    metadata={'version': '1',
                                              'title': "Document Two"})])]),
                self.make_binder(
                    None,
                    metadata={'title': "Part Two"},
                    nodes=[
                        self.make_binder(
                            None,
                            metadata={'title': "Chapter Three"},
                            nodes=[
                                self.make_document(
                                    id="ad17c39c",
                                    metadata={'version': '2',
                                              'title': "Document Three"})])])])
        expected_titles = [
            'Book One',
            'Part One',
            'Chapter One', 'Document One',
            'Chapter Two', 'Document Two',
            'Part Two',
            'Chapter Three', 'Document Three']

        from ..models import flatten_model
        titles = [m.metadata['title'] for m in flatten_model(binder)]
        self.assertEqual(titles, expected_titles)

    def test_flatten_to_documents(self):
        binder = self.make_binder(
            '8d75ea29',
            metadata={'version': '3', 'title': "Book One"},
            nodes=[
                self.make_binder(
                    None,
                    metadata={'title': "Part One"},
                    nodes=[
                        self.make_binder(
                            None,
                            metadata={'title': "Chapter One"},
                            nodes=[
                                self.make_document(
                                    id="e78d4f90",
                                    metadata={'version': '3',
                                              'title': "Document One"})]),
                        self.make_binder(
                            None,
                            metadata={'title': "Chapter Two"},
                            nodes=[
                                self.make_document(
                                    id="3c448dc6",
                                    metadata={'version': '1',
                                              'title': "Document Two"})])]),
                self.make_binder(
                    None,
                    metadata={'title': "Part Two"},
                    nodes=[
                        self.make_binder(
                            None,
                            metadata={'title': "Chapter Three"},
                            nodes=[
                                self.make_document(
                                    id="ad17c39c",
                                    metadata={'version': '2',
                                              'title': "Document Three"})])])])
        expected_titles = ['Document One', 'Document Two', 'Document Three']

        from ..models import flatten_to_documents
        titles = [d.metadata['title'] for d in flatten_to_documents(binder)]
        self.assertEqual(titles, expected_titles)