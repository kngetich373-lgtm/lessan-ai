"""Runtime compatibility aliases for PyQt6 imports used by legacy UI modules.

PyQt6 exposes QKeySequence and QShortcut from QtGui, while some Lessan UI
code historically imported them from QtCore. Python loads sitecustomize before
main.py, so normalize those names before any UI module is imported.
"""
try:
    from PyQt6 import QtCore, QtGui

    if not hasattr(QtCore, "QKeySequence"):
        QtCore.QKeySequence = QtGui.QKeySequence
    if not hasattr(QtCore, "QShortcut"):
        QtCore.QShortcut = QtGui.QShortcut
except Exception:
    # Keep Python startup resilient if PyQt6 is unavailable; the normal
    # dependency/bootstrap path will report the actual missing dependency.
    pass
