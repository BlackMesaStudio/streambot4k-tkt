"""Offline tests for the RTMP grabber, plus a headless run of the window.

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
"""

import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import loginmg as g

DEAD = "0" * 24
HOME = Path(__file__).resolve().parent
BOX = {}


class Answer:
    def __init__(self, body=None, status=200):
        self.body = body
        self.status_code = status

    def json(self):
        if self.body is None:
            raise ValueError("nope")
        return self.body


def answering(body=None, status=200):
    return mock.patch.object(g.requests, "request", return_value=Answer(body, status))


class ApiTests(unittest.TestCase):
    def test_authorization_header(self):
        self.assertEqual(g.identify(DEAD)["authorization"], f"Bearer {DEAD}")
        self.assertIn("StreamlabsDesktop", g.identify()["user-agent"])
        self.assertNotIn("authorization", g.identify())

    def test_url_and_verb(self):
        with answering({}) as request:
            g.ask(DEAD, "/info")
        self.assertEqual(request.call_args.args[1], g.API + "/info")
        self.assertEqual(request.call_args.args[0], "GET")

    def test_refused_token(self):
        for status in (401, 403):
            with answering({}, status):
                with self.assertRaises(g.Nope) as caught:
                    g.ask(DEAD, "/info", topic="Account")
            self.assertIn("rechaz", str(caught.exception))

    def test_other_http_error(self):
        with answering({}, 500):
            with self.assertRaises(g.Nope) as caught:
                g.ask(DEAD, "/info", topic="Account")
        self.assertIn("500", str(caught.exception))

    def test_not_json(self):
        with answering(None, 200):
            with self.assertRaises(g.Nope):
                g.ask(DEAD, "/info", topic="Account")

    def test_offline(self):
        with mock.patch.object(g.requests, "request", side_effect=g.requests.ConnectionError("x")):
            with self.assertRaises(g.Nope) as caught:
                g.ask(DEAD, "/info", topic="Account")
        self.assertIn("x", str(caught.exception))

    def test_describe(self):
        with answering({
            "user": {"username": "irsak1"},
            "application_status": {"status": "approved"},
            "can_be_live": True,
        }):
            self.assertEqual(g.describe(DEAD), ("irsak1", "approved", True))

    def test_describe_defaults(self):
        with answering({}):
            self.assertEqual(g.describe(DEAD), ("unknown", "unknown", False))

    def test_raise_stream_fields(self):
        body = {"rtmp": "rtmp://x/live", "key": "abc", "id": "77"}
        with answering(body) as request:
            self.assertEqual(g.raise_stream(DEAD), ("rtmp://x/live", "abc"))
        sent = dict((k, v[1]) for k, v in request.call_args.kwargs["files"])
        self.assertEqual(sent, {
            "title": "live", "device_platform": "win32",
            "category": "", "audience_type": "0",
        })
        self.assertEqual(request.call_args.args[0], "POST")
        self.assertTrue(request.call_args.args[1].endswith("/stream/start"))

    def test_raise_stream_incomplete(self):
        with answering({"nope": 1}):
            with self.assertRaises(g.Nope):
                g.raise_stream(DEAD)


class RedeemTests(unittest.TestCase):
    def test_happy(self):
        body = {"success": True, "data": {"oauth_token": "tok"}}
        with mock.patch.object(g.requests, "get", return_value=Answer(body)) as get:
            self.assertEqual(g.redeem("code1", "seed1"), "tok")
        self.assertEqual(get.call_args.kwargs["params"],
                         {"code_verifier": "seed1", "code": "code1"})
        self.assertEqual(get.call_args.args[0], g.AUTH)

    def test_browser_headers(self):
        body = {"success": True, "data": {"oauth_token": "tok"}}
        with mock.patch.object(g.requests, "get", return_value=Answer(body)) as get:
            g.redeem("c", "s")
        head = get.call_args.kwargs["headers"]
        self.assertEqual(head["Sec-Fetch-Site"], "cross-site")
        self.assertIn("1.20.4", head["User-Agent"])

    def test_http_error(self):
        with mock.patch.object(g.requests, "get", return_value=Answer(None, 500)):
            with self.assertRaises(g.Nope):
                g.redeem("c", "s")

    def test_not_json(self):
        with mock.patch.object(g.requests, "get", return_value=Answer(None, 200)):
            with self.assertRaises(g.Nope):
                g.redeem("c", "s")

    def test_declined(self):
        with mock.patch.object(g.requests, "get", return_value=Answer({"success": False})):
            with self.assertRaises(g.Nope):
                g.redeem("c", "s")

    def test_no_token(self):
        body = {"success": True, "data": {}}
        with mock.patch.object(g.requests, "get", return_value=Answer(body)):
            with self.assertRaises(g.Nope):
                g.redeem("c", "s")

    def test_offline(self):
        with mock.patch.object(g.requests, "get", side_effect=g.requests.ConnectionError("z")):
            with self.assertRaises(g.Nope) as caught:
                g.redeem("c", "s")
        self.assertIn("z", str(caught.exception))


