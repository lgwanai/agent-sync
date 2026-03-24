#!/usr/bin/env python3
import sys
import os

# Ensure the app module is in the path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import main

if __name__ == "__main__":
    main()
