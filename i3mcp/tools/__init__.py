"""Importing this package registers every tool on the server."""

from . import focus, move, query, resize  # noqa: F401

# Remaining modules are added task by task; the full list is restored in Task 13:
# from . import (
#     bar,
#     focus,
#     gaps,
#     kill,
#     layout,
#     mark,
#     move,
#     query,
#     resize,
#     scratchpad,
#     window,
#     wm,
#     workspace,
# )
