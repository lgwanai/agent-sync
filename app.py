import os
import sys
import json
import re
import urllib.request
import urllib.error
import time

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.txt")
TOOL_SKILL_PATHS = {
    "Trae": "~/.trae/skills/",
    "Claude Code": "~/.claude/skills/",
    "OpenClaw": "~/.openclaw/skills/",
    "Open Code": "~/.opencode/skills/",
    "Open Code (Config)": "~/.config/opencode/skills/",
    "QClaw": "~/.qclaw/skills/",
    "Workbuddy": "~/.workbuddy/skills/",
    "General Agents": "~/.agents/skills/"
}

def read_kv(path):
    d = {}
    if not os.path.exists(path):
        return d
    try:
        with open(path, "r") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                if s.startswith("#"):
                    continue
                if "=" in s:
                    k, v = s.split("=", 1)
                    d[k.strip()] = v.strip()
    except Exception:
        pass
    return d

def write_kv(path, d):
    lines = []
    for k, v in d.items():
        lines.append(f"{k}={v}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")

def ensure_model_config():
    conf = read_kv(CONFIG_FILE)
    changed = False
    if "PROVIDER" not in conf or not conf.get("PROVIDER"):
        conf["PROVIDER"] = "openai"
        changed = True
    if "BASE_URL" not in conf or not conf.get("BASE_URL"):
        conf["BASE_URL"] = "https://api.openai.com/v1"
        changed = True
    if "MODEL" not in conf or not conf.get("MODEL"):
        conf["MODEL"] = "gpt-4o-mini"
        changed = True
    if "TIMEOUT" not in conf or not conf.get("TIMEOUT"):
        conf["TIMEOUT"] = "60"
        changed = True
    if "OPENAI_API_KEY" not in conf:
        conf["OPENAI_API_KEY"] = ""
        changed = True
    if changed:
        write_kv(CONFIG_FILE, conf)
    return conf

def configure_model():
    conf = ensure_model_config()
    print("当前大模型配置:")
    for k in ["PROVIDER", "BASE_URL", "MODEL", "TIMEOUT", "OPENAI_API_KEY"]:
        print(f"{k}={conf.get(k, '')}")
    print("")
    print("回车跳过保持不变。")
    p = input(f"PROVIDER [{conf['PROVIDER']}]: ").strip() or conf["PROVIDER"]
    b = input(f"BASE_URL [{conf['BASE_URL']}]: ").strip() or conf["BASE_URL"]
    m = input(f"MODEL [{conf['MODEL']}]: ").strip() or conf["MODEL"]
    t = input(f"TIMEOUT [{conf['TIMEOUT']}]: ").strip() or conf["TIMEOUT"]
    k = input(f"OPENAI_API_KEY [{conf.get('OPENAI_API_KEY','')[:4]}***]: ").strip() or conf.get("OPENAI_API_KEY","")
    conf["PROVIDER"] = p
    conf["BASE_URL"] = b
    conf["MODEL"] = m
    conf["TIMEOUT"] = t
    conf["OPENAI_API_KEY"] = k
    write_kv(CONFIG_FILE, conf)
    print("已保存。")

def call_llm(conf, content):
    url = conf.get("BASE_URL", "").rstrip("/") + "/chat/completions"
    key = conf.get("OPENAI_API_KEY", "")
    model = conf.get("MODEL", "")
    to = int(conf.get("TIMEOUT", "60") or "60")
    data = {
        "model": model,
        "messages": [
            {"role":"system","content":"You are a parser. Read the provided skill.md and return a strict JSON that identifies configuration files and environment variables. Respond with JSON only."},
            {"role":"user","content":content}
        ],
        "temperature": 0
    }
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=to) as r:
            txt = r.read().decode()
            try:
                j = json.loads(txt)
            except Exception:
                j = {}
            c = ""
            if "choices" in j and j["choices"]:
                ch = j["choices"][0]
                if "message" in ch and "content" in ch["message"]:
                    c = ch["message"]["content"]
            if not c:
                return None
            start = c.find("{")
            end = c.rfind("}")
            if start != -1 and end != -1 and end >= start:
                s = c[start:end+1]
                try:
                    return json.loads(s)
                except Exception:
                    return None
            return None
    except urllib.error.HTTPError as e:
        return None
    except urllib.error.URLError as e:
        return None

