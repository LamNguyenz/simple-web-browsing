import socket
import ssl
import time
import tkinter
import tkinter.font
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

    def resolve(self, ref):
        if "://" in ref:
            return URL(ref)

        if self.scheme == "file":
            current = Path(self.path).expanduser()
            if ref.startswith("/"):
                path = (self.root / ref.lstrip("/")).resolve()
            else:
                path = (current.parent / ref).resolve()
            return URL.from_file(path, root=self.root)

        base = f"{self.scheme}://{self.host}"
        if self.port != (80 if self.scheme == "http" else 443):
            base += f":{self.port}"
        base += self.path
        return URL(urljoin(base, ref))

    @classmethod
    def from_file(cls, path, root=None):
        url = cls.__new__(cls)
        url.source = str(path)
        url._init_file(path, root=root)
        return url

    def request(self):
        if self.scheme == "file":
            with open(self.path, "r", encoding="utf8") as f:
                body = f.read()
            return {"status": "200"}, body

        s = socket.socket(
            family=socket.AF_INET, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
        )
        s.connect((self.host, self.port))

        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)

        request = f"GET {self.path} HTTP/1.0\r\n"
        request += f"Host: {self.host}\r\n"
        request += "User-Agent: Browser - version\r\n"
        request += "\r\n"
        s.send(request.encode("utf8"))

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


def print_nodes(node, indent=0, file=None):
    if isinstance(node, DocumentLayout):
        print("Document")
    elif isinstance(node, BlockLayout):
        print("Block")
    elif isinstance(node, InlineLayout):
        print("Inline")
    print(node.__dict__)
    if node.children:
        for child in node.children:
            print_nodes(child, indent + 2, file)


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
        for c in self.body:
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

    def whitespace(self, i: int):
        while i < len(self.s) and self.s[i].isspace():
            i += 1
        return None, i

    def literal(self, i, literal):
        assert self.s[i : i + len(literal)] == literal, (
            f"i: {i}, literal: {self.s[i : i + len(literal)]} == {literal}"
        )
        return None, i + len(literal)

    def word(self, i):
        start = i
        while i < len(self.s) and self.s[i].isalnum() or self.s[i] in "#-.%":
            i += 1
        assert i > start
        return self.s[start:i], i

    def pair(self, i):
        prop, i = self.word(i)
        _, i = self.whitespace(i)
        _, i = self.literal(i, ":")
        _, i = self.whitespace(i)
        val, i = self.word(i)
        return (prop.lower(), val), i

    def ignore_until(self, i, chars):
        while i < len(self.s) and self.s[i] in chars:
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

BLOCK_ELEMENTS = [
    "html",
    "body",
    "article",
    "section",
    "nav",
    "aside",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hgroup",
    "header",
    "footer",
    "address",
    "p",
    "hr",
    "ol",
    "ul",
    "menu",
    "li",
    "dl",
    "dt",
    "dd",
    "figure",
    "figcaption",
    "main",
    "div",
    "table",
    "form",
    "fieldset",
    "legend",
    "details",
    "summary",
]


def layout_mode(node):
    if isinstance(node, Text):
        return "inline"
    elif node.tag in BLOCK_ELEMENTS:
        return "block"
    elif node.children:
        for child in node.children:
            if isinstance(child, Text):
                continue
            if child.tag in BLOCK_ELEMENTS:
                return "block"
        return "inline"
    else:
        return "block"


class BlockLayout:
    def __init__(self, node, parent, previous) -> None:
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []

    def layout(self):
        previous = None
        for child in self.node.children:
            if layout_mode(child) == "inline":
                next = InlineLayout(child, self, previous)
            else:
                next = BlockLayout(child, self, previous)
            self.children.append(next)
            previous = next

        self.width = self.parent.width
        self.x = self.parent.x

        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y

        for child in self.children:
            child.layout()

        self.height = sum([child.height for child in self.children])

    def getDraw(self):
        display_list = []
        bgcolor = self.node.style.get("background-color", "transparent")
        if bgcolor != "transparent":
            x2, y2 = self.x + self.width, self.y + self.height
            rect = DrawRect(self.x, self.y, x2, y2, bgcolor)
            display_list.append(rect)
        for child in self.children:
            display_list.extend(child.getDraw())
        return tuple(display_list)


