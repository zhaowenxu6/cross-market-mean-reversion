"""
一键运行完整回测Pipeline
从数据下载到报告生成，按顺序执行全部9个脚本

用法:
  python run_all.py                  # 完整运行（下载+处理+建模+回测+报告）
  python run_all.py --skip-download  # 跳过数据下载（已下载过数据时使用）

每个步骤失败时自动终止并打印错误信息
"""
import sys, os, subprocess, time

PROJ_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(PROJ_DIR, "scripts")

STEPS = [
    ("1/9", "下载原始数据",         "download_data.py",       False),
    ("2/9", "数据清洗与对齐",       "preprocess_data.py",     True),
    ("3/9", "因子模型与质量检验",   "factor_model.py",        True),
    ("4/9", "z-score信号生成",      "generate_signals.py",    True),
    ("5/9", "组合构建与风控",       "build_portfolio.py",     True),
    ("6/9", "回测引擎与成本建模",   "backtest.py",            True),
    ("7/9", "风控可视化图表",       "risk_dashboard.py",      True),
    ("8/9", "样本交易可视化",       "visualize_samples.py",   True),
    ("9/9", "生成最终Word报告",     "generate_docx_report.py",True),
]

def print_header(msg):
    width = 60
    print()
    print("=" * width)
    print(f"  {msg}")
    print("=" * width)
    print()

def run_step(step_num, label, script, required):
    print_header(f"Step {step_num} — {label}")
    start = time.time()
    script_path = os.path.join(SCRIPTS_DIR, script)
    
    if not os.path.exists(script_path):
        print(f"  [ERROR] 脚本不存在: {script_path}")
        if required:
            sys.exit(1)
        else:
            print("  [SKIP] 非必需步骤，跳过")
            return
    
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=PROJ_DIR,
        capture_output=False,
        text=True,
    )
    
    elapsed = time.time() - start
    
    if result.returncode == 0:
        print(f"  [DONE] 耗时 {elapsed:.1f}秒，返回码 {result.returncode}")
    else:
        print(f"  [FAIL] 耗时 {elapsed:.1f}秒，返回码 {result.returncode}")
        if required:
            print(f"\n  [ERROR] {script} 执行失败，Pipeline终止")
            print(f"  请检查错误信息后重试")
            sys.exit(1)
        else:
            print("  [SKIP] 非必需步骤，跳过")

if __name__ == "__main__":
    skip_download = "--skip-download" in sys.argv
    
    print()
    print("=" * 60)
    print("  跨市场特质均值回归策略 — 完整Pipeline")
    print("=" * 60)
    print(f"  项目目录: {PROJ_DIR}")
    print(f"  Python:   {sys.executable}")
    if skip_download:
        print(f"  模式:     跳过数据下载")
    print(f"  开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    overall_start = time.time()
    
    for step_num, label, script, required in STEPS:
        if skip_download and script == "download_data.py":
            print_header(f"Step {step_num} — {label}")
            print("  [SKIP] 已指定 --skip-download，跳过")
            continue
        # 报告已存在时自动跳过，--force-report 可强制重新生成
        if script == "generate_docx_report.py":
            report_path = os.path.join(PROJ_DIR, "output", "reports", "strategy_report.docx")
            if os.path.exists(report_path) and "--force-report" not in sys.argv:
                print_header(f"Step {step_num} — {label}")
                print(f"  [SKIP] 报告已存在: {os.path.basename(report_path)}")
                print(f"  如需重新生成请加 --force-report 参数")
                continue
        run_step(f"{step_num}/{len(STEPS)}", label, script, required)
    
    total_elapsed = time.time() - overall_start
    print()
    print("=" * 60)
    print(f"  Pipeline 完成！总耗时 {total_elapsed:.1f}秒")
    print(f"  最终报告: {os.path.join(PROJ_DIR, 'output', 'reports', 'strategy_report.docx')}")
    print("=" * 60)
    print()