def fallback_parse(md_text, md_path):
    env_vars = set()
    m1 = re.findall(r'`([A-Z][A-Z0-9_]{2,})`', md_text)
    m2 = re.findall(r'export\s+([A-Z][A-Z0-9_]{2,})\s*=', md_text)
    for x in m1 + m2:
        env_vars.add(x)
    files = []
    base_dir = os.path.dirname(md_path)
    cand = [".env","config.json","config.yaml","config.yml","config.txt","config","config.md"]
    found = []
    for root, _, fs in os.walk(base_dir):
        for f in fs:
            fl = f.lower()
            if fl in cand or any(fl.endswith(x) for x in cand):
                found.append(os.path.join(root, f))
    found.sort()
    targets = []
    for p in found:
        bn = os.path.basename(p)
        if "example" in bn.lower():
            tp = re.sub(r'[\.\-_]?example', '', bn, flags=re.IGNORECASE)
            if not tp or tp in [".",".txt"]:
                tp = "config.txt"
            targets.append({"source_examples":[p],"target_path":os.path.join(os.path.dirname(p), tp)})
        else:
            targets.append({"source_examples":[],"target_path":p})
    res = {"env_vars":sorted(env_vars),"files":targets}
    return res

def ensure_file_from_example(entry):
    target = entry.get("target_path","")
    exs = entry.get("source_examples",[])
    if not target:
        return False
    tdir = os.path.dirname(target)
    try:
        os.makedirs(tdir, exist_ok=True)
    except Exception:
        pass
    if os.path.exists(target):
        return True
    for e in exs:
        try:
            with open(e,"r") as f:
                cnt = f.read()
            with open(target,"w") as w:
                w.write(cnt)
            return True
        except Exception:
            continue
    try:
        with open(target,"w") as w:
            w.write("")
        return True
    except Exception:
        return False

def read_text(p):
    try:
        with open(p,"r") as f:
            return f.read()
    except Exception:
        return ""

def write_text(p, s):
    d = os.path.dirname(p)
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    if os.path.exists(p):
        if not os.access(p, os.W_OK):
            return False, "PERMISSION_DENIED"
    else:
        if not os.access(d, os.W_OK):
            return False, "PERMISSION_DENIED"
    try:
        with open(p,"w") as f:
            f.write(s)
        rb = read_text(p)
        if rb != s:
            return False, "VERIFY_FAILED"
        return True, ""
    except Exception as e:
        return False, str(e)

def scan_skills_dict():
    results = {}
    for tool_name, path_template in TOOL_SKILL_PATHS.items():
        tool_dir = os.path.expanduser(path_template)
        if not os.path.exists(tool_dir):
            continue
        tool_skills = []
        for item in os.listdir(tool_dir):
            skill_path = os.path.join(tool_dir, item)
            real_skill_path = os.path.realpath(skill_path)
            if os.path.isdir(real_skill_path):
                info = {"name": item, "path": real_skill_path, "md_files": [], "config_files": []}
                for root, _, files in os.walk(real_skill_path):
                    for f in files:
                        fl = f.lower()
                        if fl.endswith(".md"):
                            info["md_files"].append(os.path.join(root, f))
                        is_cfg = False
                        if "example" in fl:
                            is_cfg = True
                        elif fl in [".env","config.json","config.yaml","config.yml","config.txt","config.md","config"]:
                            is_cfg = True
                        if is_cfg:
                            info["config_files"].append(os.path.join(root, f))
                tool_skills.append(info)
        if tool_skills:
            results[tool_name] = tool_skills
    return results

