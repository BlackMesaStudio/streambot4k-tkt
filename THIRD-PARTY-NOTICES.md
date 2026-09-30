# Third-Party Notices

Copyright (C) 2026 **Black Mesa Studio**. Licensed under the GNU General Public
License v3.0 — see [`LICENSE`](LICENSE).

This project is an independent reimplementation. It is not affiliated with,
endorsed by, or a fork of any of the projects listed below.

---

## StreamlabsTikTokStreamKeyGenerator

- **Upstream:** <https://github.com/Loukious/StreamlabsTikTokStreamKeyGenerator>
- **Author:** Loukious (<https://buymeacoffee.com/loukious>)
- **Version consulted:** 2.0.9
- **License:** GNU General Public License v3.0 (see [`LICENSE`](LICENSE))
- **Relationship:** no source code was copied. What was reused is the *API
  contract* — the facts a server dictates, which copyright does not protect:

  | Reused | Value |
  |---|---|
  | Endpoints | `https://streamlabs.com/api/v5/slobs/tiktok/info`, `.../stream/start`, `.../stream/{id}/end`, `.../slobs/auth/data`, `.../slobs/login` |
  | Request fields | `title`, `device_platform`, `category`, `audience_type`, `rtmp`, `key`, `id`, `success`, `user`, `application_status`, `can_be_live` |
  | Token exchange | `code_verifier`, `code`, `code_challenge`, `code_flow=true`, `skip_splash`, `external=electron`, `tiktok`, `force_verify`, `origin=slobs`, `port` |
  | Required headers | `authorization: Bearer …`, `user-agent: StreamlabsDesktop/…`, `Accept`, `Accept-Language`, `Sec-Fetch-Site: cross-site`, `Sec-Fetch-Mode: cors`, `Sec-Fetch-Dest: empty` |
  | LevelDB token record | the literal `"apiToken":"<hex>"` written by the StreamLabs desktop app |
  | Storage paths | `%appdata%\slobs-client\Local Storage\leveldb\*.log` and the macOS equivalent |

  Everything else — the file layout, the class and function names, the window,
  the styling, the threading model, the error handling and the tests — was
  written from scratch for this project.

  If you consider this work a derivative of the upstream project, the upstream
  GPL-3.0 terms apply, and this project is already distributed under those terms
  with its complete corresponding source. Either way the obligations are the
  same and are met.

---

## Runtime dependencies

Neither is vendored; both are installed from PyPI and carry their own licenses.

| Package | License | Project |
|---|---|---|
| PySide6 | LGPL-3.0 (with the Qt for Python terms) | <https://pypi.org/project/PySide6/> |
| requests | Apache-2.0 | <https://pypi.org/project/requests/> |

`certifi` and `urllib3` come in as transitive dependencies of `requests`.

---

## External services

No data is sent anywhere except the hosts listed here, and only when you press a
button:

| Host | When | What |
|---|---|---|
| `streamlabs.com` | always | token exchange, account lookup, broadcast start |
| `livecenter.tiktok.com` | never (not linked) | — |

---

## Not legal advice

This file is an engineering record of what was reused and from where. It is not
legal advice. Get a qualified lawyer before relying on it for a commercial
release.
