BAR_HEIGHT = 72
TITLE_HEIGHT = 38

PANEL = (30, 33, 43)
PANEL_DARK = (22, 24, 31)
PANEL_LIGHT = (44, 48, 62)
BORDER = (82, 90, 114)
TEXT = (228, 230, 236)
MUTED = (140, 146, 160)
ACCENT = (96, 146, 235)
GOOD = (120, 200, 130)
BAD = (236, 122, 112)
DISABLED = (88, 92, 104)
SHADOW = (10, 11, 15)

KIND_COLORS = {
    "body": (92, 176, 104),
    "sense": (86, 152, 226),
    "action": (232, 154, 72),
    "reaction": (192, 104, 204),
}


def mix(first, second, amount):
    return tuple(int(first[index] + (second[index] - first[index]) * amount) for index in range(3))