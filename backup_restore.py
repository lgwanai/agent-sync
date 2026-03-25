import os
import zipfile
import tempfile
import shutil
import time
import glob
from pathlib import Path
import difflib

def get_claw_paths(app_type):
    if app_type == "qclaw":
        base_dir = os.path.expanduser("~/.qclaw")
        workspace_dir = os.path.join(base_dir, "workspace")
        agents_dir = os.path.join(base_dir, "agents")
        return base_dir, workspace_dir, agents_dir
    elif app_type == "workbuddy":
        base_dir = os.path.expanduser("~/.workbuddy")
        # Workbuddy 没有明确的 workspace/agents 区分，主要配置就在根目录
        workspace_dir = base_dir
        # 记忆在 ~/workbuddy (注意没有点)
        memory_dir = os.path.expanduser("~/workbuddy")
        return base_dir, workspace_dir, memory_dir
    else:
        base_dir = os.path.expanduser("~/.openclaw")
        workspace_dir = os.path.join(base_dir, "workspace")
        agents_dir = os.path.join(base_dir, "agents")
        return base_dir, workspace_dir, agents_dir

def is_skill_config_file(filename):
    fl = filename.lower()
    if "example" in fl:
        return True
    if fl in [".env", "config.json", "config.yaml", "config.yml", "config.txt", "config.md", "config"]:
        return True
    if fl in ["skill.md", "kill.md"]:
        return True
    return False

def export_data(app_type="openclaw"):
    base_dir, workspace_dir, extra_dir = get_claw_paths(app_type)
    
    if not os.path.exists(base_dir):
        print(f"{app_type} 目录 {base_dir} 不存在。")
        return None

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    zip_name = f"{app_type}_backup_{timestamp}.zip"
    zip_path = os.path.abspath(zip_name)

    files_to_zip = []

    if app_type == "workbuddy":
        # 1. 配置文件和关键目录
        if os.path.exists(base_dir):
            for item in ["BOOTSTRAP.md", "USER.md", "IDENTITY.md", "SOUL.md"]:
                p = os.path.join(base_dir, item)
                if os.path.exists(p):
                    # 压缩包内路径前缀加上 .workbuddy 以便恢复时区分
                    files_to_zip.append((p, os.path.join(".workbuddy", item)))
            
            for folder in ["inspiration", "skills"]:
                d = os.path.join(base_dir, folder)
                if os.path.exists(d):
                    for root, _, files in os.walk(d):
                        for file in files:
                            if folder == "skills" and not is_skill_config_file(file):
                                continue
                            full_path = os.path.join(root, file)
                            rel_path = os.path.relpath(full_path, base_dir)
                            files_to_zip.append((full_path, os.path.join(".workbuddy", rel_path)))

        # 2. 记忆记录 (~/workbuddy)
        if os.path.exists(extra_dir):
            for root, _, files in os.walk(extra_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, extra_dir)
                    # 压缩包内路径前缀加上 workbuddy (无点)
                    files_to_zip.append((full_path, os.path.join("workbuddy", rel_path)))
    else:
        # OpenClaw / QClaw 逻辑
        if os.path.exists(workspace_dir):
            for root, _, files in os.walk(workspace_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, base_dir)
                    if "skills" in rel_path.split(os.sep) and not is_skill_config_file(file):
                        continue
                    files_to_zip.append((full_path, rel_path))

        if os.path.exists(extra_dir): # agents_dir
            for root, _, files in os.walk(extra_dir):
                if os.path.basename(root) == "sessions":
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, base_dir)
                        files_to_zip.append((full_path, rel_path))

    if not files_to_zip:
        print("未找到任何需要备份的文件。")
        return None

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for full_path, rel_path in files_to_zip:
                zipf.write(full_path, rel_path)
        print(f"成功导出 {len(files_to_zip)} 个文件至 {zip_path}")
        return zip_path
    except Exception as e:
        print(f"导出失败: {e}")
        return None

