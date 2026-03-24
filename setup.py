from setuptools import setup, find_packages

setup(
    name="agent-sync",
    version="1.0.0",
    description="A TUI tool to configure, manage, backup and restore AI Agent environments and skills",
    author="Wu Liang",
    py_modules=["app", "backup_restore"],
    entry_points={
        "console_scripts": [
            "agent-sync=app:main",
        ],
    },
    python_requires=">=3.6",
)
