"""Resource path resolution, kept in its own module deliberately.

``toolbox/main.py`` is the PyInstaller entry script, and a frozen entry
script's own ``__file__`` does NOT resolve the same way a regularly-
imported submodule's does -- confirmed by actually running the frozen
build: ``os.path.dirname(__file__)`` inside ``main.py`` resolved to the
bundle root instead of ``toolbox/``, so the stylesheet load failed with
FileNotFoundError even though the resources were bundled correctly. This
module is always imported normally (never run as ``__main__``), so its
own ``__file__`` resolves correctly in both source and frozen contexts;
everything else should get ``RESOURCES_DIR`` from here rather than
computing it locally.
"""
import os

RESOURCES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources')
