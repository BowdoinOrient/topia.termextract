from __future__ import print_function

#!/usr/bin/python
# -*- coding: utf8 -*-
############################################################################## #
# Copyright (c) 2009 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""POS Tagger

$Id: tag.py 100555 2009-05-30 15:26:12Z srichter $
"""
import os
import re

# Timeout re requests
from .timeout import timeout, TimeoutError

from zope.interface import implementer

from topia.termextract import interfaces

ORIG_TERM_SPEC = re.compile('([^a-zA-Z]*)([a-zA-Z-\.]*[a-zA-Z])([^a-zA-Z]*[a-zA-Z]*)')
# Modified by jpt
# regex [^\W\d_] = [a-zA-Z] with Unicode alphabetic character.
# See: http://stackoverflow.com/questions/2039140/python-re-how-do-i-match-an-alpha-character/2039476#2039476
TERM_SPEC = re.compile('([\W\d_]*)(([^\W\d_]?[-\.]?)*[^\W\d_])([\W\d_]*[^\W\d_]*)', re.UNICODE)
DATA_DIRECTORY = os.path.join(os.path.dirname(__file__), 'data')


def correctDefaultNounTag(idx, tagged_term, tagged_terms, lexicon):
    """Determine whether a default noun is plural or singular."""
    term, tag, norm = tagged_term
    if tag == 'NND':
        if term.endswith('s'):
            tagged_term[1] = 'NNS'
            tagged_term[2] = term[:-1]
        else:
            tagged_term[1] = 'NN'

def verifyProperNounAtSentenceStart(idx, tagged_term, tagged_terms, lexicon):
    """Verify that noun at sentence start is truly proper."""
    term, tag, norm = tagged_term
    if (tag in ('NNP', 'NNPS') and
        (idx == 0 or tagged_terms[idx-1][1] == '.')):
        lower_term = term.lower()
        lower_tag = lexicon.get(lower_term)
        if lower_tag in ('NN', 'NNS'):
            tagged_term[0] = tagged_term[2] = lower_term
            tagged_term[1] = lower_tag

def determineVerbAfterModal(idx, tagged_term, tagged_terms, lexicon):
    "Determine the verb after a modal verb to avoid accidental noun detection."
    term, tag, norm = tagged_term
    if tag != 'MD':
        return
    len_terms = len(tagged_terms)
    idx += 1
    while idx < len_terms:
        if tagged_terms[idx][1] == 'RB':
            idx += 1
            continue
        if tagged_terms[idx][1] == 'NN':
            tagged_terms[idx][1] = 'VB'
        break

def normalizePluralForms(idx, tagged_term, tagged_terms, lexicon):
    term, tag, norm = tagged_term
    if tag in ('NNS', 'NNPS') and term == norm:
        # Plural form ends in "s"
        singular = term[:-1]
        if (term.endswith('s') and
            singular in lexicon):
            tagged_term[2] = singular
            return
        # Plural form ends in "es"
        singular = term[:-2]
        if (term.endswith('es') and
            singular in lexicon):
            tagged_term[2] = singular
            return
        # Plural form ends in "ies" (from "y")
        singular = term[:-3]+'y'
        if (term.endswith('ies') and
            singular in lexicon):
            tagged_term[2] = singular
            return

@implementer(interfaces.ITagger)
class Tagger(object):

    rules = (
        correctDefaultNounTag,
        verifyProperNounAtSentenceStart,
        determineVerbAfterModal,
        normalizePluralForms,
        )

    def __init__(self, language='english'):
        self.language = language

    def initialize(self):
        """See interfaces.ITagger"""
        filename = os.path.join(DATA_DIRECTORY, '%s-lexicon.txt' %self.language)
        file = open(filename, 'r')
        self.tags_by_term = dict([line[:-1].split(' ')[:2] for line in file])
        file.close()

    def tokenize(self, text):
        """See interfaces.ITagger.
        Split is true if this token originally had a space after it."""
        split = []
        terms = []
        for term in re.split('\s', text):
            # If the term is empty, skip it, since we probably just have
            # multiple whitespace cahracters.
            if term == '':
                continue
            # Now, a word can be preceded or succeeded by symbols, so let's
            # split those out
            @timeout(1)
            def slow_match(term):
                return TERM_SPEC.search(term)
            try:
                match = slow_match(term)
            except TimeoutError:
                print("Ugh")
            if match is None:
                terms.append(term)
                split.append(True)
                continue

            # In the new TERM_SPEC, skip the third regex group
            # -jpt
#            import sys
#            print >> sys.stderr, "match groups =", repr(match.groups()), term.encode("utf-8")
            match_groups = match.groups()[0], match.groups()[1], match.groups()[3]
            for subTerm in match_groups:
                if subTerm != '':
                    terms.append(subTerm)
                    split.append(False)
            split[-1] = True
        return split, terms

    def tag(self, terms):
        """See interfaces.ITagger"""
        tagged_terms = []
        # Phase 1: Assign the tag from the lexicon. If the term is not found,
        # it is assumed to be a default noun (NND).
        for term in terms:
            tagged_terms.append(
                [term, self.tags_by_term.get(term, 'NND'), term])
        # Phase 2: Run through some rules to improve the term tagging and
        # normalized form.
        for idx, tagged_term in enumerate(tagged_terms):
            for rule in self.rules:
                rule(idx, tagged_term, tagged_terms, self.tags_by_term)
        return tagged_terms

    def __call__(self, text):
        """See interfaces.ITagger"""
        split, terms = self.tokenize(text)
        return split, self.tag(terms)

    def __repr__(self):
        return '<%s for %s>' %(self.__class__.__name__, self.language)
