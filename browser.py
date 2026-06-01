import socket
import ssl
import time
import tkinter
import tkinter.font
from enum import Enum
from pathlib import Path
from urllib.parse import urljoin


class URL:
    def __init__(self, url) -> None:
        self.source = url
        if "://" not in url:
            path = Path(url).expanduser()
            self._init_file(path, root=path.resolve().parent)
            return

        self.scheme, rest = url.split("://", 1)
        assert self.scheme in ["http", "https", "file"]

        if self.scheme == "file":
            self._init_file(rest)
            return

        self._init_http(rest)

    def _init_file(self, path, root=None):
        self.scheme = "file"
        file_path = Path(path).expanduser()
        self.path = str(file_path)
        self.root = Path(root) if root is not None else file_path.resolve().parent

    def _init_http(self, url):
        self.port = 80 if self.scheme == "http" else 443

        if "/" not in url:
            url = url + "/"
        self.host, url = url.split("/", 1)
        self.path = "/" + url

        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

    @classmethod
    def from_file(cls, path, root=None):
        url = cls.__new__(cls)
        url.source = str(path)
        url._init_file(path, root=root)
        return url

    def request(self, payload=None):
        if self.scheme == "file":
            with open(self.path, "r", encoding="utf8") as f:
                body = f.read()
            return {"status": "200"}, body

        s = socket.socket(
            family=socket.AF_INET, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
        print(f"Host: {self.host}, port: {self.port}")
        s.connect((self.host, self.port))

        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)

        method = "POST" if payload else "GET"
        body = f"{method} {self.path} HTTP/1.0\r\n"
        body += f"Host: {self.host}\r\n"
        body += "User-Agent: Browser - version\r\n"
        if payload:
            content_length = len(payload.encode("utf8"))
            body += f"Content-Length: {content_length}\r\n"
        body += "\r\n" + (payload or "")
        s.send(body.encode("utf8"))

        response = s.makefile("r", encoding="utf8", newline="\r\n")

        status_line = response.readline()
        _, status, explanation = status_line.split(" ", 2)
        assert status == "200", "{}: {}".format(status, explanation)

        headers = {}
        headers["status"] = status
        while True:
            line = response.readline()
            if line == "\r\n":
                break
            header, value = line.split(":", 1)
            headers[header.lower()] = value.strip()

        assert "transfer_encoding" not in headers
        assert "content-encoding" not in headers

        body = response.read()
        s.close()

        return headers, body


def find_links(node, lst):
    if not isinstance(node, Element):
        return []
    if (
        node.tag == "link"
        and node.attributes.get("rel", "") == "stylesheet"
        and "href" in node.attributes
    ):
        lst.append(node.attributes["href"])
    for child in node.children:
        find_links(child, lst)
    return lst


def relative_url(url, current) -> str:
    return urljoin(current, url)


class Text:
    def __init__(self, text, parent) -> None:
        self.text = text
        self.children = []
        self.parent = parent
        self.style = {}

    def __repr__(self) -> str:
        return repr(self.text)


class Element:
    def __init__(self, tag, parent, attributes) -> None:
        self.tag = tag
        self.children = []
        self.parent = parent
        self.attributes = attributes

        self.style = {}
        for pair in self.attributes.get("style", "").split(";"):
            if ":" not in pair:
                continue
            prop, val = pair.split(":")
            self.style[prop.strip().lower()] = val.strip()

    def __repr__(self) -> str:
        return "<" + self.tag + ">"


def print_tree(node, indent=0, file=None):
    if file is None:
        file = open("result.txt", "w")
        should_close = True
    else:
        should_close = False

    file.write(" " * indent + str(node) + "\n")
    for child in node.children:
        print_tree(child, indent + 2, file)

    if should_close:
        file.close()


def print_nodes(node, indent=0):
    print(" " * indent, node.__dict__)
    if node.children:
        for child in node.children:
            print_nodes(child, indent + 2)