def _select_preferred_target(config_files):
    if not config_files:
        return None
    priority = [".env","config.json","config.yaml","config.yml","config.txt","config","config.md"]
    def is_example(p):
        return "example" in os.path.basename(p).lower()
    non_examples = [p for p in config_files if not is_example(p)]
    examples = [p for p in config_files if is_example(p)]
    def sort_key(p):
        bn = os.path.basename(p).lower()
        for i, name in enumerate(priority):
            if bn == name or bn.endswith(name):
                return i
        return len(priority)
    if non_examples:
        non_examples.sort(key=sort_key)
        return os.path.realpath(os.path.expanduser(non_examples[0]))
    examples.sort(key=sort_key)
    ex = examples[0]
    bn = os.path.basename(ex)
    nb = re.sub(r'[\.\-_]?example','', bn, flags=re.IGNORECASE)
    if not nb or nb in [".",".txt"]:
        nb = "config.txt"
    return os.path.realpath(os.path.expanduser(os.path.join(os.path.dirname(ex), nb)))

def open_in_editor(filepath):
    import subprocess
    import shutil
    import curses
    
    # macOS 和大部分 Linux 都内置了 nano 或 vim
    editor = 'nano'
    if not shutil.which('nano'):
        if shutil.which('vim'):
            editor = 'vim'
        else:
            editor = 'vi'
            
    # 先重置 curses 的终端模式，确保子进程(编辑器)能接管标准输入输出
    curses.def_prog_mode()
    curses.endwin()
    
    try:
        # 刷新终端屏幕，清除可能残留的按键缓冲
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        
        # 只有在明确需要给小白提示时才停留，并且将输出写在另一个备用缓冲区
        # 避免污染 shell 历史
        print("\033[?1049h", end="") # Use alternative screen buffer if possible
        
        if editor == 'nano':
            print("\r\n正在启动 nano...")
            print("================================================================")
            print(" 【操作指南】")
            print("  1. 直接打字编辑内容")
            print("  2. 保存：按 Control + O，然后按 Enter 确认")
            print("  3. 退出：按 Control + X")
            print("================================================================")
        elif editor in ('vim', 'vi'):
            print(f"\r\n正在启动 {editor}...")
            print("================================================================")
            print(" 【操作指南】")
            print("  1. 按 i 进入编辑模式")
            print("  2. 编辑完成后，按 Esc 退出编辑模式")
            print("  3. 保存并退出：输入 :wq 然后按 Enter")
            print("================================================================")
            
        import time
        time.sleep(2)
        
        # 使用 os.system 替代 subprocess.run 以更好地兼容终端 TTY 接管
        os.system(f"{editor} '{filepath}'")
    finally:
        # 清除提示文字，避免退出后污染外层 shell 界面
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        # 编辑器退出后，恢复 curses 终端模式
        curses.reset_prog_mode()
        curses.doupdate()

