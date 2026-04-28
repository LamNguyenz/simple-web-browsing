import socket
import ssl
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
    def __init__(self, text):
        self.text = text


class Tag:
    def __init__(self, tag) -> None:
        self.tag = tag


def lex(body):
    out = []
    buffer = ""
    in_tag = False
    for c in body:
        if c == "<":
            in_tag = True
            if buffer:
                out.append(Text(buffer))
                buffer = ""
        elif c == ">":
            in_tag = False
            out.append(Tag(buffer))
            buffer = ""
        else:
            buffer += c
    if not in_tag and buffer:
        out.append(Text(buffer))
    return out


WIDTH, HEIGHT = 800, 600
H_STEP, V_STEP = 13, 18
SCROLL_STEP = 100


class Layout:
    def __init__(self, tokens) -> None:
        self.tokens = tokens
        self.display_list = []
        self.cursor_x = H_STEP
        self.cursor_y = V_STEP
        self.weight = "normal"
        self.style = "roman"
        self.size = 16

        self.line = []
        for tok in tokens:
            self.token(tok)
        self.flush()

    def token(self, tok):
        if isinstance(tok, Text):
            self.text(tok.text)
        elif tok.tag == "i":
            self.style = "italic"
        elif tok.tag == "/i":
            self.style = "roman"
        elif tok.tag == "b":
            self.weight = "bold"
        elif tok.tag == "/b":
            self.weight = "normal"
        elif tok.tag == "small":
            self.size -= 2
        elif tok.tag == "/small":
            self.size += 2
        elif tok.tag == "big":
            self.size += 4
        elif tok.tag == "/big":
            self.size -= 4
        elif tok.tag == "br":
            self.flush()
        elif tok.tag == "/p":
            self.flush()
            self.cursor_y += V_STEP

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

    def load(self, url: URL):
        _, body = url.request()
        tokens = lex(body)
        self.display_list = Layout(tokens).display_list
        self.draw()

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
    browser.load(URL(sys.argv[1]))
    tkinter.mainloop()
