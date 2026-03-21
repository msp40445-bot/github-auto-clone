"""Tests for utility functions."""


from github_auto_clone.utils import (
    detect_language,
    extract_imports_js,
    extract_imports_python,
    format_size,
    is_config_file,
    is_doc_file,
    is_test_file,
    sanitize_name,
    should_skip_dir,
    truncate_text,
)


def test_detect_language() -> None:
    assert detect_language("main.py") == "Python"
    assert detect_language("app.ts") == "TypeScript"
    assert detect_language("index.js") == "JavaScript"
    assert detect_language("main.rs") == "Rust"
    assert detect_language("main.go") == "Go"
    assert detect_language("data.bin") is None


def test_is_test_file() -> None:
    assert is_test_file("tests/test_main.py") is True
    assert is_test_file("test_utils.py") is True
    assert is_test_file("src/main.py") is False
    assert is_test_file("component.test.tsx") is True
    assert is_test_file("component.spec.js") is True


def test_is_doc_file() -> None:
    assert is_doc_file("README.md") is True
    assert is_doc_file("docs/guide.md") is True
    assert is_doc_file("CHANGELOG.md") is True
    assert is_doc_file("src/main.py") is False


def test_is_config_file() -> None:
    assert is_config_file("package.json") is True
    assert is_config_file("pyproject.toml") is True
    assert is_config_file("Dockerfile") is True
    assert is_config_file("main.py") is False


def test_should_skip_dir() -> None:
    assert should_skip_dir("node_modules") is True
    assert should_skip_dir("__pycache__") is True
    assert should_skip_dir(".git") is True
    assert should_skip_dir("src") is False


def test_sanitize_name() -> None:
    assert sanitize_name("My Project!@#") == "my_project"
    assert sanitize_name("hello--world") == "hello--world"


def test_truncate_text() -> None:
    assert truncate_text("hello", 10) == "hello"
    assert truncate_text("hello world this is long", 10) == "hello w..."


def test_format_size() -> None:
    assert format_size(500) == "500.0 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024) == "1.0 MB"


def test_extract_imports_python() -> None:
    code = """
import os
import sys
from pathlib import Path
from typing import Any
from mypackage.module import something
import json as j
"""
    imports = extract_imports_python(code)
    assert "os" in imports
    assert "sys" in imports
    assert "pathlib" in imports
    assert "typing" in imports
    assert "mypackage" in imports
    assert "json" in imports


def test_extract_imports_js() -> None:
    code = """
import React from 'react';
import { useState } from 'react';
import axios from 'axios';
import { helper } from './utils';
const fs = require('fs');
const path = require('path');
const local = require('./local');
"""
    imports = extract_imports_js(code)
    assert "react" in imports
    assert "axios" in imports
    assert "fs" in imports
    assert "path" in imports
    # Relative imports should not be included
    assert "./utils" not in imports
    assert "./local" not in imports