def tui_view_skills(stdscr):
    import curses
    stdscr.clear()
    stdscr.addstr(0, 0, "正在扫描 Skill 目录...")
    stdscr.refresh()
    
    data = scan_skills_dict()
    flat_skills = []
    for tool, skills in data.items():
        for s in skills:
            # 仅在有配置文件时才加入列表
            if s.get("config_files"):
                target = _select_preferred_target(s.get("config_files", []))
                flat_skills.append({
                    "tool": tool,
                    "name": s["name"],
                    "path": s["path"],
                    "target_path": target,
                    "has_config": True,
                    "cfgs": s.get("config_files", [])
                })
            
    # 排序：按工具名、技能名
    flat_skills.sort(key=lambda x: (x["tool"], x["name"]))
    
    if not flat_skills:
        stdscr.clear()
        stdscr.addstr(0, 0, "未发现任何带有配置文件的 Skill。按任意键返回。")
        stdscr.refresh()
        stdscr.getch()
        return

    current_row = 0
    offset = 0

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        max_visible = h - 4
        
        stdscr.addstr(0, 0, "Skill 列表 - [上下箭头]移动 [Enter]编辑配置 [q]返回", curses.A_BOLD)
        stdscr.addstr(1, 0, "-" * (w - 1))
        
        if current_row < offset:
            offset = current_row
        if current_row >= offset + max_visible:
            offset = current_row - max_visible + 1

        for i in range(max_visible):
            idx = offset + i
            if idx >= len(flat_skills):
                break
            s = flat_skills[idx]
            display_text = f"[{s['tool']}] {s['name']}"
            
            if idx == current_row:
                stdscr.attron(curses.A_REVERSE)
                stdscr.addstr(i + 2, 0, display_text[:w-1])
                stdscr.attroff(curses.A_REVERSE)
            else:
                stdscr.addstr(i + 2, 0, display_text[:w-1])

        stdscr.addstr(h-1, 0, f"进度: {current_row+1}/{len(flat_skills)} | ENTER: 多行编辑配置文件"[:w-1])
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_UP and current_row > 0:
            current_row -= 1
        elif key == curses.KEY_DOWN and current_row < len(flat_skills) - 1:
            current_row += 1
        elif key in [10, 13]: # Enter
            s = flat_skills[current_row]
            target = s["target_path"]
            cfgs = s["cfgs"]
            
            # 确保文件创建
            if cfgs:
                entry = {"target_path": target, "source_examples": [p for p in cfgs if "example" in os.path.basename(p).lower()]}
                ensure_file_from_example(entry)
            else:
                try:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    if not os.path.exists(target):
                        with open(target, 'w') as f:
                            f.write("")
                except:
                    pass

            open_in_editor(target)
            
        elif key == ord('q'):
            break

def tui_view_llm(stdscr):
    import curses
    config = ensure_model_config()
    keys = ["PROVIDER", "BASE_URL", "MODEL", "TIMEOUT", "OPENAI_API_KEY"]
    current_row = 0

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        stdscr.addstr(0, 0, "大模型配置 - [上下箭头]移动 [Enter]修改 [q]返回", curses.A_BOLD)
        stdscr.addstr(1, 0, "-" * (w - 1))

        for idx, k in enumerate(keys):
            val = config.get(k, "")
            if k == "OPENAI_API_KEY" and val:
                val = val[:5] + "***" + val[-4:] if len(val) > 10 else "***"
            
            display_text = f"{k}: {val}"
            if idx == current_row:
                stdscr.attron(curses.A_REVERSE)
                stdscr.addstr(idx + 2, 2, display_text[:w-1])
                stdscr.attroff(curses.A_REVERSE)
            else:
                stdscr.addstr(idx + 2, 2, display_text[:w-1])

        stdscr.refresh()
        key = stdscr.getch()

        if key == curses.KEY_UP and current_row > 0:
            current_row -= 1
        elif key == curses.KEY_DOWN and current_row < len(keys) - 1:
            current_row += 1
        elif key in [10, 13]:
            k = keys[current_row]
            curses.echo()
            curses.curs_set(1)
            stdscr.addstr(len(keys) + 4, 0, f"输入 {k} 的新值 (留空保持不变): ")
            stdscr.refresh()
            new_val = stdscr.getstr(len(keys) + 5, 0).decode('utf-8').strip()
            curses.noecho()
            curses.curs_set(0)
            if new_val:
                config[k] = new_val
                write_kv(CONFIG_FILE, config)
        elif key == ord('q'):
            break

def tui_main(stdscr):
    import curses
    curses.curs_set(0)
    stdscr.keypad(True)
    menu_items = [
        "1. 浏览与编辑 Skill 配置 (多行编辑器)", 
        "2. 配置大模型 (LLM)", 
        "3. OpenClaw 配置与记忆备份/恢复",
        "4. 退出"
    ]
    current_row = 0

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        stdscr.addstr(0, 0, "统一 Agent 环境与配置中心 - TUI", curses.A_BOLD)
        stdscr.addstr(1, 0, "-" * (w - 1))

        for idx, item in enumerate(menu_items):
            if idx == current_row:
                stdscr.attron(curses.A_REVERSE)
                stdscr.addstr(idx + 2, 2, item)
                stdscr.attroff(curses.A_REVERSE)
            else:
                stdscr.addstr(idx + 2, 2, item)

        stdscr.refresh()
        key = stdscr.getch()

        if key == curses.KEY_UP and current_row > 0:
            current_row -= 1
        elif key == curses.KEY_DOWN and current_row < len(menu_items) - 1:
            current_row += 1
        elif key in [10, 13]:
            if current_row == 0:
                tui_view_skills(stdscr)
            elif current_row == 1:
                tui_view_llm(stdscr)
            elif current_row == 2:
                from backup_restore import tui_backup_restore
                tui_backup_restore(stdscr)
            elif current_row == 3:
                break
        elif key == ord('q'):
            break

