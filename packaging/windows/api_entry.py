"""PyInstaller entry point for the original grading_api package.

Run this with PyInstaller from the repository root so package imports remain intact.
"""

from multiprocessing import freeze_support

from grading_api.server import main


if __name__ == "__main__":
    freeze_support()
    main()