class SignInTests(unittest.TestCase):
    def drive(self, query, answer, seconds=20):
        self.landed = (0, "")
        opened = []
        released = threading.Event()

        def opener(link):
            opened.append(link)
            threading.Thread(target=self.hit, args=(link, query), daemon=True).start()
            released.set()
            return True

        result = {}

        def worker():
            try:
                result["token"] = g.token_in_browser(seconds=seconds)
            except BaseException as trouble:
                result["error"] = trouble

        with mock.patch.object(g.webbrowser, "open", opener), mock.patch.object(
            g.requests, "get", return_value=answer
        ):
            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            self.assertTrue(released.wait(10), "browser never opened")
            thread.join(25)
            self.assertFalse(thread.is_alive(), "sign-in never finished")
        return opened, result

    def hit(self, link, query):
        port = link.split("port=")[1].split("&")[0]
        time.sleep(0.4)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/?{query}", timeout=5) as got:
                self.landed = (got.status, got.read().decode())
        except urllib.error.HTTPError as trouble:
            self.landed = (trouble.code, trouble.read().decode())
        except OSError as trouble:
            self.landed = (0, str(trouble))

    def test_happy(self):
        answer = Answer({"success": True, "data": {"oauth_token": "final"}})
        opened, result = self.drive("success=true&code=xyz", answer)
        self.assertEqual(result.get("token"), "final")
        self.assertEqual(self.landed[0], 200)
        self.assertIn("Signed in", self.landed[1])
        self.assertIn("code_flow=true", opened[0])
        self.assertIn("force_verify", opened[0])

    def test_challenge_is_unpadded_base64(self):
        answer = Answer({"success": True, "data": {"oauth_token": "final"}})
        opened, _ = self.drive("success=true&code=xyz", answer)
        proof = opened[0].split("code_challenge=")[1].split("&")[0]
        self.assertNotIn("=", proof)
        self.assertEqual(len(proof), 43)

    def test_declined(self):
        answer = Answer({"success": True, "data": {"oauth_token": "final"}})
        _, result = self.drive("success=false", answer)
        self.assertIsInstance(result.get("error"), g.Nope)
        self.assertEqual(self.landed[0], 400)
        self.assertIn("declined", self.landed[1])

    def test_no_browser(self):
        with mock.patch.object(g.webbrowser, "open", return_value=False):
            with self.assertRaises(g.Nope):
                g.token_in_browser(seconds=5)

    def test_timeout(self):
        with mock.patch.object(g.webbrowser, "open", return_value=True):
            with self.assertRaises(g.Nope):
                g.token_in_browser(seconds=1)