def print_layout(layout, indent=0):
    if isinstance(layout.node, Element) and layout.node.tag == "input":
        print(" " * indent)
        if isinstance(layout, DocumentLayout):
            print("Document")
        elif isinstance(layout, BlockLayout):
            print("Block")
        elif isinstance(layout, InlineLayout):
            print("Inline")
        print(layout.__dict__)
        print(type(layout.node), layout.node.__dict__)

    if layout.children:
        for child in layout.children:
            print_layout(child, indent + 2)


class HTMLParser:
    SELF_CLOSING_TAG = [
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    ]
    HEAD_TAGS = [
        "base",
        "basefont",
        "bgsound",
        "noscript",
        "link",
        "meta",
        "title",
        "style",
        "script",
    ]

    def __init__(self, body) -> None:
        self.body = body
        self.unfinished = []

    def parse(self):
        text = ""
        in_tag = False
        i = 0
        while i < len(self.body):
            if self.body.startswith("<!--", i):
                if text:
                    self.add_text(text)
                    text = ""
                end = self.body.find("-->", i + 4)
                if end == -1:
                    break
                i = end + 3
                continue

            c = self.body[i]
            if c == "<":
                in_tag = True
                if text:
                    self.add_text(text)
                text = ""
            elif c == ">":
                in_tag = False
                self.add_tag(text)
                text = ""
            else:
                text += c
            i += 1
        if not in_tag and text:
            self.add_text(text)
        return self.finish()

    def get_parent(self):
        return self.unfinished[-1] if self.unfinished else None

    def add_text(self, text):
        if text.isspace():
            return
        self.implicit_tags(None)
        parent = self.get_parent()
        node = Text(text, parent)
        if parent:
            parent.children.append(node)

    def add_tag(self, tagEl):
        tag, attributes = self.get_attributes(tagEl)
        if tag.startswith("!"):
            return
        self.implicit_tags(tag)

        if tag.startswith("/"):
            if len(self.unfinished) == 1:
                return
            node = self.unfinished.pop()
            parent = self.get_parent()
            if parent:
                parent.children.append(node)
        elif tag in self.SELF_CLOSING_TAG:
            parent = self.get_parent()
            node = Element(tag, parent, attributes)
            if parent:
                parent.children.append(node)
        else:  # the normal tag
            parent = self.get_parent()
            node = Element(tag, parent, attributes)
            self.unfinished.append(node)

    def get_attributes(self, text):
        from shlex import split

        parts = split(text)
        tag = parts[0].casefold()
        attributes = {}
        for attrpair in parts[1:]:
            if "=" in attrpair:
                key, value = attrpair.split("=", 1)
                attributes[key.casefold()] = value
            else:
                attributes[attrpair.casefold()] = ""
        return tag, attributes

    def finish(self):
        while len(self.unfinished) > 1:
            node = self.unfinished.pop()
            parent = self.get_parent()
            if parent:
                parent.children.append(node)
        return self.unfinished.pop()

    def implicit_tags(self, tag):
        """Add default tag"""
        while True:
            open_tags = [node.tag for node in self.unfinished]
            if open_tags == [] and tag != "html":
                self.add_tag("html")
            elif open_tags == ["html"] and tag not in ["head", "body", "/html"]:
                if tag in self.HEAD_TAGS:
                    self.add_tag("head")
                else:
                    self.add_tag("body")
            elif (
                open_tags == ["html", "head"] and tag not in ["/head"] + self.HEAD_TAGS
            ):
                self.add_tag("/head")
            else:
                break


class TagSelector:
    def __init__(self, tag) -> None:
        self.tag = tag

    def matches(self, node):
        return isinstance(node, Element) and self.tag == node.tag

    def priority(self):
        return 1


class ClassSelector:
    def __init__(self, cls) -> None:
        self.cls = cls

    def matches(self, node):
        return self.cls in node.attributes.get("class", "").split()

    def priority(self):
        return 16