def parse_skill_md():
    conf = ensure_model_config()
    path = input("输入 skill.md 文件路径或包含它的目录路径: ").strip()
    if not path:
        print("未输入路径。")
        return
    mp = path
    if os.path.isdir(mp):
        p1 = os.path.join(mp, "skill.md")
        p2 = os.path.join(mp, "SKILL.md")
        if os.path.exists(p1):
            mp = p1
        elif os.path.exists(p2):
            mp = p2
        else:
            print("目录下未找到 skill.md。")
            return
    if not os.path.exists(mp):
        print("文件不存在。")
        return
    txt = read_text(mp)
    print("尝试使用大模型解析...")
    payload = "Read the following skill.md and return JSON with keys: env_vars (array of strings), files (array of objects with fields: source_examples (array of strings), target_path (string)). Return JSON only.\n\n" + txt
    parsed = None
    if conf.get("OPENAI_API_KEY"):
        parsed = call_llm(conf, payload)
    if not parsed:
        print("大模型解析失败，使用本地启发式解析。")
        parsed = fallback_parse(txt, mp)
    print("")
    print("解析结果:")
    print(json.dumps(parsed, indent=2, ensure_ascii=False))
    print("")
    if parsed.get("files"):
        for idx, entry in enumerate(parsed["files"], 1):
            tp = entry.get("target_path","")
            print(f"[{idx}] 目标文件: {tp}")
            ok = ensure_file_from_example(entry)
            if not ok:
                print("无法创建或复制示例文件。")
                continue
            cur = read_text(tp)
            print(f"当前内容长度: {len(cur)}")
            ans = input("是否编辑并保存该文件内容? [y/N]: ").strip().lower()
            if ans == "y":
                print("请输入新内容，结束后输入单独一行仅包含: :wq")
                lines = []
                while True:
                    line = sys.stdin.readline()
                    if line is None:
                        break
                    if line.strip() == ":wq":
                        break
                    lines.append(line.rstrip("\n"))
                newc = "\n".join(lines)
                ok, err = write_text(tp, newc)
                if ok:
                    print("已保存。")
                else:
                    if err == "PERMISSION_DENIED":
                        print("写入失败：权限不足。可执行命令授予权限后重试。")
                        print(f"sudo chown $USER '{tp}' && sudo chmod u+w '{tp}'")
                    else:
                        print(f"写入失败：{err}")
    if parsed.get("env_vars"):
        print("")
        print("识别的环境变量:")
        for v in parsed["env_vars"]:
            print(v)

