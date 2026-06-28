#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Hashable, Literal, Sequence, TypeVar

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
USER_INVOKED_POLICY = "policy:\n  allow_implicit_invocation: false\n"

Invocation = Literal["model", "user"]
T = TypeVar("T", bound=Hashable)


@dataclass(frozen=True)
class SkillEntry:
    name: str
    bucket: str
    invocation: Invocation

    @property
    def is_user_invoked(self) -> bool:
        return self.invocation == "user"

    def destination_in(self, skills_root: Path) -> Path:
        return skills_root / self.bucket / self.name


@dataclass(frozen=True)
class SourceSnapshot:
    source: Path
    package: dict[str, Any]
    entries: tuple[SkillEntry, ...]
    plugin_skills: tuple[str, ...]
    commit: str

    @property
    def skill_names(self) -> list[str]:
        return sorted({entry.name for entry in self.entries})

    @property
    def user_invoked_entries(self) -> tuple[SkillEntry, ...]:
        return tuple(entry for entry in self.entries if entry.is_user_invoked)


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Build a Codex plugin repo from the parent mattpocock/skills source repo.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=script_dir.parent,
        help="Source mattpocock/skills repo. Defaults to this script's parent directory.",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=script_dir,
        help="Target Codex plugin repo. Defaults to this script's directory.",
    )
    return parser.parse_args()


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def ensure_source(source: Path, target: Path) -> None:
    if source == target:
        fail("source and target must be different directories")
    if not (source / "skills").is_dir():
        fail(f"skills directory not found in source: {source}")
    if not (source / ".claude-plugin" / "plugin.json").is_file():
        fail(f".claude-plugin/plugin.json not found in source: {source}")