class IdSelector:
    def __init__(self, tag) -> None:
        self.id = id

    def matches(self, node):
        return self.id == node.attributes.get("id", "")

    def priority(self):
        return 256


INHERITED_PROPERTIES = {
    "font-style": "normal",
    "font-weight": "normal",
    "font-size": "16px",
    "color": "black",
}


def style(node, rules):
    if isinstance(node, Text):
        node.style = dict(node.parent.style)
        return

    for selector, pairs in rules:
        if selector.matches(node):
            for property in pairs:
                if property not in node.style:
                    node.style[property] = pairs[property]
    for property, default in INHERITED_PROPERTIES.items():
        if property not in node.style:
            if node.parent:
                node.style[property] = node.parent.style[property]
            else:
                node.style[property] = default

    for child in node.children:
        style(child, rules)


class CSSParser:
    def __init__(self, s) -> None:
        self.s = s

    def comment(self, i: int):
        assert self.s[i : i + 2] == "/*"
        end = self.s.find("*/", i + 2)
        if end == -1:
            return None, len(self.s)
        return None, end + 2

    def whitespace(self, i: int):
        while i < len(self.s):
            if self.s[i].isspace():
                i += 1
            elif self.s[i : i + 2] == "/*":
                _, i = self.comment(i)
            else:
                break
        return None, i

    def literal(self, i, literal):
        assert self.s[i : i + len(literal)] == literal, (
            f"i: {i}, literal: {self.s[i : i + len(literal)]} == {literal}"
        )
        return None, i + len(literal)

    def word(self, i):
        start = i
        while i < len(self.s) and (self.s[i].isalnum() or self.s[i] in "#-.%"):
            i += 1
        assert i > start, f"i: {i}, word: {self.s[i]}"
        return self.s[start:i], i

    def pair(self, i):
        prop, i = self.word(i)
        _, i = self.whitespace(i)
        _, i = self.literal(i, ":")
        _, i = self.whitespace(i)
        val, i = self.word(i)
        return (prop.lower(), val), i

    def ignore_until(self, i, chars):
        while i < len(self.s) and self.s[i] not in chars:
            i += 1
        return None, i

    def body(self, i):
        pairs = {}
        _, i = self.literal(i, "{")
        _, i = self.whitespace(i)
        while i < len(self.s) and self.s[i] != "}":
            try:
                (prop, val), i = self.pair(i)
                pairs[prop] = val
                _, i = self.whitespace(i)
                _, i = self.literal(i, ";")
            except AssertionError:
                _, i = self.ignore_until(i, [";", "}"])
                if i < len(self.s) and self.s[i] == ";":
                    _, i = self.literal(i, ";")
            _, i = self.whitespace(i)

        _, i = self.literal(i, "}")
        return pairs, i

    def selector(self, i):
        if self.s[i] == "#":
            _, i = self.literal(i, "#")
            name, i = self.word(i)
            return IdSelector(name), i
        elif self.s[i] == ".":
            _, i = self.literal(i, ".")
            name, i = self.word(i)
            return ClassSelector(name), i
        else:
            name, i = self.word(i)
            return TagSelector(name.lower()), i

    def rule(self, i):
        selector, i = self.selector(i)
        _, i = self.whitespace(i)
        body, i = self.body(i)
        return (selector, body), i

    def file(self, i):
        rules = []
        _, i = self.whitespace(i)
        while i < len(self.s):
            try:
                rule, i = self.rule(i)
                rules.append(rule)
            except AssertionError:
                _, i = self.ignore_until(i, ["}"])
                _, i = self.literal(i, "}")

            _, i = self.whitespace(i)
        return rules, i

    def parse(self):
        rules, _ = self.file(0)
        return rules


WIDTH, HEIGHT = 800, 600
H_STEP, V_STEP = 13, 18
SCROLL_STEP = 100