def import_data(app_type="openclaw"):
    zips = glob.glob(f"{app_type}_backup_*.zip")
    if not zips:
        print(f"当前目录下未找到任何 {app_type}_backup_*.zip 文件。")
        return

    print("找到以下备份文件:")
    for i, z in enumerate(zips, 1):
        print(f"[{i}] {z}")
    
    sel = input("请选择要导入的备份序号 (回车取消): ").strip()
    if not sel.isdigit() or int(sel) < 1 or int(sel) > len(zips):
        return

    zip_file = zips[int(sel)-1]
    base_dir, _, extra_dir = get_claw_paths(app_type)

    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"正在解压 {zip_file}...")
        try:
            with zipfile.ZipFile(zip_file, 'r') as zipf:
                zipf.extractall(tmpdir)
        except Exception as e:
            print(f"解压失败: {e}")
            return

        overwrite_all = False
        missing_skills = set()
        
        for root, _, files in os.walk(tmpdir):
            for file in files:
                src_path = os.path.join(root, file)
                rel_path = os.path.relpath(src_path, tmpdir)
                
                skill_name = None
                target_skill_dir = None
                
                if app_type == "workbuddy":
                    # 解析前缀，还原真实路径
                    if rel_path.startswith(".workbuddy"):
                        real_rel = os.path.relpath(rel_path, ".workbuddy")
                        dest_path = os.path.join(base_dir, real_rel)
                        parts = real_rel.split(os.sep)
                        if len(parts) >= 2 and parts[0] == "skills":
                            skill_name = parts[1]
                            target_skill_dir = os.path.join(base_dir, "skills", skill_name)
                    elif rel_path.startswith("workbuddy"):
                        real_rel = os.path.relpath(rel_path, "workbuddy")
                        dest_path = os.path.join(extra_dir, real_rel)
                    else:
                        continue
                else:
                    dest_path = os.path.join(base_dir, rel_path)
                    parts = rel_path.split(os.sep)
                    if len(parts) >= 3 and parts[0] == "workspace" and parts[1] == "skills":
                        skill_name = parts[2]
                        target_skill_dir = os.path.join(base_dir, "workspace", "skills", skill_name)

                # 如果是 Skill 相关的配置，检查目标环境是否已经安装了该 Skill
                if skill_name and target_skill_dir:
                    if not os.path.exists(target_skill_dir):
                        if skill_name not in missing_skills:
                            print(f"\n[警告] 目标环境中未安装 Skill: {skill_name}")
                            print(f"请先安装该 Skill 后再进行备份恢复。已跳过恢复 {skill_name} 目录及其相关配置。")
                            missing_skills.add(skill_name)
                        continue

                if not os.path.exists(dest_path):
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.copy2(src_path, dest_path)
                    print(f"已恢复: {rel_path}")
                else:
                    if overwrite_all:
                        shutil.copy2(src_path, dest_path)
                        print(f"已覆盖: {rel_path}")
                        continue
                    
                    # 检查内容是否相同
                    with open(src_path, 'r', errors='replace') as sf, open(dest_path, 'r', errors='replace') as df:
                        src_content = sf.read()
                        dest_content = df.read()
                        
                    if src_content == dest_content:
                        print(f"跳过 (无变化): {rel_path}")
                        continue
                    
                    print(f"\n文件冲突: {rel_path}")
                    
                    # 允许对比的文件类型：常见的文本配置文件后缀
                    ext = os.path.splitext(dest_path)[1].lower()
                    can_diff = ext in [".md", ".json", ".txt", ".yaml", ".yml", ".env", ""] or is_skill_config_file(os.path.basename(dest_path))
                    prompt_str = "[o]覆盖 [d]对比差异 [s]跳过 [a]全部覆盖 [q]中止: " if can_diff else "[o]覆盖 [s]跳过 [a]全部覆盖 [q]中止: "

                    while True:
                        ans = input(prompt_str).strip().lower()
                        if ans == 'a':
                            overwrite_all = True
                            shutil.copy2(src_path, dest_path)
                            print(f"已覆盖: {rel_path}")
                            break
                        elif ans == 'o':
                            shutil.copy2(src_path, dest_path)
                            print(f"已覆盖: {rel_path}")
                            break
                        elif ans == 's':
                            print(f"已跳过: {rel_path}")
                            break
                        elif ans == 'q':
                            print("导入中止。")
                            return
                        elif ans == 'd':
                            if not can_diff:
                                print("当前文件格式不支持对比差异，请选择其他操作。")
                                continue
                            # 显示差异
                            diff = difflib.unified_diff(
                                dest_content.splitlines(),
                                src_content.splitlines(),
                                fromfile='当前系统文件',
                                tofile='备份文件',
                                lineterm=''
                            )
                            for line in diff:
                                if line.startswith('+') and not line.startswith('+++'):
                                    print(f"\033[92m{line}\033[0m")
                                elif line.startswith('-') and not line.startswith('---'):
                                    print(f"\033[91m{line}\033[0m")
                                elif line.startswith('@@'):
                                    print(f"\033[96m{line}\033[0m")
                                else:
                                    print(line)
                        else:
                            print("无效输入。")

    print("\n导入完成。")