class NotebookTests(unittest.TestCase):
    def test_missing_file(self):
        with mock.patch.object(g, "NOTEBOOK", HOME / "nope.json"):
            self.assertEqual(g.open_notebook(), {})

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "notebook.json"
            with mock.patch.object(g, "NOTEBOOK", target):
                g.keep_notebook(token="abc")
                self.assertEqual(g.open_notebook(), {"token": "abc"})
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["notebook.json"])

    def test_merges(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "notebook.json"
            target.write_text('{"a": 1}', encoding="utf-8")
            with mock.patch.object(g, "NOTEBOOK", target):
                g.keep_notebook(b=2)
                self.assertEqual(g.open_notebook(), {"a": 1, "b": 2})

    def test_broken_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "notebook.json"
            target.write_text("{oops", encoding="utf-8")
            with mock.patch.object(g, "NOTEBOOK", target):
                self.assertEqual(g.open_notebook(), {})

    def test_no_scratch_left_behind_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "notebook.json"
            with mock.patch.object(g, "NOTEBOOK", target):
                with mock.patch.object(g.os, "replace", side_effect=OSError("busy")):
                    with self.assertRaises(OSError):
                        g.keep_notebook(token="x")
            self.assertEqual([p.name for p in Path(tmp).iterdir()], [])


class FrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        (HOME / "notebook.json").unlink(missing_ok=True)
        self.win = g.Grabber()
        BOX.clear()
        BOX.update(self.win.w)

    def tearDown(self):
        self.win.close()
        (HOME / "notebook.json").unlink(missing_ok=True)

    def settle(self, seconds=8):
        for _ in range(5):
            self.qt.processEvents()
            time.sleep(0.02)
        job = self.win.job
        end = time.time() + seconds
        while job is not None and job.isRunning() and time.time() < end:
            self.qt.processEvents()
            time.sleep(0.02)
        for _ in range(20):
            self.qt.processEvents()
            time.sleep(0.02)

    def say(self):
        return self.win.statusBar().currentMessage()

    def test_shape(self):
        self.assertEqual(self.win.windowTitle(), "Streambot4k KTK")
        self.assertEqual(sorted(BOX), ["fetch", "key", "rtmp", "token", "web"])
        self.assertEqual(BOX["fetch"].text(), "Obtener Clave")
        self.assertEqual(BOX["web"].text(), "Iniciar sesi\u00f3n desde el navegador")
        self.assertTrue(BOX["rtmp"].isReadOnly())
        self.assertTrue(BOX["key"].isReadOnly())

    def test_token_field_is_read_only_and_visible(self):
        from PySide6.QtWidgets import QLineEdit

        self.assertTrue(BOX["token"].isReadOnly())
        self.assertEqual(BOX["token"].echoMode(), QLineEdit.Normal)
        self.assertFalse(hasattr(self.win, "peek"))

    def test_primary_button_is_the_red_one(self):
        self.assertEqual(BOX["fetch"].objectName(), "primary")
        self.assertEqual(BOX["web"].objectName(), "secondary")
        self.assertIn("#fe2c55", g.THEME)

    def test_focus_rule_beats_the_read_only_rule(self):
        focus = g.THEME.rindex("QLineEdit:focus")
        read_only = g.THEME.rindex("QLineEdit:read-only {")
        self.assertGreater(focus, read_only, "focus would be overridden by read-only")
        self.assertIn("QLineEdit:read-only:focus", g.THEME)

    def test_focus_border_is_actually_red(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor

        win = self.win
        win.show()
        win.activateWindow()
        field = win.w["token"]
        field.setFocus(Qt.OtherFocusReason)
        self.qt.processEvents()

        def red_pixels():
            image = win.grab().toImage()
            found = 0
            for y in range(field.y() - 2, field.y() + field.height() + 2):
                for x in range(field.x() - 2, field.x() + field.width() + 2):
                    colour = QColor(image.pixel(x, y))
                    if colour.red() > 200 and colour.green() < 110 and colour.blue() < 130:
                        found += 1
            return found

        on = red_pixels()
        field.clearFocus()
        self.qt.processEvents()
        self.assertGreater(on, 0, "focused field showed no TikTok red")
        self.assertEqual(red_pixels(), 0, "blurred field still showed red")
        win.hide()

    def test_labels_are_spanish(self):
        from PySide6.QtWidgets import QLabel

        wanted = ["Token", "URL de Transmisi\u00f3n (RTMP)", "Clave de Transmisi\u00f3n"]
        found = [w.text() for w in self.win.findChildren(QLabel) if w.text() in wanted]
        self.assertEqual(sorted(found), sorted(wanted))

    def test_fetch_needs_a_sign_in(self):
        self.assertEqual(self.win.token, "")
        self.win.fetch()
        self.assertIn("inicia sesi\u00f3n desde el navegador", self.say())

    def test_fetch_fills_and_copies(self):
        from PySide6.QtWidgets import QApplication

        self.win.token = DEAD
        with mock.patch.object(g, "raise_stream", return_value=("rtmp://a/b", "sekret")):
            self.win.fetch()
            self.settle()
        self.assertEqual(BOX["rtmp"].text(), "rtmp://a/b")
        self.assertEqual(BOX["key"].text(), "sekret")
        self.assertEqual(QApplication.clipboard().text(), "rtmp://a/b\nsekret")
        self.assertIn("portapapeles", self.say())
        self.assertTrue(BOX["fetch"].isEnabled())

    def test_fetch_failure_unfreezes(self):
        self.win.token = DEAD
        with mock.patch.object(g, "raise_stream", side_effect=g.Nope("denied")):
            self.win.fetch()
            self.settle()
        self.assertIn("denied", self.say())
        self.assertTrue(BOX["fetch"].isEnabled())
        self.assertEqual(BOX["key"].text(), "")

    def test_sign_in_then_account(self):
        with mock.patch.object(g, "token_in_browser", return_value="abc"):
            with mock.patch.object(g, "describe", return_value=("irsak1", "approved", True)):
                self.win.from_browser()
                self.settle()
        self.assertEqual(BOX["token"].text(), "abc")
        self.assertEqual(self.win.token, "abc")
        self.assertIn("irsak1", self.say())
        self.assertIn("autorizado", self.say())

    def test_sign_in_reports_a_blocked_account(self):
        with mock.patch.object(g, "token_in_browser", return_value="abc"):
            with mock.patch.object(g, "describe", return_value=("x", "denied", False)):
                self.win.from_browser()
                self.settle()
        self.assertIn("SIN autorizaci\u00f3n", self.say())

    def test_sign_in_without_a_token(self):
        with mock.patch.object(g, "token_in_browser", return_value=""):
            self.win.from_browser()
            self.settle()
        self.assertIn("ning\u00fan token", self.say())
        self.assertEqual(self.win.token, "")

    def test_notebook_roundtrip(self):
        self.win.token = "keepme"
        self.win.jot()
        twin = g.Grabber()
        try:
            self.assertEqual(twin.w["token"].text(), "keepme")
            self.assertEqual(twin.token, "keepme")
        finally:
            twin.close()

    def test_saved_on_close(self):
        self.win.token = "closing"
        self.win.close()
        self.assertTrue((HOME / "notebook.json").exists())

    def test_main_keeps_the_window_alive(self):
        with mock.patch.object(g, "QApplication") as fake_app:
            with mock.patch.object(g, "Grabber") as frame:
                g.main()
        frame.return_value.show.assert_called_once()
        fake_app.return_value.exec.assert_called_once()

    def test_icon_is_loaded_from_disk(self):
        from PySide6.QtGui import QIcon

        art = g.find_icon()
        self.assertIsNotNone(art, "icon.ico not found next to the source")
        self.assertEqual(art.suffix, ".ico")
        icon = QIcon(str(art))
        self.assertFalse(icon.isNull(), "Qt could not decode icon.ico")
        self.assertGreater(icon.availableSizes().width() if hasattr(icon.availableSizes(), "width")
                           else len(icon.availableSizes()), 0)

    def test_icon_lookup_survives_a_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(g, "HERE", Path(tmp)):
                with mock.patch.object(sys, "_MEIPASS", str(Path(tmp)), create=True):
                    self.assertIsNone(g.find_icon())

    def test_icon_path_prefers_the_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp)
            (bundle / "icon.ico").write_bytes(b"fake")
            with mock.patch.object(sys, "_MEIPASS", str(bundle), create=True):
                self.assertEqual(g.find_icon(), bundle / "icon.ico")

    def test_window_carries_the_icon(self):
        icon = self.win.windowIcon()
        self.assertFalse(icon.isNull(), "the window has no icon set")

    def test_window_icon_comes_from_the_file(self):
        from PySide6.QtGui import QIcon

        self.assertEqual(g.find_icon(), HOME / "icon.ico")
        self.assertFalse(QIcon(str(g.find_icon())).isNull())


if __name__ == "__main__":
    unittest.main(verbosity=2)
