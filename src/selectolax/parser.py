from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser as _HTMLParser


class _Element:
    def __init__(self, tag: str, attrs: dict[str, str], parent=None):
        self.tag = tag
        self.attrs = attrs
        self.parent = parent
        self.children = []
        self.text_parts = []

    def append_text(self, text: str):
        self.text_parts.append(text)

    def full_text(self) -> str:
        return ''.join(self.text_parts + [child.full_text() for child in self.children])


class _TreeBuilder(_HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = _Element('document', {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        element = _Element(tag, {k: v or '' for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(element)
        self.stack.append(element)

    def handle_endtag(self, tag):
        for idx in range(len(self.stack)-1, 0, -1):
            if self.stack[idx].tag == tag:
                del self.stack[idx:]
                break

    def handle_data(self, data):
        self.stack[-1].append_text(data)


class Node:
    def __init__(self, element: _Element):
        self.element = element
        self.attributes = element.attrs

    def text(self, strip: bool = False):
        value = unescape(self.element.full_text())
        return ' '.join(value.split()) if strip else value

    def css(self, selector: str):
        return [Node(item) for item in _select(self.element, selector)]

    def css_first(self, selector: str):
        matches = self.css(selector)
        return matches[0] if matches else None


class HTMLParser:
    def __init__(self, html: str):
        parser = _TreeBuilder()
        parser.feed(html)
        self.root = parser.root

    def css(self, selector: str):
        return [Node(item) for item in _select(self.root, selector)]


def _select(root: _Element, selector: str):
    selectors = [part.strip() for part in selector.split(',') if part.strip()]
    matched = []
    for item in _walk(root):
        if any(_matches(item, sel) for sel in selectors):
            matched.append(item)
    return matched


def _walk(element: _Element):
    for child in element.children:
        yield child
        yield from _walk(child)


def _matches(element: _Element, selector: str) -> bool:
    selector = selector.strip()
    if not selector:
        return False
    attr_name = attr_value = None
    tag = selector
    cls = None
    if '[' in selector and selector.endswith(']'):
        tag, attr = selector[:-1].split('[', 1)
        if '=' in attr:
            attr_name, attr_value = [part.strip('"\' ') for part in attr.split('=', 1)]
        else:
            attr_name = attr.strip()
    if '.' in tag:
        tag, cls = tag.split('.', 1)
    tag = tag.strip() or None
    if tag and element.tag != tag:
        return False
    if cls:
        classes = element.attrs.get('class', '').split()
        if cls not in classes:
            return False
    if attr_name:
        if attr_name not in element.attrs:
            return False
        if attr_value is not None and element.attrs.get(attr_name) != attr_value:
            return False
    return True