def tui_backup_restore(stdscr):
    import curses
    curses.curs_set(0)
    menu_items = [
        "1. 导出 OpenClaw 配置与对话记忆 (备份为 Zip)",
        "2. 导入 OpenClaw 配置与对话记忆 (从 Zip 恢复)",
        "3. 导出 QClaw 配置与对话记忆 (备份为 Zip)",
        "4. 导入 QClaw 配置与对话记忆 (从 Zip 恢复)",
        "5. 导出 Workbuddy 配置与记忆 (备份为 Zip)",
        "6. 导入 Workbuddy 配置与记忆 (从 Zip 恢复)",
        "7. 返回上一级"
    ]
    current_row = 0

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        stdscr.addstr(0, 0, "Agent 数据备份与恢复", curses.A_BOLD)
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
                curses.def_prog_mode()
                curses.endwin()
                sys_stdout = os.system("clear")
                print("=== 导出 OpenClaw 数据 ===")
                export_data("openclaw")
                input("\n按回车键继续...")
                curses.reset_prog_mode()
                curses.doupdate()
            elif current_row == 1:
                curses.def_prog_mode()
                curses.endwin()
                sys_stdout = os.system("clear")
                print("=== 导入 OpenClaw 数据 ===")
                import_data("openclaw")
                input("\n按回车键继续...")
                curses.reset_prog_mode()
                curses.doupdate()
            elif current_row == 2:
                curses.def_prog_mode()
                curses.endwin()
                sys_stdout = os.system("clear")
                print("=== 导出 QClaw 数据 ===")
                export_data("qclaw")
                input("\n按回车键继续...")
                curses.reset_prog_mode()
                curses.doupdate()
            elif current_row == 3:
                curses.def_prog_mode()
                curses.endwin()
                sys_stdout = os.system("clear")
                print("=== 导入 QClaw 数据 ===")
                import_data("qclaw")
                input("\n按回车键继续...")
                curses.reset_prog_mode()
                curses.doupdate()
            elif current_row == 4:
                curses.def_prog_mode()
                curses.endwin()
                sys_stdout = os.system("clear")
                print("=== 导出 Workbuddy 数据 ===")
                export_data("workbuddy")
                input("\n按回车键继续...")
                curses.reset_prog_mode()
                curses.doupdate()
            elif current_row == 5:
                curses.def_prog_mode()
                curses.endwin()
                sys_stdout = os.system("clear")
                print("=== 导入 Workbuddy 数据 ===")
                import_data("workbuddy")
                input("\n按回车键继续...")
                curses.reset_prog_mode()
                curses.doupdate()
            elif current_row == 6:
                break
        elif key == ord('q'):
            break