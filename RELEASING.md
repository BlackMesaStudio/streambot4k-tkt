# Publishing checklist

Run through this before the first public commit. It is a technical checklist, not
legal advice.

## 1. Verify the tree

```bat
python -m unittest test_loginmg
python -m flake8 loginmg.py test_loginmg.py make_icon.py verify_exe.py
```

Both must pass with no output.

## 2. Confirm nothing private is staged

```bat
git status --porcelain
git check-ignore -v notebook.json
```

`git check-ignore` must print a rule for `notebook.json`. That file holds the
StreamLabs OAuth token in plain text; it must never be committed. If it ever
was, rotate the token before pushing.

## 3. First commit

```bat
git init
git add -A
git status --porcelain
```

Expect exactly these ten paths, and nothing else:

```
.gitignore
.flake8
LICENSE
README.md
THIRD-PARTY-NOTICES.md
icon.ico
icon.png
loginmg.py
make_icon.py
requirements.txt
run.bat
test_loginmg.py
verify_exe.py
```

If `notebook.json`, `release/`, `dist/`, `build/`, `*.exe` or `__pycache__`
appear, stop — a `.gitignore` rule is broken.

## 4. Verify what is actually in the commit

```bat
git grep -n -i -E "apiToken|oauth_token|password|secret|api[_-]?key" -- "*.py" "*.json" "*.md"
```

Every hit should be a variable name or a doc reference, never a live value.

## 5. Attach the binary as a Release, not a commit

```bat
python -m PyInstaller --noconsole --onefile --name streambot4ktkt ^
    --icon=icon.ico --add-data "icon.ico;." --clean loginmg.py
python verify_exe.py
```

`verify_exe.py` must report `WINDOWS_GUI` and an embedded icon. Then upload
`dist\streambot4ktkt.exe` to a GitHub **Release** and link it from the README.
Do not commit the 51 MB binary: GitHub warns above 50 MB and it bloats every
clone forever.

## 6. Licence and attribution must stay

These four are non-negotiable under GPL-3.0:

| File | Why |
|---|---|
| `LICENSE` | the full licence text has to travel with the work |
| the notice in `loginmg.py` | version 3, warranty disclaimer, credit to Loukious |
| `THIRD-PARTY-NOTICES.md` | itemised list of what was reused and from where |
| `README.md` licence section | states the obligations to anyone redistributing |

Keep `Copyright (C) 2026 Black Mesa Studio` in both `.py` files.

## 7. What this does not cover

- **Terms of service.** The tool automates a private StreamLabs API. Publishing
  it publicly makes that visible to StreamLabs. Nothing in a licence file
  addresses that risk; it is a business decision.
- **Trademark.** The window title carries your own product name, not
  StreamLabs'. Keep it that way.
- **Warranty.** GPL-3.0 §11 and §12 disclaim warranty and liability. That
  protects you, but it also means users have no support commitment.
- **Legal sign-off.** A technical audit cannot tell you whether your particular
  use is lawful in your jurisdiction. Get a lawyer before selling anything.