class InlineLayout:
    def __init__(self, node, parent, previous) -> None:
        self.node = node
        self.parent = parent
        self.previous = previous
        self.children = []

    def layout(self):
        self.width = self.parent.width
        self.x = self.parent.x

        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y

        self.display_list = []
        self.weight = "normal"
        self.style = "roman"
        self.size = 16

        self.cursor_x = self.x
        self.cursor_y = self.y
        self.line = []
        self.recurse(self.node)
        self.flush()

        self.height = self.cursor_y - self.y

    def open_tag(self, tag):
        if tag == "i":
            self.style = "italic"
        elif tag == "b":
            self.weight = "bold"
        elif tag == "small":
            self.size -= 2
        elif tag == "big":
            self.size += 4
        elif tag == "br":
            self.flush()

    def close_tag(self, tag):
        if tag == "i":
            self.style = "roman"
        elif tag == "b":
            self.weight = "normal"
        elif tag == "small":
            self.size += 2
        elif tag == "big":
            self.size -= 4
        elif tag == "p":
            self.flush()
            self.cursor_y += V_STEP

    def text(self, text, color):
        font = tkinter.font.Font(size=self.size, weight=self.weight, slant=self.style)
        for word in text.split():
            w = font.measure(word)
            if self.cursor_x + w > WIDTH - H_STEP:
                self.flush()
                self.cursor_y += font.metrics("linespace") * 1.25
                self.cursor_x = H_STEP
            self.line.append((self.cursor_x, word, font, color))
            self.cursor_x += w + font.measure(" ")

    def recurse(self, tree):
        if isinstance(tree, Text):
            self.text(tree.text, tree.style["color"])
        else:
            self.open_tag(tree.tag)
            for child in tree.children:
                self.recurse(child)
            self.close_tag(tree.tag)

    def flush(self):
        if not self.line:
            return
        metrics = [font.metrics() for _, _, font, _ in self.line]
        max_ascent = max([metric["ascent"] for metric in metrics])
        baseline = self.cursor_y + 1.2 * max_ascent
        for x, word, font, color in self.line:
            y = baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font, color))
        self.cursor_x = self.x
        self.line = []
        max_descent = max([metric["descent"] for metric in metrics])
        self.cursor_y = baseline + 1.2 * max_descent

    def getDraw(self):
        return tuple(
            DrawText(x, y, word, font, color)
            for x, y, word, font, color in self.display_list
        )


class DocumentLayout:
    def __init__(self, node) -> None:
        self.node = node
        self.parent = None
        self.previous = None
        self.children = []

        self.width = WIDTH - 2 * H_STEP
        self.x = H_STEP
        self.y = V_STEP

    def layout(self):
        child = BlockLayout(self.node, self, None)
        self.children.append(child)

        child.layout()
        self.height = child.height + 2 * V_STEP

    def getDraw(self):
        display_list = []
        for child in self.children:
            display_list.extend(child.getDraw())
        return tuple(display_list)


class DrawText:
    def __init__(self, x1, y1, text, font, color) -> None:
        self.left = x1
        self.top = y1
        self.text = text
        self.font = font
        self.color = color
        self.bottom = y1 + font.metrics("linespace")

    def execute(self, canvas, scroll):
        canvas.create_text(
            self.left,
            self.top - scroll,
            text=self.text,
            font=self.font,
            fill=self.color,
            anchor="nw",
        )


class DrawRect:
    def __init__(self, x1, y1, x2, y2, color) -> None:
        self.top = y1
        self.left = x1
        self.bottom = y2
        self.right = x2
        self.color = color

    def execute(self, canvas, scroll):
        canvas.create_rectangle(
            self.left,
            self.top - scroll,
            self.right,
            self.bottom - scroll,
            width=0,
            fill=self.color,
        )


class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.window.title("Web Browser")
        self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT)
        self.canvas.pack()

        self.scroll = 0
        self.window.bind("<Down>", self.scrolldown)
        self.display_list = []

    def load(self, url):
        start_time = time.time()
        if not isinstance(url, URL):
            url = URL(url)

        _, body = url.request()
        nodes = HTMLParser(body).parse()

        rules = []

        for link in find_links(nodes, []):
            _, body = url.resolve(link).request()
            rules.extend(CSSParser(body).parse())

        style(nodes, rules)

        self.document = DocumentLayout(nodes)
        self.document.layout()
        self.display_list = self.document.getDraw()
        self.render()

        draw_time = time.time()
        print(f"Total time: {draw_time - start_time:.3f}s")

    def render(self):
        self.canvas.delete("all")
        for cmd in self.display_list:
            if cmd.top > self.scroll + HEIGHT:
                continue
            if cmd.bottom < self.scroll:
                continue
            cmd.execute(self.canvas, self.scroll)

    def scrolldown(self, e):
        max_y = self.document.height - HEIGHT
        self.scroll = min(self.scroll + SCROLL_STEP, max_y)
        self.render()


if __name__ == "__main__":
    import sys

    browser = Browser()
    browser.load(sys.argv[1])
    # tkinter.mainloop()