class LineLayout:
    def __init__(self, node, parent) -> None:
        self.node = node
        self.parent = parent
        self.children = []
        self.x = 0
        self.y = 0
        self.w = 0
        self.h = 0
        self.cx = 0

    def append(self, child):
        self.children.append(child)
        child.parent = self
        self.cx += child.w + child.font.measure(" ")

    def layout(self):
        self.w = self.parent.w
        if not self.children:
            self.h = 0
            return
        metrics = [child.font.metrics() for child in self.children]
        max_ascent = max([metric["ascent"] for metric in metrics])
        baseline = self.y + 1.2 * max_ascent

        dx = 0
        for child, metric in zip(self.children, metrics):
            child.x = self.x + dx
            child.y = baseline - metric["ascent"]
            dx += child.w + child.font.measure(" ")
        max_descent = max([metric["descent"] for metric in metrics])
        self.h = 1.2 * (max_descent + max_ascent)

    def get_draw(self):
        display_list = []
        for child in self.children:
            display_list.extend(child.get_draw())
        return tuple(display_list)


class TextLayout:
    def __init__(self, node, word) -> None:
        self.node = node
        self.word = word
        self.children = []
        self.x = -1
        self.y = -1
        self.w = -1
        self.h = -1

    def layout(self):
        weight = self.node.style["font-weight"]
        style = self.node.style["font-style"]
        if style == "normal":
            style = "roman"
        size = int(px(self.node.style["font-size"]) * 0.75)
        self.font = tkinter.font.Font(size=size, weight=weight, slant=style)

        self.w = self.font.measure(self.word)
        self.h = self.font.metrics("linespace")

    def get_draw(self):
        color = self.node.style["color"]
        return [DrawText(self.x, self.y, self.word, self.font, color)]


class InputLayout:
    def __init__(self, node) -> None:
        self.node = node
        self.children = []
        self.x = -1
        self.y = -1
        self.w = 200
        self.h = 20

    def is_valid_coordinate(self):
        return self.x != -1 and self.y != -1 and self.w != -1 and self.h != -1

    def layout(self):
        weight = self.node.style["font-weight"]
        style = self.node.style["font-style"]
        if style == "normal":
            style = "roman"
        size = int(px(self.node.style["font-size"]) * 0.75)
        self.font = tkinter.font.Font(size=size, weight=weight, slant=style)

    def get_draw(self):
        if not self.is_valid_coordinate():
            return []
        display_list = []
        x1, x2 = self.x, self.x + self.w
        y1, y2 = self.y, self.y + self.h
        bgcolor = "light gray" if self.node.tag == "input" else "yellow"
        display_list.append(DrawRect(x1, y1, x2, y2, bgcolor))

        if self.node.tag == "input":
            text = self.node.attributes.get("value", "")
        else:
            text = self.node.children[0].text
        color = self.node.style["color"]
        display_list.append(DrawText(x1, y1, text, self.font, color))
        return tuple(display_list)


class InlineLayout:
    def __init__(self, node, parent) -> None:
        self.node = node
        self.parent = parent
        self.children = [LineLayout(self.node, self)]

        self.x = -1
        self.y = -1
        self.w = -1
        self.h = -1
        self.line_height = 0

    def layout(self):
        self.mt = self.bt = self.pt = 0
        self.mr = self.br = self.pr = 0
        self.mb = self.bb = self.pb = 0
        self.ml = self.bl = self.pl = 0
        self.w = (
            self.parent.w
            - self.parent.pl
            - self.parent.pr
            - self.parent.bl
            - self.parent.br
        )

        self.cy = self.y
        self.recurse(self.node)
        self.flush()
        self.children.pop()

        self.h = self.cy - self.y

    def recurse(self, node):
        if isinstance(node, Text):
            self.text(node)
        else:
            if node.tag == "br":
                self.break_line()
            if node.tag == "input":
                self.input(node)
            for child in node.children:
                self.recurse(child)

    def text(self, node):
        for word in node.text.split():
            child = TextLayout(node, word)
            child.layout()
            if self.children[-1].cx + child.w > self.w:
                self.flush()
            self.children[-1].append(child)

    def input(self, node):
        child = InputLayout(node)
        child.layout()
        if self.children[-1].cx + child.w > self.w:
            self.flush()
        self.children[-1].append(child)

    def flush(self):
        child = self.children[-1]
        child.x = self.x
        child.y = self.cy
        child.layout()
        self.cy += child.h
        self.line_height = child.h
        self.children.append(LineLayout(self.node, self))

    def break_line(self):
        if self.children[-1].children:
            self.flush()
        else:
            self.cy += self.line_height
        self.children.append(LineLayout(self.node, self))

    def get_draw(self):
        display_list = []
        for child in self.children:
            display_list.extend(child.get_draw())
        return tuple(display_list)