def unquote_yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_frontmatter_fields(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if match is None:
        return {}

    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = unquote_yaml_scalar(value)
    return fields


def is_user_invoked(fields: dict[str, str]) -> bool:
    return (
        fields.get("disable-model-invocation") == "true"
        or fields.get("disable_model_invocation") == "true"
    )


def duplicates_in(values: Sequence[T]) -> list[T]:
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        else:
            seen.add(value)
    return sorted(duplicates)


def discover_skill_entries(source: Path) -> tuple[SkillEntry, ...]:
    entries: list[SkillEntry] = []

    for skill_md in sorted((source / "skills").glob("*/*/SKILL.md")):
        skill_dir = skill_md.parent
        bucket = skill_dir.parent.name
        folder = skill_dir.name
        fields = parse_frontmatter_fields(skill_md)
        name = fields.get("name", folder)
        if name != folder:
            fail(f"SKILL.md name '{name}' does not match folder '{folder}'")

        entries.append(
            SkillEntry(
                name=folder,
                bucket=bucket,
                invocation="user" if is_user_invoked(fields) else "model",
            )
        )

    duplicates = [
        f"{bucket}/{name}"
        for bucket, name in duplicates_in([(entry.bucket, entry.name) for entry in entries])
    ]
    if duplicates:
        fail(f"duplicate skill entries: {', '.join(duplicates)}")
    if not entries:
        fail("no skill directories found under skills/")
    return tuple(entries)


def read_package_json(source: Path) -> dict[str, Any]:
    path = source / "package.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_claude_plugin_skills(source: Path) -> tuple[str, ...]:
    path = source / ".claude-plugin" / "plugin.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    skills = payload.get("skills")
    if not isinstance(skills, list) or not all(isinstance(skill, str) for skill in skills):
        fail(f"{path} must contain a string array at 'skills'")

    duplicates = duplicates_in(skills)
    if duplicates:
        fail(f"duplicate .claude-plugin skills: {', '.join(duplicates)}")

    for skill in skills:
        relative = Path(skill)
        if not skill.startswith("./skills/") or relative.is_absolute() or ".." in relative.parts:
            fail(f"invalid .claude-plugin skill path: {skill}")
        if not (source / skill.removeprefix("./") / "SKILL.md").is_file():
            fail(f".claude-plugin references missing skill: {skill}")

    return tuple(skills)


def source_commit(source: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=source,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def write_user_invoked_openai_yaml(skill_dir: Path) -> None:
    agents_dir = skill_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "openai.yaml").write_text(USER_INVOKED_POLICY, encoding="utf-8")


def transform_text(text: str, skill_names: Sequence[str]) -> str:
    names = "|".join(re.escape(name) for name in sorted(skill_names, key=len, reverse=True))
    if names:
        text = re.sub(
            rf"(?<![A-Za-z0-9._~:/-])/({names})(?![A-Za-z0-9_-]|/)",
            r"$\1",
            text,
        )
    text = text.replace(
        "`disable-model-invocation`",
        "`policy.allow_implicit_invocation`",
    )
    text = text.replace(
        "`disable-model-invocation: true`",
        "`policy.allow_implicit_invocation: false`",
    )
    return text


def transform_skill_md(path: Path, skill_names: Sequence[str]) -> None:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if match is not None:
        frontmatter = "\n".join(
            line
            for line in match.group(1).splitlines()
            if not line.startswith("disable-model-invocation:")
            and not line.startswith("disable_model_invocation:")
            and not line.startswith("argument-hint:")
        )
        text = f"---\n{frontmatter}\n---\n" + text[match.end() :]
    path.write_text(transform_text(text, skill_names), encoding="utf-8")


def transform_text_file(path: Path, skill_names: Sequence[str]) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    path.write_text(transform_text(text, skill_names), encoding="utf-8")


def load_source_snapshot(source: Path) -> SourceSnapshot:
    return SourceSnapshot(
        source=source,
        package=read_package_json(source),
        entries=discover_skill_entries(source),
        plugin_skills=read_claude_plugin_skills(source),
        commit=source_commit(source),
    )


def write_plugin_json(build: Path, snapshot: SourceSnapshot) -> None:
    version = snapshot.package.get("version")
    if not isinstance(version, str) or not version.strip():
        version = "0.1.0"

    payload = {
        "name": "mattpocock",
        "version": version,
        "description": "Matt Pocock's Codex skills for real engineering.",
        "author": {
            "name": "Matt Pocock",
            "url": "https://github.com/mattpocock",
        },
        "homepage": "https://github.com/mattpocock/skills",
        "repository": "https://github.com/mattpocock/skills",
        "license": snapshot.package.get("license", "MIT"),
        "keywords": ["codex", "skills", "engineering", "productivity"],
        "skills": snapshot.plugin_skills,
        "interface": {
            "displayName": "Matt Pocock Skills",
            "shortDescription": "Engineering workflows for Codex",
            "longDescription": (
                "Matt Pocock's agent skills converted into a Codex plugin with explicit "
                "user-invoked workflows and reusable model-invoked disciplines."
            ),
            "developerName": "Matt Pocock",
            "category": "Productivity",
            "capabilities": ["Interactive", "Write"],
            "websiteURL": "https://github.com/mattpocock/skills",
            "defaultPrompt": [
                "Use $ask-matt to choose the right workflow.",
                "Use $grill-with-docs to sharpen a plan.",
            ],
            "screenshots": [],
        },
    }
    plugin_dir = build / ".codex-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_readme(build: Path, commit: str) -> None:
    if commit == "unknown":
        commit_line = "- 사용한 source commit: `unknown`"
    else:
        commit_line = (
            "- 사용한 source commit: "
            f"[`{commit[:5]}`](https://github.com/mattpocock/skills/commit/{commit})"
        )
    body = f"""# Matt Pocock Codex Skills

이 repo는 [mattpocock/skills](https://github.com/mattpocock/skills)를 Codex 용도로 변환한 결과물입니다.

{commit_line}

## Update

원본 repo가 업데이트되면 다음 명령으로 이 Codex용 출력물을 다시 생성합니다.

```bash
# mattpocock의 skills 폴더 안에서 실행
git clone https://github.com/rmekdma/mattpocock.git
./mattpocock/update-from-source.py
cp -r mattpocock ~/.agents/skills

cd mattpocock
git add . && git commit -m "update" && git push origin main
```
"""
    (build / "README.md").write_text(body, encoding="utf-8")


def transform_skills_tree(skills_root: Path, skill_names: Sequence[str]) -> None:
    for path in skills_root.rglob("*"):
        if not path.is_file():
            continue
        if path.name == "SKILL.md":
            transform_skill_md(path, skill_names)
        else:
            transform_text_file(path, skill_names)


def copy_transformed_skills(snapshot: SourceSnapshot, skills_root: Path) -> None:
    shutil.copytree(snapshot.source / "skills", skills_root)
    transform_skills_tree(skills_root, snapshot.skill_names)
    for entry in snapshot.user_invoked_entries:
        write_user_invoked_openai_yaml(entry.destination_in(skills_root))


def build_output(
    target: Path,
    script: Path,
    snapshot: SourceSnapshot,
) -> Path:
    temp = target.parent / f".{target.name}.tmp.{os.getpid()}"
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir(parents=True)

    write_readme(temp, snapshot.commit)
    write_plugin_json(temp, snapshot)
    copy_transformed_skills(snapshot, temp / "skills")
    shutil.copy2(script, temp / script.name)
    return temp


def replace_target(target: Path, build: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    preserve = {".git"}
    for child in list(target.iterdir()):
        if child.name in preserve:
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()

    for child in build.iterdir():
        destination = target / child.name
        if child.is_dir() and not child.is_symlink():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    target = args.target.resolve()
    script = Path(__file__).resolve()

    ensure_source(source, target)
    snapshot = load_source_snapshot(source)
    build = build_output(target, script, snapshot)
    try:
        replace_target(target, build)
    finally:
        if build.exists():
            shutil.rmtree(build)

    user_invoked = [entry.name for entry in snapshot.user_invoked_entries]
    print(f"Synced {len(snapshot.entries)} skills into {target}")
    print("User-invoked skills:", ", ".join(user_invoked))


if __name__ == "__main__":
    main()