def parse_skill_md_cli(target_path):
    conf = ensure_model_config()
    mp = target_path
    if os.path.isdir(mp):
        p1 = os.path.join(mp, "skill.md")
        p2 = os.path.join(mp, "SKILL.md")
        if os.path.exists(p1):
            mp = p1
        elif os.path.exists(p2):
            mp = p2
        else:
            print(json.dumps({"error":"skill.md not found in directory"}, ensure_ascii=False))
            return 1
    if not os.path.exists(mp):
        print(json.dumps({"error":"file not found"}, ensure_ascii=False))
        return 1
    txt = read_text(mp)
    payload = "Read the following skill.md and return JSON with keys: env_vars (array of strings), files (array of objects with fields: source_examples (array of strings), target_path (string)). Return JSON only.\n\n" + txt
    parsed = None
    if conf.get("OPENAI_API_KEY"):
        parsed = call_llm(conf, payload)
    if not parsed:
        parsed = fallback_parse(txt, mp)
    # Ensure files exist if example only
    files_info = []
    for entry in parsed.get("files", []):
        tp = entry.get("target_path", "")
        ok = ensure_file_from_example(entry)
        files_info.append({"target_path": tp, "created": ok and os.path.exists(tp)})
    out = {
        "env_vars": parsed.get("env_vars", []),
        "files": files_info
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0

def main():
    if len(sys.argv) >= 2:
        cmd = sys.argv[1]
        if cmd == "parse":
            if len(sys.argv) < 3:
                print("用法: python3 main.py parse <skill.md 或目录路径>")
                return
            path = sys.argv[2]
            code = parse_skill_md_cli(path)
            try:
                sys.exit(code)
            except SystemExit:
                return
        elif cmd == "scan":
            data = scan_skills_dict()
            out = {}
            for t, arr in data.items():
                out[t] = []
                for s in arr:
                    target = _select_preferred_target(s.get("config_files", []))
                    out[t].append({
                        "name": s["name"],
                        "path": s["path"],
                        "target_path": target,
                        "has_config": bool(s.get("config_files")),
                    })
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return
        elif cmd == "edit":
            if len(sys.argv) < 4:
                print("用法: python3 main.py edit <ToolName> <SkillName>")
                return
            tool = sys.argv[2]
            name = sys.argv[3]
            data = scan_skills_dict()
            if tool not in data:
                print("未找到工具。")
                return
            hit = None
            for s in data[tool]:
                if s["name"] == name:
                    hit = s
                    break
            if not hit:
                print("未找到 Skill。")
                return
            cfgs = hit.get("config_files", [])
            if not cfgs:
                print("该 Skill 未发现配置文件。")
                return
            target = _select_preferred_target(cfgs)
            entry = {"target_path": target, "source_examples": [p for p in cfgs if "example" in os.path.basename(p).lower()]}
            ok = ensure_file_from_example(entry)
            if not ok:
                print("无法创建目标文件。")
                return
            cur = read_text(target)
            print(f"当前文件: {target}")
            print(f"当前内容长度: {len(cur)}")
            print("输入新内容，以 :wq 结束保存")
            lines = []
            while True:
                line = sys.stdin.readline()
                if line is None:
                    break
                if line.strip() == ":wq":
                    break
                lines.append(line.rstrip("\n"))
            newc = "\n".join(lines)
            ok, err = write_text(target, newc)
            if ok:
                print("已保存。")
            else:
                if err == "PERMISSION_DENIED":
                    print("权限不足，请执行命令后重试:")
                    print(f"sudo chown $USER '{target}' && sudo chmod u+w '{target}'")
                else:
                    print(f"写入失败: {err}")
            return
        elif cmd in ("config","config:show"):
            conf = ensure_model_config()
            out = dict(conf)
            if out.get("OPENAI_API_KEY"):
                v = out["OPENAI_API_KEY"]
                out["OPENAI_API_KEY"] = (v[:4] + "***") if len(v) > 4 else "***"
            print(json.dumps(out, indent=2))
            return
        elif cmd in ("configure",):
            configure_model()
            return
        elif cmd in ("-h","--help","help"):
            print("用法:")
            print("  python3 main.py                  # 进入交互式 TUI")
            print("  python3 main.py parse <path>     # 非交互解析 skill.md 或目录")
            print("  python3 main.py scan             # 扫描已知 Skill 目录并输出摘要")
            print("  python3 main.py edit <Tool> <Skill>  # 直接编辑某个 Skill 的目标配置文件")
            print("  python3 main.py configure        # 交互式配置大模型")
            print("  python3 main.py config           # 显示当前大模型配置")
            print("\n全局安装后可直接使用 agent-sync 命令替代 python3 main.py")
            return
    while True:
        import curses
        try:
            curses.wrapper(tui_main)
            break
        except Exception as e:
            print(f"TUI 启动失败: {e}")
            break

if __name__ == "__main__":
    main()
