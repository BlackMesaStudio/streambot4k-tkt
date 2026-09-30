"""Static checks on the built executable: PE subsystem and icon resource.

Run it after building:

    python -m PyInstaller --noconsole --onefile --name streambot4ktkt ^
        --icon=icon.ico --add-data "icon.ico;." --clean loginmg.py
    python verify_exe.py

Paths are resolved relative to this file, so it works from any checkout and
never hardcodes a user name.
"""

import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT = HERE / "dist" / "streambot4ktkt.exe"

RT_ICON, RT_GROUP_ICON, RT_VERSION, RT_MANIFEST = 3, 14, 16, 24
NAMES = {RT_ICON: "RT_ICON", RT_GROUP_ICON: "RT_GROUP_ICON",
         RT_VERSION: "RT_VERSION", RT_MANIFEST: "RT_MANIFEST"}


def section_table(data, pe, count, opt):
    out = []
    base = pe + 24 + opt
    for i in range(count):
        _, vsize, vaddr, rawsize, rawptr = struct.unpack_from("<8sIIII", data, base + 40 * i)
        out.append((vaddr, max(vsize, rawsize), rawptr))
    return out


def resource_types(data, rva, sections):
    def to_file(want):
        for vaddr, span, rawptr in sections:
            if vaddr <= want < vaddr + span:
                return rawptr + (want - vaddr)
        raise KeyError(hex(want))

    root = to_file(rva)
    named, identified = struct.unpack_from("<HH", data, root + 12)
    found = []
    for i in range(named + identified):
        entry = root + 8 + i * 8
        kind = struct.unpack_from("<I", data, entry)[0]
        if kind in NAMES:
            found.append(NAMES[kind])
    return found


def inspect(path: Path) -> int:
    data = path.read_bytes()
    print(f"archivo   : {path.name}")
    print(f"tamano    : {len(data) / 1024 / 1024:.1f} MB")

    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\x00\x00":
        print("ERROR: no es un PE valido")
        return 1

    machine = struct.unpack_from("<H", data, pe + 4)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    magic = struct.unpack_from("<H", data, pe + 24)[0]
    subsystem = struct.unpack_from("<H", data, pe + 24 + 68)[0]

    print(f"maquina   : 0x{machine:04x} " + ("(x64)" if machine == 0x8664 else "(x86)"))
    print(f"bits      : {'PE32+' if magic == 0x20B else 'PE32'}")
    print(f"secciones : {count}")

    labels = {2: "WINDOWS_GUI  sin consola, correcto", 3: "WINDOWS_CUI  CON CONSOLA, MAL"}
    print(f"subsistema: {subsystem}  {labels.get(subsystem, 'desconocido')}")

    problems = 0
    if subsystem != 2:
        problems += 1

    data_dir = 112 if magic == 0x20B else 96
    rva = struct.unpack_from("<I", data, pe + 24 + opt + data_dir + 2 * 8)[0]
    if rva == 0:
        print("recursos  : ninguno")
        problems += 1
    else:
        kinds = resource_types(data, rva, section_table(data, pe, count, opt))
        print(f"recursos  : {', '.join(kinds) if kinds else 'ninguno'}")
        has_icon = "RT_GROUP_ICON" in kinds
        print(f"icono     : {'incrustado' if has_icon else 'NO incrustado'}")
        if not has_icon:
            problems += 1

    print()
    if problems:
        print(f"{problems} problema(s) encontrado(s)")
        return 1
    print("todo correcto")
    return 0


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    if not target.is_file():
        print(f"no existe: {target}")
        print("compila primero, o pasa la ruta del exe como argumento")
        return 1
    return inspect(target)


if __name__ == "__main__":
    raise SystemExit(main())
