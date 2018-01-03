# -*- coding: utf-8 -*-
import cssutils
import re

from bs4 import BeautifulSoup, element
from copy import copy

try:
    # Python 2
    from urlparse import parse_qs, urlsplit
except ImportError:
    # Python 3
    from urllib.parse import parse_qs, urlsplit

try:
    # Python 2
    unicode
except NameError:
    # Python 3
    unicode = str

ATTR_WHITELIST = {
    'a': ['href'],
    'img': ['src', 'alt'],
}

STYLE_WHITELIST = {
    'font-weight': ['700', 'bold'],
    'font-style': ['italic'],
    'text-decoration': ['underline']
}


class CopyDoc:
    """
    Clean up Google Doc html.

    To use, create a doc parser instance:

    .. code:: python

        parser = CopyDoc('<html><body><h1>My fake doc</h1></body></html>')

    Access rendered, parsed document:

    .. code:: python

        print(str(parser))

    Access parsed, Beautifulsoup object:

    ..code:: python

        soup = parser.soup
    """
    def __init__(self, html_string, tokens=[]):
        """
        Constructor takes an HTML string and sets up object.
        """
        self.soup = BeautifulSoup(html_string, 'html.parser')
        self.stylesheet = self.build_stylesheet()
        self.tags_blacklist = []
        self.tokens = tokens
        self.parse()

    def build_stylesheet(self):
        selectors = {}

        styles = self.soup.select('style')
        for style in styles:
            css = cssutils.parseString(style.encode_contents())
            for rule in css:
                if rule.type == rule.STYLE_RULE:
                    style = rule.selectorText
                    selectors[style] = {}
                    for item in rule.style:
                        propertyname = item.name
                        value = item.value
                        selectors[style][propertyname] = value

        return selectors

    def parse(self):
        """
        Run all parsing functions.
        """

        for tag in self.soup.findAll('span'):
            self.create_italic(tag)
            self.create_strong(tag)
            self.create_underline(tag)
            self.unwrap_span(tag)

        for tag in self.soup.findAll('a'):
            self.remove_comments(tag)
            self.check_next(tag)

        if self.soup.body:
            for tag in self.soup.body.findAll():
                self.remove_empty(tag)
                self.remove_inline_comment(tag)
                self.parse_attrs(tag)
                for token, target in self.tokens:
                    self.find_token(tag, token, target)

                self.remove_blacklisted_tags(tag)

    def remove_comments(self, tag):
        """
        Remove comments.
        """
        if tag.get('id', '').startswith('cmnt'):
            tag.parent.extract()

    def check_next(self, tag):
        """
        If next tag is link with same href, combine them.
        """
        if (type(tag.next_sibling) == element.Tag and
                tag.next_sibling.name == 'a'):

            next_tag = tag.next_sibling
            if tag.get('href') and next_tag.get('href'):
                href = self._parse_href(tag.get('href'))
                next_href = self._parse_href(next_tag.get('href'))

                if href == next_href:
                    next_text = next_tag.get_text()
                    tag.append(next_text)
                    self.tags_blacklist.append(next_tag)

    def remove_blacklisted_tags(self, tag):
        if tag in self.tags_blacklist:
            tag.decompose()

    def create_italic(self, tag):
        """
        See if span tag has italic style and wrap with em tag.
        """
        classes = tag.get('class', [])
        for class_name in classes:
            styles = self.stylesheet['.{0}'.format(class_name)]

            for key, value in styles.items():
                if key == 'font-style' and value == 'italic':
                    tag.wrap(self.soup.new_tag('em'))

    def create_strong(self, tag):
        """
        See if span tag has bold style and wrap with strong tag.
        """
        classes = tag.get('class', [])
        for class_name in classes:
            styles = self.stylesheet['.{0}'.format(class_name)]

            for key, value in styles.items():
                if key == 'font-weight' and value in ['bold', '700']:
                    tag.wrap(self.soup.new_tag('strong'))

    def create_underline(self, tag):
        """
        See if span tag has underline style and wrap with u tag.
        """
        classes = tag.get('class', [])
        for class_name in classes:
            styles = self.stylesheet['.{0}'.format(class_name)]

            for key, value in styles.items():
                if key == 'text-decoration' and value == 'underline':
                    tag.wrap(self.soup.new_tag('u'))

    def unwrap_span(self, tag):
        """
        Remove span tags while preserving contents.
        """
        tag.unwrap()

    def parse_attrs(self, tag):
        """
        Reject attributes not defined in ATTR_WHITELIST.
        """
        if tag.name in ATTR_WHITELIST.keys():
            attrs = copy(tag.attrs)
            for attr, value in attrs.items():
                if attr in ATTR_WHITELIST[tag.name]:
                    tag.attrs[attr] = self._parse_attr(tag.name, attr, value)
                else:
                    del tag.attrs[attr]
        else:
            tag.attrs = {}

    def remove_empty(self, tag):
        """
        Remove non-self-closing tags with no children *and* no content.
        """
        has_children = len(tag.contents)
        has_text = len(list(tag.stripped_strings))
        if not has_children and not has_text and not tag.is_empty_element:
            tag.extract()

    def find_token(self, tag, token, attr):
        try:
            if not hasattr(self, attr) or not getattr(self, attr):
                text = tag.text
                if text.startswith(token):
                    setattr(self, attr, text.split(':', 1)[-1].strip())
                    tag.extract()
        except TypeError:
            pass

    def remove_inline_comment(self, tag):
        text = tag.text
        if text.startswith('##'):
            tag.extract()

    def clean_linebreaks(self, tag):
        """
        get unicode string without any other content transformation.
        and clean extra spaces
        """
        stripped = tag.decode(formatter=None)
        stripped = re.sub('\s+', ' ', stripped)
        stripped = re.sub('\n', '', stripped)
        return stripped

    def _parse_href(self, href):
        """
        Extract "real" URL from Google redirected url by getting `q`
        querystring parameter.
        """
        params = parse_qs(urlsplit(href).query)
        return params.get('q')

    def _parse_attr(self, tagname, attr, value):
        """
        Parse attribute. Delegate to href parser for hrefs, otherwise return
        value.
        """
        if tagname == 'a' and attr == 'href':
            return self._parse_href(value)
        else:
            return value

    def __unicode__(self):
        if not self.soup.body:
            return ''
        else:
            return ''.join([unicode(self.clean_linebreaks(tag))
                            for tag in self.soup.body.children])

    def __str__(self):
        if not self.soup.body:
            return ''
        else:
            return ''.join([str(self.clean_linebreaks(tag))
                            for tag in self.soup.body.children])
