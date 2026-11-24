"""Configuration and Jules pixel-art color palette."""

from __future__ import annotations

# Authentic Jules pixel-art palette (matching jules.google)
OUTLINE = "#E6DCFF"       # Light lavender pixel outline
BODY = "#705BD6"          # Jules signature purple
HIGHLIGHT = "#9B87F5"     # Top-left dome highlight
SHADOW = "#4E39A8"        # Lower body / tentacle shading
EYE = "#140B29"           # Deep dark indigo eyes
EYE_GLINT = "#FFFFFF"     # Specular glint when happy/curious
BLUSH = "#F472B6"         # Pink cheeks on click/pet

# Pixel-art particle colors
SPARKLE_CYAN = "#38BDF8"
SPARKLE_YELLOW = "#FACC15"
HEART_PINK = "#FB7185"
ZZZ_LAVENDER = "#C4B5FD"

# Logical sprite grid dimensions
GRID_WIDTH = 24
GRID_HEIGHT = 22

# Scale presets (logical pixel -> screen pixels)
PIXEL_SCALES: dict[str, int] = {
    "Pequeno": 3,
    "Médio": 4,
    "Grande": 5,
}
DEFAULT_SCALE_NAME = "Médio"

# Timing & physics constants
FPS = 60
FRAME_MS = 16  # ~60 FPS

FOLLOW_STOP_RADIUS = 72.0
FOLLOW_SPEED = 4.2
ROAM_SPEED = 1.6
WALK_FLOOR_SPEED = 1.8

# Extra transparent canvas padding around the sprite for bobbing & particles
PADDING_X = 28
PADDING_Y = 32
