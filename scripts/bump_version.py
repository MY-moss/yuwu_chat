import json
import sys
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(SCRIPT_DIR, "..", "src", "backend", "version.json")
CHANGELOG_FILE = os.path.join(SCRIPT_DIR, "..", "src", "backend", "CHANGELOG.json")


def load_version():
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"major": 1, "minor": 0, "patch": 0}


def save_version(v):
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        json.dump(v, f, indent=4)


def load_changelog():
    try:
        with open(CHANGELOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"history": []}


def save_changelog(cl):
    with open(CHANGELOG_FILE, "w", encoding="utf-8") as f:
        json.dump(cl, f, indent=4, ensure_ascii=False)


def get_version_string(v):
    return f"v{v['major']}.{v['minor']}.{v['patch']}"


def get_change_type_desc(mode):
    desc_map = {
        "major": "重大版本更新",
        "minor": "大版本更新",
        "patch": "小版本更新"
    }
    return desc_map.get(mode, "未知更新")


def bump_version(mode, description=""):
    v = load_version()
    old_version = get_version_string(v)
    
    if mode == "major":
        v["major"] += 1
        v["minor"] = 0
        v["patch"] = 0
    elif mode == "minor":
        v["minor"] += 1
        v["patch"] = 0
    elif mode == "patch":
        v["patch"] += 1
    else:
        print(f"错误: 未知模式 '{mode}'. 可用模式: major, minor, patch")
        sys.exit(1)
    
    new_version = get_version_string(v)
    save_version(v)
    
    cl = load_changelog()
    change_entry = {
        "version": new_version,
        "old_version": old_version,
        "type": mode,
        "type_desc": get_change_type_desc(mode),
        "description": description,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    cl["history"].insert(0, change_entry)
    save_changelog(cl)
    
    return new_version


def show_version():
    v = load_version()
    print(get_version_string(v))


def show_changelog():
    cl = load_changelog()
    history = cl.get("history", [])
    if not history:
        print("暂无版本更新记录")
        return
    
    print("\n版本更新历史:")
    print("=" * 60)
    for i, entry in enumerate(history):
        print(f"\n[{i+1}] {entry['version']}")
        print(f"       类型: {entry['type_desc']}")
        print(f"       时间: {entry['timestamp']}")
        if entry.get("description"):
            print(f"       描述: {entry['description']}")
    print("\n" + "=" * 60)


def show_help():
    print("版本号管理工具")
    print("=" * 30)
    print("用法: python bump_version.py [模式] [描述]")
    print("\n模式:")
    print("  show          - 显示当前版本")
    print("  changelog     - 显示版本更新历史")
    print("  patch         - 小版本更新 (v1.1.1 -> v1.1.2)")
    print("  minor         - 大版本更新 (v1.1.2 -> v1.2.0)")
    print("  major         - 重大版本更新 (v1.2.0 -> v2.0.0)")
    print("\n示例:")
    print("  python bump_version.py patch")
    print("  python bump_version.py minor \"添加新功能\"")
    print("  python bump_version.py major \"玩法大迭代\"")


def main():
    if len(sys.argv) < 2:
        show_help()
        sys.exit(0)
    
    mode = sys.argv[1]
    
    if mode == "show":
        show_version()
    elif mode == "changelog":
        show_changelog()
    elif mode in ["major", "minor", "patch"]:
        description = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        new_version = bump_version(mode, description)
        print(new_version)
    else:
        print(f"错误: 未知模式 '{mode}'")
        show_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
