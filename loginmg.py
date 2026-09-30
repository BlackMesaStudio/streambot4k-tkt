"""TikTok RTMP grabber.

Talks to the StreamLabs "slobs" API and hands you the RTMP url plus the stream
key, ready to paste into OBS.

    Copyright (C) 2026  Black Mesa Studio

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

    Attribution
    -----------
    The StreamLabs API contract used here (endpoint paths, request field names,
    the required Sec-Fetch-* headers and the desktop user agent) was learned from
    the open-source project Loukious/StreamlabsTikTokStreamKeyGenerator
    (https://github.com/Loukious/StreamlabsTikTokStreamKeyGenerator), which is
    licensed under the GNU General Public License v3.0.  No code was copied from
    it; this is an independent reimplementation.  Thanks to Loukious for the
    original.
"""

import base64
import hashlib
import json
import os
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

# Beside the .py when run from source, beside the .exe when frozen.  In a
# PyInstaller onefile bundle __file__ points at the temporary extraction
# folder, which is wiped on exit, so the saved token would not survive a restart.
HERE = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
API = "https://streamlabs.com/api/v5/slobs/tiktok"
AUTH = "https://streamlabs.com/api/v5/slobs/auth/data"
SIGNIN = "https://streamlabs.com/slobs/login"
NOTEBOOK = HERE / "notebook.json"

DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) StreamlabsDesktop/1.17.0 Chrome/122.0.6261.156 "
    "Electron/29.3.1 Safari/537.36"
)
BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) StreamlabsDesktop/1.20.4 Chrome/122.0.6261.156 "
    "Electron/29.3.1 Safari/537.36"
)


class Nope(RuntimeError):
    """Anything worth reading out loud."""


# ------------------------------------------------------------------ talking

def identify(token=""):

    head = {"user-agent": DESKTOP}
    if token:
        head["authorization"] = "Bearer " + token
    return head


def ask(token, path, verb="GET", topic="Peticion", **extra):
    """One slobs call; returns the decoded body or blows up with a reason."""
    try:
        got = requests.request(verb, API + path, headers=identify(token), timeout=20, **extra)
    except requests.RequestException as trouble:
        raise Nope(f"{topic}: {trouble}") from trouble
    if got.status_code in (401, 403):
        raise Nope(f"{topic}: StreamLabs rechaz\u00f3 ese token.")
    if got.status_code >= 400:
        raise Nope(f"{topic}: HTTP {got.status_code}.")
    try:
        return got.json()
    except ValueError as trouble:
        raise Nope(f"{topic}: la respuesta no era JSON.") from trouble


def describe(token):
    """(handle, approval status, allowed to broadcast)."""
    body = ask(token, "/info", topic="Cuenta")
    return (
        (body.get("user") or {}).get("username") or "unknown",
        (body.get("application_status") or {}).get("status") or "unknown",
        bool(body.get("can_be_live")),
    )


def raise_stream(token):
    """Open a broadcast; returns (rtmp url, stream key)."""
    body = ask(
        token, "/stream/start", "POST", "Start",
        files=[
            ("title", (None, "live")),
            ("device_platform", (None, "win32")),
            ("category", (None, "")),
            ("audience_type", (None, "0")),
        ],
    )
    try:
        return body["rtmp"], body["key"]
    except KeyError as gap:
        raise Nope(f"Obtener claves: a la respuesta le falta {gap}.") from gap


# ------------------------------------------------------------------- tokens

def redeem(code, seed):
    """Swap the redirect code for a StreamLabs token."""
    try:
        got = requests.get(
            AUTH,
            params={"code_verifier": seed, "code": code},
            headers={
                "User-Agent": BROWSER,
                "Accept": "*/*",
                "Accept-Language": "en-US",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
            },
            timeout=30,
        )
    except requests.RequestException as trouble:
        raise Nope(f"Inicio de sesi\u00f3n: {trouble}") from trouble

    if got.status_code != 200:
        raise Nope(f"Inicio de sesi\u00f3n: HTTP {got.status_code}.")
    try:
        body = got.json()
    except ValueError as trouble:
        raise Nope("Inicio de sesi\u00f3n: la respuesta no era JSON.") from trouble
    if not body.get("success"):
        raise Nope(f"StreamLabs respondi\u00f3 que no: {body}")
    token = (body.get("data") or {}).get("oauth_token")
    if not token:
        raise Nope("StreamLabs no devolvi\u00f3 ning\u00fan token.")
    return token


