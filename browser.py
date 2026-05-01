import socket
import ssl
import time
import tkinter
import tkinter.font


class URL:
    def __init__(self, url) -> None:
        self.scheme, url = url.split("://", 1)
        assert self.scheme in ["http", "https"]

        self.port = 80 if self.scheme == "http" else 443

        if "/" not in url:
            url = url + "/"
        self.host, url = url.split("/", 1)
        self.path = "/" + url

        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

    def request(self):
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
        version, status, explanation = status_line.split(" ", 2)
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


class Text:
    def __init__(self, text, parent) -> None:
        self.text = text
        self.children = []
        self.parent = parent

    def __repr__(self) -> str:
        return repr(self.text)


class Element:
    def __init__(self, tag, parent, attributes) -> None:
        self.tag = tag
        self.children = []
        self.parent = parent
        self.attributes = attributes

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
            parent.children.append(node)
        else:  # the normal tag
            parent = self.get_parent()
            node = Element(tag, parent, attributes)
            self.unfinished.append(node)

    def get_attributes(self, text):
        parts = text.split()
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


WIDTH, HEIGHT = 800, 600
H_STEP, V_STEP = 13, 18
SCROLL_STEP = 100


class Layout:
    def __init__(self, tree) -> None:
        self.display_list = []
        self.cursor_x = H_STEP
        self.cursor_y = V_STEP
        self.weight = "normal"
        self.style = "roman"
        self.size = 16

        self.line = []
        self.recurse(tree)

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

    def recurse(self, tree):
        if isinstance(tree, Text):
            for word in tree.text.split():
                self.text(word)
        else:
            self.open_tag(tree.tag)
            for child in tree.children:
                self.recurse(child)
            self.close_tag(tree.tag)

    def text(self, text):
        font = tkinter.font.Font(size=self.size, weight=self.weight, slant=self.style)
        for word in text.split():
            w = font.measure(word)
            if self.cursor_x + w > WIDTH - H_STEP:
                self.flush()
                self.cursor_y += font.metrics("linespace") * 1.25
                self.cursor_x = H_STEP
            self.line.append((self.cursor_x, word, font))
            self.cursor_x += w + font.measure(" ")

    def flush(self):
        if not self.line:
            return
        metrics = [font.metrics() for x, word, font in self.line]
        max_ascent = max([metric["ascent"] for metric in metrics])
        baseline = self.cursor_y + 1.25 * max_ascent
        for x, word, font in self.line:
            y = baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font))
        self.cursor_x = H_STEP
        self.line = []
        max_descent = max([metric["descent"] for metric in metrics])
        self.cursor_y = baseline + 1.2 * max_descent


class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.window.title("Web Browser")
        self.canvas = tkinter.Canvas(self.window, width=WIDTH, height=HEIGHT)
        self.canvas.pack()

        self.scroll = 0
        self.window.bind("<Down>", self.scrolldown)

    def load(self, url):
        start_time = time.time()
        if not isinstance(url, URL):
            url = URL(url)
        _, body = url.request()
        self.nodes = HTMLParser(body).parse()
        self.display_list = Layout(self.nodes).display_list
        self.draw()
        draw_time = time.time()

        print(f"Total time: {draw_time - start_time:.3f}s")

    def draw(self):
        self.canvas.delete("all")
        for x, y, c, font in self.display_list:
            if y > self.scroll + HEIGHT or y + V_STEP < self.scroll:
                continue
            self.canvas.create_text(x, y - self.scroll, text=c, font=font, anchor="nw")

    def scrolldown(self, e):
        self.scroll += SCROLL_STEP
        self.draw()


if __name__ == "__main__":
    import sys

    browser = Browser()
    browser.load(sys.argv[1])
    tkinter.mainloop()
    # headers, body = URL(sys.argv[1]).request()
    # nodes = HTMLParser(body).parse()
    # print_tree(nodes)
