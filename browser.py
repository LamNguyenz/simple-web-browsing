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


def lex(body):
    text = ""
    in_tag = False
    for c in body:
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            text += c
    return text


WIDTH, HEIGHT = 800, 600
H_STEP, V_STEP = 13, 18
SCROLL_STEP = 100


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
        text = lex(body)
        self.display_list = self.layout(text)
        self.draw()

    def layout(self, text):
        display_list = []
        font = tkinter.font.Font(size=16)
        cursor_x, cursor_y = H_STEP, V_STEP
        for word in text.split():
            print((word, cursor_x))
            w = font.measure(word)
            if cursor_x + w > WIDTH - H_STEP:
                cursor_y += font.metrics("linespace") * 1.25
                cursor_x = H_STEP
            display_list.append((cursor_x, cursor_y, word, font))
            cursor_x += w + font.measure(" ")
        return display_list

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