def token_in_browser(seconds=300):
    """PKCE sign-in: real browser in, loopback page catches the code."""
    seed = os.urandom(64).hex()
    proof = base64.urlsafe_b64encode(hashlib.sha256(seed.encode()).digest()).decode().rstrip("=")
    landed = threading.Event()
    pocket = {}

    class Landing(BaseHTTPRequestHandler):
        def do_GET(self):
            bits = parse_qs(urlparse(self.path).query)
            good = bits.get("success", [""])[0] == "true" and "code" in bits
            pocket["code"] = bits["code"][0] if good else None
            page = (b"<h2>Signed in. You may close this tab.</h2>" if good
                    else b"<h2>Sign-in was declined.</h2>")
            self.send_response(200 if good else 400)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(page)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(page)
            landed.set()

        def log_message(self, *unused):
            return

    gate = HTTPServer(("127.0.0.1", 0), Landing)
    port = gate.server_address[1]
    threading.Thread(target=gate.serve_forever, daemon=True).start()

    link = (f"{SIGNIN}?skip_splash=true&external=electron&tiktok&force_verify"
            f"&origin=slobs&port={port}&code_challenge={proof}&code_flow=true")
    print(f"sign-in callback listening on {port}")
    try:
        if not webbrowser.open(link):
            raise Nope("No se pudo abrir ning\u00fan navegador.")
        if not landed.wait(seconds):
            raise Nope("Se agot\u00f3 el tiempo del inicio de sesi\u00f3n.")
    finally:
        gate.shutdown()
        gate.server_close()

    if not pocket.get("code"):
        raise Nope("La redirecci\u00f3n no tra\u00eda c\u00f3digo.")
    return redeem(pocket["code"], seed)


# ------------------------------------------------------------------ notebook

def open_notebook():
    try:
        return json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def keep_notebook(**pairs):
    book = {**open_notebook(), **pairs}
    spare, scratch = tempfile.mkstemp(dir=HERE, prefix=".nb-", suffix=".tmp")
    os.close(spare)
    try:
        Path(scratch).write_text(json.dumps(book, indent=2), encoding="utf-8")
        os.replace(scratch, NOTEBOOK)
    except BaseException:
        try:
            os.unlink(scratch)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------- jobs

class Job(QThread):
    """Runs one blocking call off the GUI thread and reports back."""

    ready = Signal(object)
    broke = Signal(str)

    def __init__(self, work):
        super().__init__()
        self.work = work

    def run(self):
        try:
            answer = self.work()
        except Exception as trouble:
            self.broke.emit(str(trouble) or type(trouble).__name__)
        else:
            self.ready.emit(answer)


# -------------------------------------------------------------------- frame

THEME = """
QWidget {
    background-color: #121212;
    color: #e8e8e8;
    font-family: "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 12px;
}
QLabel {
    background: transparent;
    color: #9e9e9e;
}
QLineEdit {
    background-color: #1e1e1e;
    border: 1px solid #2b2b2b;
    border-radius: 7px;
    padding: 5px 9px;
    color: #f5f5f5;
    selection-background-color: #fe2c55;
    selection-color: #ffffff;
}
QLineEdit:hover { border: 1px solid #3a3a3a; }
QLineEdit:read-only {
    background-color: #181818;
    border-color: #232323;
    color: #bdbdbd;
}
QLineEdit:focus,
QLineEdit:read-only:focus {
    border: 1px solid #fe2c55;
    background-color: #242424;
}
QPushButton {
    background-color: #1f1f1f;
    border: 1px solid #333333;
    border-radius: 7px;
    padding: 7px 12px;
    color: #e0e0e0;
}
QPushButton:hover {
    background-color: #2a2a2a;
    border-color: #464646;
    color: #ffffff;
}
QPushButton:pressed { background-color: #161616; }
QPushButton:disabled {
    background-color: #171717;
    border-color: #242424;
    color: #555555;
}
QPushButton#primary {
    background-color: #fe2c55;
    border: 1px solid #fe2c55;
    color: #ffffff;
    font-weight: bold;
}
QPushButton#primary:hover {
    background-color: #ff4a6d;
    border-color: #ff4a6d;
    color: #ffffff;
}
QPushButton#primary:pressed { background-color: #d81f45; border-color: #d81f45; }
QPushButton#primary:disabled {
    background-color: #3d1b25;
    border-color: #3d1b25;
    color: #7a5b64;
}
QStatusBar {
    background-color: #0a0a0a;
    color: #9e9e9e;
    border-top: 1px solid #1e1e1e;
}
QStatusBar::item { border: none; }
"""