def px(s):
    if s.endswith("px"):
        return int(s[:-2])
    else:
        return 0


def is_inline_node(node):
    if isinstance(node, Text):
        return not node.text.isspace()
    return node.style.get("display", "inline") != "block"


class AnonymousBlock:
    def __init__(self, parent, children) -> None:
        self.tag = "anonymous"
        self.parent = parent
        self.children = children
        self.attributes = {}
        self.style = dict(parent.style)


class BlockLayout:
    def __init__(self, node, parent) -> None:
        self.node = node
        self.parent = parent
        self.children = []

        self.x = -1
        self.y = -1
        self.w = -1
        self.h = -1

    def has_block_children(self):
        for child in self.node.children:
            if is_inline_node(child):
                return False
        return True

    def add_inline_child(self, inline_nodes):
        if inline_nodes:
            anonymous = AnonymousBlock(self.node, inline_nodes)
            self.children.append(InlineLayout(anonymous, self))

    def build_children(self):
        inline_nodes = []
        for child in self.node.children:
            if is_inline_node(child):
                inline_nodes.append(child)
                continue

            self.add_inline_child(inline_nodes)
            inline_nodes = []
            self.children.append(BlockLayout(child, self))

        self.add_inline_child(inline_nodes)

    def layout(self):
        self.children = []
        if self.has_block_children():
            for child in self.node.children:
                if isinstance(child, Text):
                    continue
                self.children.append(BlockLayout(child, self))
        else:
            self.build_children()

        self.mt = px(self.node.style.get("margin-top", "0px"))
        self.bt = px(self.node.style.get("border-top-width", "0px"))
        self.pt = px(self.node.style.get("padding-top", "0px"))
        self.mr = px(self.node.style.get("margin-right", "0px"))
        self.br = px(self.node.style.get("border-right-width", "0px"))
        self.pr = px(self.node.style.get("padding-right", "0px"))
        self.mb = px(self.node.style.get("margin-bottom", "0px"))
        self.bb = px(self.node.style.get("border-bottom-width", "0px"))
        self.pb = px(self.node.style.get("padding-bottom", "0px"))
        self.ml = px(self.node.style.get("margin-left", "0px"))
        self.bl = px(self.node.style.get("border-left-width", "0px"))
        self.pl = px(self.node.style.get("padding-left", "0px"))

        self.w = (
            self.parent.w
            - self.parent.pl
            - self.parent.pr
            - self.parent.bl
            - self.parent.br
            - self.ml
            - self.mr
        )

        self.y += self.mt
        self.x += self.ml

        y = self.y
        for child in self.children:
            child.x = self.x + self.pl + self.bl
            child.y = y
            child.layout()
            y += child.mt + child.h + child.mb

        self.h = y - self.y

    def get_draw(self):
        display_list = []
        bgcolor = self.node.style.get("background-color", "transparent")
        if bgcolor != "transparent":
            x2, y2 = self.x + self.w, self.y + self.h
            rect = DrawRect(self.x, self.y, x2, y2, bgcolor)
            display_list.append(rect)
        for child in self.children:
            display_list.extend(child.get_draw())
        return tuple(display_list)


