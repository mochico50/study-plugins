"""マニフェスト、スキル、リンクの整合と、固有情報の紛れ込みを確かめる。

使い方: python3 scripts/validate.py
問題があれば一覧を出して終了コード 1 で終わる。
"""
from pathlib import Path
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
KEBAB = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
SEMVER = re.compile(r'\d+\.\d+\.\d+')
errors = []


def expect(ok, message):
    if not ok:
        errors.append(message)


def load_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        errors.append(f'{path.relative_to(ROOT)}: 読めない（{exc}）')
        return None


def frontmatter(path):
    """SKILL.md の先頭の --- で囲まれた部分を、キーと値の辞書にする。"""
    text = path.read_text(encoding='utf-8')
    match = re.match(r'---\n(.*?)\n---\n', text, flags=re.S)
    if not match:
        return None
    fields = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(':')
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def check_skills(plugin_dir, label):
    skills_dir = plugin_dir / 'skills'
    skill_dirs = sorted(p for p in skills_dir.iterdir() if p.is_dir()) if skills_dir.is_dir() else []
    expect(bool(skill_dirs), f'{label}: skills/ にスキルがない')
    for skill_dir in skill_dirs:
        skill_label = f'{label}/skills/{skill_dir.name}'
        skill_file = skill_dir / 'SKILL.md'
        if not skill_file.is_file():
            errors.append(f'{skill_label}: SKILL.md がない')
            continue
        fields = frontmatter(skill_file)
        if fields is None:
            errors.append(f'{skill_label}: SKILL.md の先頭に frontmatter がない')
            continue
        expect(fields.get('name') == skill_dir.name,
               f'{skill_label}: name（{fields.get("name")}）がフォルダ名と違う')
        expect(bool(KEBAB.fullmatch(skill_dir.name)), f'{skill_label}: スキル名は小文字とハイフンにする')
        description = fields.get('description', '')
        expect(bool(description), f'{skill_label}: description がない')
        expect(len(description) <= 1024, f'{skill_label}: description が 1024 文字を超えている')


def check_marketplace():
    catalog = ROOT / '.claude-plugin/marketplace.json'
    data = load_json(catalog)
    if data is None:
        return
    expect(bool(KEBAB.fullmatch(data.get('name', ''))), 'marketplace.json: name は小文字とハイフンにする')
    expect(bool((data.get('owner') or {}).get('name')), 'marketplace.json: owner.name がない')
    listed = set()
    for entry in data.get('plugins', []):
        name = entry.get('name', '')
        label = f'plugins/{name}'
        expect(name not in listed, f'marketplace.json: {name} が重複している')
        listed.add(name)
        source = entry.get('source')
        if not isinstance(source, str) or '://' in source or '..' in Path(source).parts:
            errors.append(f'marketplace.json: {name} の source は .. を含まない相対パスにする')
            continue
        plugin_dir = ROOT / source
        if not plugin_dir.is_dir():
            errors.append(f'marketplace.json: {name} の source（{source}）が見つからない')
            continue
        manifest = load_json(plugin_dir / '.claude-plugin/plugin.json')
        if manifest is None:
            continue
        expect(manifest.get('name') == name, f'{label}: plugin.json の name が marketplace.json と違う')
        expect(bool(SEMVER.fullmatch(manifest.get('version', ''))),
               f'{label}: plugin.json の version は 1.2.3 の形にする')
        expect(bool(manifest.get('description')), f'{label}: plugin.json に description がない')
        expect((plugin_dir / 'README.md').is_file(), f'{label}: README.md がない')
        expect((plugin_dir / 'LICENSE').is_file(), f'{label}: LICENSE がない')
        check_skills(plugin_dir, label)
    on_disk = {p.name for p in (ROOT / 'plugins').iterdir() if p.is_dir()}
    for name in sorted(on_disk - listed):
        errors.append(f'plugins/{name}: marketplace.json に登録されていない')


def tracked_files():
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True)
    return [ROOT / line for line in out.stdout.splitlines() if (ROOT / line).is_file()]


def check_links(files):
    """Markdown のリンクのうち、リポジトリ内を指すものが実在するか。"""
    for path in files:
        if path.suffix != '.md':
            continue
        text = re.sub(r'```.*?```', '', path.read_text(encoding='utf-8'), flags=re.S)
        for target in re.findall(r'\]\(([^)\s]+)\)', text):
            if re.match(r'[a-z]+:', target) or target.startswith('#'):
                continue
            resolved = (path.parent / target.split('#')[0]).resolve()
            expect(resolved.exists(), f'{path.relative_to(ROOT)}: リンク先がない（{target}）')


# 個人の環境を指す値が紛れ込んでいないかを、形で探す。
# 特定の名前は書かない（このファイル自体が公開されるため）。
PRIVATE_PATTERNS = (
    (re.compile(r'https?://[\w.-]*notion\.(?:so|com|site)/\S*[0-9a-f]{32}'), 'Notion のページ URL'),
    (re.compile(r'https?://[\w-]+\.slack\.com/'), 'Slack のワークスペース URL'),
    (re.compile(r'(?<![A-Za-z0-9])(?=[A-Z0-9]*[0-9])[CGD][A-Z0-9]{8,11}(?![A-Za-z0-9])'), 'Slack のチャンネル ID らしい文字列'),
    (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), 'メールアドレス'),
)
TEXT_SUFFIXES = {'.md', '.json', '.py', '.yml', '.yaml', '.txt', ''}


def check_private(files):
    for path in files:
        if path.suffix not in TEXT_SUFFIXES:
            continue
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, 1):
            for pattern, what in PRIVATE_PATTERNS:
                if pattern.search(line):
                    errors.append(f'{path.relative_to(ROOT)}:{number}: {what}が含まれている')


def main():
    check_marketplace()
    files = tracked_files()
    check_links(files)
    check_private(files)
    if errors:
        print(f'{len(errors)} 件の問題:')
        for message in errors:
            print(f'  - {message}')
        return 1
    print('OK: マニフェスト、スキル、リンク、固有情報のチェックを通過')
    return 0


if __name__ == '__main__':
    sys.exit(main())
