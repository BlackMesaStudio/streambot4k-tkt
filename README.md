# loginmg - Streambot4k KTK

One file, one job: sign in to StreamLabs, open a TikTok broadcast, get the
**RTMP url** and the **stream key** on the clipboard.

```
loginmg/
├── loginmg.py       the whole program
├── test_loginmg.py  42 offline tests + a headless run of the window
├── run.bat          double-click launcher
├── icon.jpg         source artwork
├── make_icon.py     icon.jpg -> icon.ico
├── verify_exe.py    PE header / resource checks on the built binary
└── requirements.txt
```

## Run it

Double-click `run.bat` (or the shortcut on the desktop).

```
python loginmg.py
```

## Use it

1. **Iniciar sesión desde el navegador** — opens the real StreamLabs login page,
   waits for the OAuth redirect, stores the token in `notebook.json`. The status
   bar then tells you whether the account is `autorizado para emitir`.
2. **Obtener Clave** — the RTMP url and stream key appear, and both are already
   on the clipboard.
3. Paste into OBS: **Server** = the RTMP url, **Stream key** = the stream key.

| Field in OBS | Value |
|---|---|
| Server | `rtmp://push-tmp-…tiktokcdn.com:443/live` |
| Stream key | the `on-…Secret=…` string |

## Appearance

Dark matte theme with TikTok red, defined in the `THEME` constant:

| Element | Colour |
|---|---|
| window background | `#121212` |
| field background / read-only | `#1e1e1e` / `#181818` |
| field border at rest | `#2b2b2b` |
| **field border and focus ring** | **`#fe2c55`** |
| primary button (Obtener Clave) | `#fe2c55`, white bold, lighter on hover |
| secondary button | `#1f1f1f` with a `#333333` border |
| status bar | `#0a0a0a`, green for success, red for errors |

The three fields are read-only: the token only ever arrives from the browser
sign-in, and the url and key only from the API, so there is nothing to type.
That is also why the show/hide eye was removed.

> The focus rule is declared **after** the `:read-only` rule on purpose. Qt Style
> Sheets let the last matching rule win, so the reverse order would silently kill
> the red ring on read-only fields. `test_focus_rule_beats_the_read_only_rule`
> guards the order and `test_focus_border_is_actually_red` renders the widget and
> counts the red pixels.

The window frame (title bar) is still drawn by Windows; styling it would need a
frameless window with a custom title bar, which breaks drag and resize.

## Endpoints

```
GET  https://streamlabs.com/api/v5/slobs/tiktok/info               check the account
POST https://streamlabs.com/api/v5/slobs/tiktok/stream/start      open a broadcast
GET  https://streamlabs.com/api/v5/slobs/auth/data                trade the login code
GET  https://streamlabs.com/slobs/login?...&code_flow=true        the login page
```

Every request impersonates the Streamlabs desktop client
(`StreamlabsDesktop/1.17.0 ... Electron/29.3.1`), because the slobs API answers
nothing else.

`stream/start` is sent as multipart with a fixed `title=live`, an empty
`category` and `audience_type=0` — the endpoint requires all four fields, so the
title cannot simply be left out of the request.

Layout of `loginmg.py`:

| Block | What it does |
|---|---|
| `ask` + `describe` / `raise_stream` | the slobs calls |
| `token_in_browser` + `redeem` | PKCE sign-in with a loopback landing page |
| `open_notebook` / `keep_notebook` | remembers the token |
| `Job` | runs one blocking call on a `QThread` |
| `Grabber` | three fields and two buttons |

## Tests

```
python -m unittest test_loginmg
```

Nothing touches the network: the API is faked and the OAuth landing page is
exercised for real on `127.0.0.1`. `python -m flake8 loginmg.py test_loginmg.py`
is clean.

## Not included

Mature-audience toggle, game/category search, the token-from-disk scan (needs
the StreamLabs Desktop app installed), stopping the broadcast, the update check,
the donation prompt, the help dialog and the live-monitor link. None of them
change the rtmp/key you get. Say the word and any of them goes back in.

## Build a .exe

```bat
python make_icon.py
python -m PyInstaller --noconsole --onefile --name streambot4ktkt --icon=icon.ico --add-data "icon.ico;." --clean loginmg.py
```

Produces `dist\streambot4ktkt.exe`. Verified properties of the current build:

| Property | Value |
|---|---|
| size | 51.0 MB |
| architecture | x64, PE32+ |
| PE subsystem | `2` = `WINDOWS_GUI` — no console window |
| icon in the file | 7 resolutions baked in, shows in Explorer |
| icon in the title bar | loaded at runtime by `find_icon()` + `setWindowIcon()` |
| `notebook.json` | written next to the `.exe`, not into the temp extraction folder |

> `--icon` only stamps the icon into the executable, which is what Explorer and
> shortcuts read. Qt does **not** pick that up on its own, so the title bar,
> Alt+Tab and the taskbar would show the generic icon. That is what
> `find_icon()` plus `app.setWindowIcon()` is for, and `--add-data` is what puts
> `icon.ico` inside the bundle where `sys._MEIPASS` can find it.
>
> `find_icon()` returns `None` instead of raising when the file is missing, so a
> missing icon degrades to the Qt default rather than a crash.

`make_icon.py` centre-crops `icon.jpg` to a square and writes `icon.ico` with
16/24/32/48/64/128/256 px. JPEG has no alpha channel, so the icon is opaque; the
logo's own background is near-black, which suits a taskbar anyway.

`verify_exe.py` prints the PE header facts above. To check the icon at runtime,
launch the exe and look at the window class: Qt names it `…QWindowIcon` only when
an icon is set.

> `--onefile` extracts to a temp folder on every launch, so the first start takes
> roughly 15-20 seconds. `--onedir` starts instantly but produces a folder
> instead of a single file. Note that PyInstaller onefile spawns a child process
> — the window belongs to the child, not the process you launched.

## License

GNU General Public License v3.0 — see [`LICENSE`](LICENSE).

```
loginmg.py                 GPL-3.0 notice + attribution in the module docstring
test_loginmg.py            same
LICENSE                    full GPL-3.0 text, from gnu.org
THIRD-PARTY-NOTICES.md     what was reused from the upstream project, and what was not
.gitignore                 keeps your token file out of git
```

Copyright (C) 2026 **Black Mesa Studio**. The copyright holder is named in both
`.py` files, as the GPL requires, and the licence text travels with the work.

### Attribution

The StreamLabs API contract used here — endpoint paths, request field names, the
required `Sec-Fetch-*` headers and the desktop user agent — was learned from
[Loukious/StreamlabsTikTokStreamKeyGenerator](https://github.com/Loukious/StreamlabsTikTokStreamKeyGenerator),
which is GPL-3.0, by **Loukious**. No code was copied; see
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md) for the itemised list of what
was reused.

If you redistribute this, GPL-3.0 requires you to also offer the complete
source of whatever you distribute, under the same license, with these notices
intact. Personal use on your own machine carries no such obligation.

> `notebook.json` holds your StreamLabs OAuth token in plain text. It is listed
> in `.gitignore` — do not remove that line, and if you ever commit by accident,
> rotate the token before pushing.
