"""
修复所有脚本中 PROJ_DIR 定义顺序问题
- 确保 PROJ_DIR 在使用之前定义
- download_data.py 缺少 PROJ_DIR，补上
"""
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
DEF = 'PROJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))'

def fix_file(fname):
    path = os.path.join(SCRIPTS_DIR, fname)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    lines = content.split("\n")
    new_lines = []
    changes = 0
    
    # 专门处理 download_data.py：没有 PROJ_DIR 定义
    if fname == "download_data.py" and "PROJ_DIR" in content and "PROJ_DIR =" not in content:
        for line in lines:
            new_lines.append(line)
            if "DATA_DIR = PROJ_DIR" in line:
                indent = line[:len(line) - len(line.lstrip())]
                new_lines.append("")
                new_lines.append(f'PROJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))')
                changes += 1
        result = "\n".join(new_lines)
        with open(path, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"  FIXED（补PROJ_DIR）: {fname}")
        return

    # 通用修复：交换 sys.path.insert 和 PROJ_DIR= 这两行的顺序
    for i in range(len(lines) - 1):
        if "sys.path.insert" in lines[i] and "PROJ_DIR" in lines[i]:
            if "PROJ_DIR = os.path.dirname" in lines[i+1]:
                # 交换两行
                lines[i], lines[i+1] = lines[i+1], lines[i]
                changes += 1
    
    result = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(result)
    
    if changes > 0:
        print(f"  FIXED（交换{nchanges}处）: {fname}")
    else:
        print(f"  OK: {fname}")

for fname in sorted(os.listdir(SCRIPTS_DIR)):
    if fname.endswith(".py") and fname != os.path.basename(__file__):
        try:
            fix_file(fname)
        except Exception as e:
            print(f"  ERROR {fname}: {e}")
