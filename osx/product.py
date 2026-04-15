def name(version: str) -> str:
    MACOS_NAMES = {
        26: "Tahoe",
        15: "Sequoia",
        14: "Sonoma",
        13: "Ventura",
        12: "Monterey",
        11: "Big Sur",
    }

    OSX_NAMES = {
        15: "Catalina",
        14: "Mojave",
        13: "High Sierra",
        12: "Sierra",
        11: "El Capitan",
        10: "Yosemite",
        9: "Mavericks",
        8: "Mountain Lion",
        7: "Lion",
        6: "Snow Leopard",
        5: "Leopard",
        4: "Tiger",
        3: "Panther",
        2: "Jaguar",
        1: "Puma",
        0: "Cheetah",
    }

    assert version and len(version), "Invalid version tuple"

    major, *minor = map(int, version.split("."))
    minor = minor[0] if minor else 0

    if major > 26:
        return f"macOS {major}.{minor}"

    if major >= 11:
        try:
            return f"macOS {MACOS_NAMES[major]}"
        except KeyError:
            raise ValueError(f"Unknown macOS version: {major}.{minor}")

    if major == 10:
        name = OSX_NAMES.get(minor)
        if not name:
            raise ValueError(f"Unknown macOS version: {major}.{minor}")

        if minor >= 12:
            return f"macOS {name}"
        elif minor >= 8:
            return f"OS X {name}"
        else:
            return f"Mac OS X {name}"

    raise ValueError(f"Unknown macOS version: {major}.{minor}")