class DocumentLayout:
    def __init__(self, node) -> None:
        self.node = node
        self.parent = None
        self.children = []

        self.x = -1
        self.y = -1
        self.w = -1
        self.h = -1

    def layout(self):
        child = BlockLayout(self.node, self)
        self.children.append(child)

        self.w = WIDTH
        self.mt = self.bt = self.pt = 0
        self.mr = self.br = self.pr = 0
        self.mb = self.bb = self.pb = 0
        self.ml = self.bl = self.pl = 0

        child.x = self.x = 0
        child.y = self.y = 0
        child.layout()
        self.h = child.h

    def get_draw(self):
        display_list = []
        display_list.extend(self.children[0].get_draw())
        return tuple(display_list)


class DrawText:
    def __init__(self, x1, y1, text, font, color) -> None:
        self.x1 = x1
        self.y1 = y1
        self.text = text
        self.font = font
        self.color = color

        self.y2 = y1 + font.metrics("linespace")

    def draw(self, canvas, scroll):
        canvas.create_text(
            self.x1,
            self.y1 - scroll,
            text=self.text,
            font=self.font,
            fill=self.color,
            anchor="nw",
        )


class DrawRect:
    def __init__(self, x1, y1, x2, y2, color) -> None:
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.color = color

    def draw(self, canvas, scroll):
        canvas.create_rectangle(
            self.x1,
            self.y1 - scroll,
            self.x2,
            self.y2 - scroll,
            width=0,
            fill=self.color,
        )


def find_layout(x, y, tree):
    if not (tree.x <= x < tree.x + tree.w and tree.y <= y < tree.y + tree.h):
        return None

    for child in reversed(tree.children):
        result = find_layout(x, y, child)
        if result:
            return result
    return tree


def is_link(node):
    return isinstance(node, Element) and node.tag == "a" and "href" in node.attributes


