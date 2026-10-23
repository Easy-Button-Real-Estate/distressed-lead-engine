"""Local approval gate and iMessage bridge helpers.

The bridge itself is the open-source ``imsg`` CLI (MIT). This package
does not talk to Apple's private frameworks. It queues commands and
refuses every side effect until the user approves it in the command chat.
"""

__version__ = "1.0.0"