def slot_box(locked=False):
    box = QLineEdit()
    box.setFixedHeight(30)
    box.setReadOnly(locked)
    return box


def press(text, slot, role="secondary"):
    button = QPushButton(text)
    button.setFixedHeight(34)
    button.setObjectName(role)
    button.setCursor(Qt.PointingHandCursor)
    button.clicked.connect(slot)
    return button


def find_icon():
    """Where the .ico lives: PyInstaller bundle, then next to the source/exe."""
    places = []
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        places.append(Path(bundle) / "icon.ico")
    places.append(HERE / "icon.ico")
    for place in places:
        if place.is_file():
            return place
    return None


class Grabber(QMainWindow):
    def __init__(self):
        super().__init__()
        self.token = ""
        self.job = None

        self.setWindowTitle("Streambot4k KTK")
        self.setMinimumSize(640, 260)
        self.setStyleSheet(THEME)
        art = find_icon()
        if art:
            self.setWindowIcon(QIcon(str(art)))
        self.draw()
        self.setStatusBar(QStatusBar())
        self.unpack()

    # -- construction ------------------------------------------------

    def draw(self):
        self.w = {}
        page = QWidget()
        shell = QVBoxLayout(page)
        shell.setContentsMargins(16, 16, 16, 12)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        shell.addLayout(grid)
        self.setCentralWidget(page)

        self.w["token"] = slot_box(locked=True)
        self.w["rtmp"] = slot_box(locked=True)
        self.w["key"] = slot_box(locked=True)

        for row, (label, name) in enumerate(
            (
                ("Token", "token"),
                ("URL de Transmisión (RTMP)", "rtmp"),
                ("Clave de Transmisión", "key"),
            )
        ):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(self.w[name], row, 1)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.w["web"] = press("Iniciar sesión desde el navegador", self.from_browser)
        self.w["fetch"] = press("Obtener Clave", self.fetch, role="primary")
        row.addWidget(self.w["web"])
        row.addWidget(self.w["fetch"])
        grid.addLayout(row, 3, 0, 1, 2)

    # -- chatter ----------------------------------------------------

    def say(self, text, bad=False):
        bar = self.statusBar()
        bar.showMessage(text)
        colour = "#ff4a6d" if bad else "#25c26a"
        bar.setStyleSheet(f"background-color: #0a0a0a; color: {colour};")

    def freeze(self, working):
        for name in ("web", "fetch"):
            self.w[name].setEnabled(not working)

    def pump(self, work, good, bad):
        if self.job and self.job.isRunning():
            return
        self.job = Job(work)
        self.job.ready.connect(good)
        self.job.broke.connect(bad)
        self.job.start()

    # -- notebook ---------------------------------------------------

    def unpack(self):
        self.token = open_notebook().get("token", "")
        self.w["token"].setText(self.token)

    def jot(self):
        keep_notebook(token=self.token)

    # -- token ------------------------------------------------------

    def from_browser(self):
        self.say("Termina el inicio de sesión en tu navegador...")
        self.pump(token_in_browser, self.got_token, self.oops)

    def got_token(self, token):
        if not token:
            self.say("StreamLabs no devolvió ningún token.", True)
            return
        self.token = token
        self.w["token"].setText(token)
        self.jot()
        self.say("Token obtained. Comprobando la cuenta...")
        self.pump(lambda: describe(token), self.told_account, self.oops)

    def told_account(self, facts):
        who, status, allowed = facts
        verdict = "autorizado para emitir" if allowed else "SIN autorización para emitir"
        self.say(f"{who} / {status} / {verdict}", not allowed)

    def oops(self, text):
        self.say(text, True)

    # -- broadcast --------------------------------------------------

    def fetch(self):
        if not self.token:
            self.say("Primero inicia sesión desde el navegador.", True)
            return
        self.freeze(True)
        self.say("Pidiendo una transmisión a StreamLabs...")
        self.pump(
            lambda: raise_stream(self.token),
            self.got_keys,
            lambda text: (self.freeze(False), self.say(text, True)),
        )

    def got_keys(self, result):
        url, key = result
        self.w["rtmp"].setText(url)
        self.w["key"].setText(key)
        QApplication.clipboard().setText(url + "\n" + key)
        self.freeze(False)
        self.say("Claves obtenidas y copiadas al portapapeles.")

    def closeEvent(self, event):
        try:
            self.jot()
        except OSError as trouble:
            print(f"could not save: {trouble}")
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    art = find_icon()
    if art:
        app.setWindowIcon(QIcon(str(art)))
    frame = Grabber()
    frame.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