class Browser:
    class FOCUS_EL(Enum):
        ADDRESS_BAR = "address bar"
        INPUT = "input"

    def __init__(self):
        self.window = tkinter.Tk()
        self.window.title("Web Browser")
        self.canvas = tkinter.Canvas(
            self.window, width=WIDTH, height=HEIGHT, bg="white"
        )
        self.canvas.pack()
        self.url = ""

        self.history = []
        self.focus = None
        self.focus_el = None
        self.address_bar = ""
        self.scroll = 0

        self.window.bind("<Down>", self.scrolldown)
        self.window.bind("<Up>", self.scrollup)
        self.window.bind("<Key>", self.key_press)
        self.window.bind("<Button-1>", self.handle_click)
        self.window.bind("<Return>", self.press_enter)
        self.display_list = []

    def handle_click(self, e):
        self.focus = None
        if e.y < 60:  # On the address bar
            if 10 <= e.x < 35 and 10 <= e.y < 50:
                self.go_back()
            elif 50 <= e.x < 790 and 10 <= e.y < 50:
                self.focus = self.FOCUS_EL.ADDRESS_BAR
                self.address_bar = ""
                self.render()
        else:
            x, y = e.x, e.y + self.scroll - 60
            obj = find_layout(x, y, self.document)
            if not obj:
                return
            node = obj.node
            while node:
                if isinstance(node, Text):
                    pass
                elif is_link(node):
                    url = relative_url(node.attributes["href"], self.url)
                    return self.load(url)
                elif node.tag == "input":
                    node.attributes["value"] = ""
                    self.focus = self.FOCUS_EL.INPUT
                    self.focus_el = obj
                    return self.layout(self.document.node)
                elif node.tag == "button":
                    return self.submit_form(node)
                node = node.parent

    def is_printable_key(self, char):
        return len(char) > 0 and 0x20 <= ord(char) < 0x7F

    def delete_character(self):
        if not self.focus_el:
            return

        if self.focus == self.FOCUS_EL.ADDRESS_BAR:
            self.address_bar = self.address_bar[:-1]
        elif self.focus == self.FOCUS_EL.INPUT:
            value = self.focus_el.node.attributes.get("value", "")
            self.focus_el.node.attributes["value"] = value[:-1]

    def append_character(self, char):
        if self.focus == self.FOCUS_EL.ADDRESS_BAR:
            self.address_bar += char
        elif self.FOCUS_EL.INPUT:
            if not self.focus_el:
                return
            self.focus_el.node.attributes["value"] += char

    def key_press(self, e):
        if not self.focus:
            return

        if e.keysym == "BackSpace":
            self.delete_character()
        else:
            if not self.is_printable_key(e.char):
                return
            self.append_character(e.char)

        self.layout(self.document.node)

    def press_enter(self, e):
        if self.focus == self.FOCUS_EL.ADDRESS_BAR:
            self.focus = None
            self.load(self.address_bar)

    def find_inputs(self, node, out=None):
        if out is None:
            out = []
        if not isinstance(node, Element):
            return
        if node.tag == "input" and "name" in node.attributes:
            out.append(node)
        for child in node.children:
            self.find_inputs(child, out)
        return out

    def submit_form(self, node):
        while node and node.tag != "form":
            node = node.parent
        if not node:
            return
        inputs = self.find_inputs(node) or []
        body = ""
        for input in inputs:
            name = input.attributes["name"]
            value = input.attributes.get("value", "")
            body += "&" + name + "=" + value.replace(" ", "%20")
        body = body[1:]
        url = relative_url(node.attributes["action"], self.url)
        self.load(url, body)

    def go_back(self):
        if len(self.history) > 1:
            self.history.pop()
            back = self.history.pop()
            self.load(back)

    def load(self, url: str, payload=None):
        start_time = time.time()

        # Process the property
        self.address_bar = url
        self.url = url
        self.history.append(url)

        url_obj = URL(url)
        _, body = url_obj.request(payload)
        nodes = HTMLParser(body).parse()

        rules = []

        for link in find_links(nodes, []):
            _, body = URL(relative_url(link, url)).request()
            rules.extend(CSSParser(body).parse())

        rules.sort(key=lambda x: x[0].priority())
        rules.reverse()
        style(nodes, rules)

        self.layout(nodes)

        draw_time = time.time()
        print(f"Total time: {draw_time - start_time:.3f}s")

    def layout(self, nodes):
        self.document = DocumentLayout(nodes)
        self.document.layout()
        # print_layout(self.document)
        self.display_list = self.document.get_draw()
        self.render()
        self.max_y = self.document.h - HEIGHT

    def render(self):
        self.canvas.delete("all")
        for cmd in self.display_list:
            if cmd.y1 > self.scroll + HEIGHT - 60:
                continue
            if cmd.y2 < self.scroll:
                continue
            cmd.draw(self.canvas, self.scroll - 60)
        self.canvas.create_rectangle(0, 0, 800, 60, width=0, fill="light gray")
        self.canvas.create_rectangle(50, 10, 790, 50)
        font = tkinter.font.Font(family="Courier", size=30)
        self.canvas.create_text(55, 15, anchor="nw", text=self.address_bar, font=font)
        self.canvas.create_rectangle(10, 10, 35, 50)
        self.canvas.create_polygon(15, 30, 30, 15, 30, 45, fill="black")
        if self.focus == self.FOCUS_EL.ADDRESS_BAR:
            w = font.measure(self.address_bar)
            self.canvas.create_line(55 + w, 15, 55 + w, 45)
        elif self.focus == self.FOCUS_EL.INPUT and self.focus_el:
            text = self.focus_el.node.attributes.get("value", "")
            x = self.focus_el.x + self.focus_el.font.measure(text)
            y = self.focus_el.y - self.scroll + 60
            self.canvas.create_line(x, y, x, y + self.focus_el.h)

    def scrolldown(self, e):
        self.scroll = min(self.scroll + SCROLL_STEP, self.max_y)
        self.render()

    def scrollup(self, e):
        self.scroll = max(self.scroll - SCROLL_STEP, 0)
        self.render()


if __name__ == "__main__":
    import sys

    browser = Browser()
    browser.load(sys.argv[1])
    tkinter.mainloop()
