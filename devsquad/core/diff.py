# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Unified diff and patch engine: generates clean patches, validates hunks, and applies changes safely."""

import difflib
import pathlib
import shutil
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class FileDiff:
    file_path: str
    original_content: str
    modified_content: str
    patch_text: str
    additions: int
    deletions: int
    is_new: bool = False
    is_deleted: bool = False


class DiffEngine:
    """Creates, inspects, and applies unified diffs with automatic backups and rollback."""

    @staticmethod
    def create_diff(file_path: str, original: str, modified: str) -> FileDiff:
        """Computes a unified diff between original and modified file contents."""
        orig_lines = original.splitlines(keepends=True)
        mod_lines = modified.splitlines(keepends=True)

        diff_lines = list(difflib.unified_diff(
            orig_lines,
            mod_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="\n",
        ))

        patch_text = "".join(diff_lines)
        additions = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
        deletions = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))

        return FileDiff(
            file_path=file_path,
            original_content=original,
            modified_content=modified,
            patch_text=patch_text,
            additions=additions,
            deletions=deletions,
            is_new=(len(original) == 0 and len(modified) > 0),
            is_deleted=(len(original) > 0 and len(modified) == 0),
        )

    @staticmethod
    def apply_file_change(root: pathlib.Path, file_path: str, new_content: str, backup: bool = True) -> Tuple[bool, str]:
        """Safely writes content to target file with automatic backup."""
        target = (root / file_path).resolve()

        # Prevent directory traversal attacks
        if not str(target).startswith(str(root.resolve())):
            return False, f"Target path escapes repository root: {file_path}"

        target.parent.mkdir(parents=True, exist_ok=True)

        if backup and target.exists():
            backup_path = target.with_suffix(target.suffix + ".devsquad.bak")
            shutil.copyfile(target, backup_path)

        try:
            target.write_text(new_content, encoding="utf-8")
            return True, f"Successfully applied changes to {file_path}"
        except Exception as e:
            return False, f"Failed applying changes to {file_path}: {e}"

    @staticmethod
    def rollback_file_change(root: pathlib.Path, file_path: str) -> Tuple[bool, str]:
        """Restores a file from its .devsquad.bak backup."""
        target = (root / file_path).resolve()
        backup_path = target.with_suffix(target.suffix + ".devsquad.bak")

        if not backup_path.exists():
            return False, f"No backup file found for {file_path}"

        try:
            shutil.copyfile(backup_path, target)
            backup_path.unlink()
            return True, f"Successfully rolled back {file_path}"
        except Exception as e:
            return False, f"Rollback error on {file_path}: {e}"
