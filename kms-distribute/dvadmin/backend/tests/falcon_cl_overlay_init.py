# Test-only package overlay: current owned sources first, installed dependencies second.
from pathlib import Path
__path__ = [str(Path(__file__).resolve().parent), '/backend/pqkds']
