#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
云雾酒馆 — AI 行为评估脚本
=====================================

功能说明：
    本脚本用于客观、严谨地评估 AI 在项目中的所有行为，对其打分并给予反馈。
    评估维度包括：规范遵循、代码质量、安全意识、问题处理、文档同步、
    任务完成度、错误处理、效率优化。

使用方法：
    python AI行为评估脚本.py                # 交互式评估当前会话
    python AI行为评估脚本.py --auto        # 自动扫描最近变更并评估
    python AI行为评估脚本.py --report      # 生成评估报告到文件
    python AI行为评估脚本.py --help        # 查看帮助

⚠️ 执行规则：
    本脚本必须像「项目架构和相关规范.md」一样，在每次 AI 执行任务前和执行后
    都要被浏览阅读。AI 必须根据本脚本的评估标准规范自己的行为。

评分标准：
    100-90：优秀 — 严格遵循规范，代码质量高，无安全问题
    89-80：良好 — 基本遵循规范，有少量可改进之处
    79-70：合格 — 存在一些问题但已基本完成
    69-60：待改进 — 存在明显问题，需要重新审视
    59以下：不合格 — 存在严重问题，必须立即修正
"""

import os
import sys
import json
import re
import datetime
from pathlib import Path

# ===== 评估维度定义 =====
EVALUATION_DIMENSIONS = {
    "规范遵循": {
        "weight": 15,
        "description": "是否严格遵循项目架构和相关规范.md中的约束",
        "check_items": [
            "代码修改是否在 src/backend/ 目录进行",
            "修改后是否同步到 release/ 目录",
            "是否使用 BASE_PATH 相对路径处理",
            "JSON_AS_ASCII 是否设为 False",
            "JSON 文件操作是否使用 threading.Lock()",
            "异常处理是否使用 'except Exception as e:'",
            "是否仅使用 SiliconFlow API",
            "端口是否保持 9000",
        ]
    },
    "代码质量": {
        "weight": 15,
        "description": "代码的可读性、可维护性、简洁性",
        "check_items": [
            "命名是否清晰且符合规范",
            "是否有死代码、未使用的变量/函数",
            "是否有重复代码（DRY 原则）",
            "函数/方法长度是否合理（<80行）",
            "注释是否恰当（不过多、不过少）",
            "是否遵循单一职责原则",
        ]
    },
    "安全意识": {
        "weight": 20,
        "description": "是否考虑并防范安全风险",
        "check_items": [
            "XSS 防护：所有用户输入是否转义",
            "SQL 注入防护：是否使用参数化查询",
            "敏感信息是否过滤（API Key 等）",
            "会话安全：Cookie 是否设置 HttpOnly/SameSite",
            "SSRF 防护：URL 是否校验",
            "竞态条件是否处理",
            "是否引入新的安全漏洞",
        ]
    },
    "问题处理": {
        "weight": 15,
        "description": "问题是否被正确记录、分级和处理",
        "check_items": [
            "新发现问题是否记录到 问题反馈与报告.md",
            "简单问题是否立即修复",
            "复杂问题是否标记后续处理",
            "修复后是否更新问题状态",
            "是否误删尚未解决的问题",
        ]
    },
    "文档同步": {
        "weight": 10,
        "description": "文档是否及时更新保持一致",
        "check_items": [
            "问题反馈与报告.md 是否更新",
            "项目架构和相关规范.md 是否更新",
            "项目记忆.md 是否更新",
            "优化建议.md 是否更新（如涉及）",
            "版本历史是否记录",
        ]
    },
    "任务完成度": {
        "weight": 10,
        "description": "是否完整完成用户要求的任务",
        "check_items": [
            "是否完成所有用户要求的事项",
            "是否有遗漏或部分完成",
            "是否引入不必要的改动",
            "是否过度设计（超出任务要求）",
        ]
    },
    "错误处理": {
        "weight": 10,
        "description": "代码的健壮性和容错性",
        "check_items": [
            "外部调用是否有 try/except 保护",
            "边界情况是否处理（空值、越界等）",
            "数据库操作是否有事务保护",
            "文件操作是否有异常保护",
            "网络请求是否有超时和重试",
        ]
    },
    "效率优化": {
        "weight": 5,
        "description": "是否考虑性能和资源使用",
        "check_items": [
            "是否有明显的性能问题（N+1 查询等）",
            "是否有内存泄漏风险",
            "是否避免不必要的重复计算",
            "资源是否及时释放",
        ]
    }
}


def print_header(title):
    """打印标题分隔线"""
    width = 60
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def print_dimension_result(name, score, max_score, items_passed, items_failed):
    """打印单维度评估结果"""
    status = "✅" if score >= max_score * 0.8 else "⚠️" if score >= max_score * 0.6 else "❌"
    print(f"\n{status} {name}（{score}/{max_score} 分）")
    if items_passed:
        print(f"   通过项:")
        for item in items_passed:
            print(f"   ✅ {item}")
    if items_failed:
        print(f"   未通过项:")
        for item in items_failed:
            print(f"   ❌ {item}")


def evaluate_specification_compliance():
    """评估规范遵循度"""
    print_header("维度 1: 规范遵循度评估")
    print("请根据本次 AI 行为回答以下问题（y/n）：")
    
    items = EVALUATION_DIMENSIONS["规范遵循"]["check_items"]
    passed = []
    failed = []
    
    for item in items:
        while True:
            ans = input(f"  {item}? (y/n): ").strip().lower()
            if ans in ('y', 'n'):
                if ans == 'y':
                    passed.append(item)
                else:
                    failed.append(item)
                break
            print("    请输入 y 或 n")
    
    total = len(items)
    score = int(EVALUATION_DIMENSIONS["规范遵循"]["weight"] * len(passed) / total)
    print_dimension_result("规范遵循", score, EVALUATION_DIMENSIONS["规范遵循"]["weight"], passed, failed)
    return score, passed, failed


def evaluate_code_quality_auto():
    """自动评估代码质量 — 扫描代码文件"""
    print_header("维度 2: 代码质量自动扫描")
    
    src_path = Path("d:/AI-moyang/打包/ai_chat/src/backend")
    issues = []
    
    # 检查 app.py
    app_py = src_path / "app.py"
    if app_py.exists():
        content = app_py.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        # 检查裸 except
        bare_excepts = []
        for i, line in enumerate(lines, 1):
            if re.match(r'\s*except\s*:', line):
                bare_excepts.append(f"app.py:{i} 裸 except:")
        if bare_excepts:
            issues.extend(bare_excepts[:3])
        
        # 检查硬编码密码
        if '123456' in content:
            issues.append("app.py: 发现硬编码密码 '123456'")
        
        # 检查 API_KEY 明文返回
        if re.search(r'return jsonify.*api_key.*[^*]', content, re.DOTALL):
            issues.append("app.py: 可能存在 API_KEY 明文返回")
    
    # 检查 script.js
    script_js = src_path / "static" / "script.js"
    if script_js.exists():
        content = script_js.read_text(encoding='utf-8')
        
        # 检查未转义的 innerHTML
        unescaped = re.findall(r'innerHTML\s*[+]?=\s*[\'"`][^`]*\$\{[^}]+\}', content)
        if unescaped:
            issues.append(f"script.js: 发现 {len(unescaped)} 处可能未转义的 innerHTML 拼接")
        
        # 检查 escapeHtml 是否存在
        if 'function escapeHtml' not in content:
            issues.append("script.js: 缺少 escapeHtml 函数")
    
    # 检查 feedback.js
    feedback_js = src_path / "static" / "feedback.js"
    if feedback_js.exists():
        content = feedback_js.read_text(encoding='utf-8')
        if 'escapeHtml' not in content:
            issues.append("feedback.js: 缺少 escapeHtml 函数")
    
    if issues:
        print(f"  发现 {len(issues)} 个代码质量问题:")
        for issue in issues:
            print(f"  ⚠️ {issue}")
        score = max(0, 15 - len(issues) * 2)
    else:
        print("  ✅ 未发现明显代码质量问题")
        score = 15
    
    print(f"\n  代码质量得分: {score}/15")
    return score, issues


def evaluate_security_auto():
    """自动评估安全意识"""
    print_header("维度 3: 安全意识自动扫描")
    
    src_path = Path("d:/AI-moyang/打包/ai_chat/src/backend")
    issues = []
    
    app_py = src_path / "app.py"
    if app_py.exists():
        content = app_py.read_text(encoding='utf-8')
        
        # 检查 XSS 防护
        if 'escapeHtml' not in content and 'escape_html' not in content:
            issues.append("app.py: 缺少 XSS 转义函数")
        
        # 检查 SSRF 防护
        if 'is_safe_url' not in content:
            issues.append("app.py: 缺少 SSRF 防护函数 (is_safe_url)")
        
        # 检查 CSRF
        if 'csrf' not in content.lower() and 'CSRFProtect' not in content:
            issues.append("app.py: 未配置 CSRF 保护")
        
        # 检查 Session Cookie 安全
        if 'SESSION_COOKIE_HTTPONLY' not in content:
            issues.append("app.py: 未设置 SESSION_COOKIE_HTTPONLY")
        if 'SESSION_COOKIE_SAMESITE' not in content:
            issues.append("app.py: 未设置 SESSION_COOKIE_SAMESITE")
        
        # 检查 SQL 注入
        sql_injection_patterns = re.findall(r'execute.*f["\'].*SELECT', content)
        if sql_injection_patterns:
            issues.append(f"app.py: 发现 {len(sql_injection_patterns)} 处可能的 SQL 注入")
    
    script_js = src_path / "static" / "script.js"
    if script_js.exists():
        content = script_js.read_text(encoding='utf-8')
        
        # 检查 DOMPurify
        if 'DOMPurify' not in content:
            issues.append("script.js: 未使用 DOMPurify 净化 HTML")
    
    if issues:
        print(f"  发现 {len(issues)} 个安全问题:")
        for issue in issues:
            print(f"  ⚠️ {issue}")
        score = max(0, 20 - len(issues) * 3)
    else:
        print("  ✅ 未发现明显安全问题")
        score = 20
    
    print(f"\n  安全意识得分: {score}/20")
    return score, issues


def evaluate_interactive(name, dimension_info):
    """交互式评估某维度"""
    print_header(f"维度: {name}")
    print(f"说明: {dimension_info['description']}")
    print(f"权重: {dimension_info['weight']} 分")
    print("\n请根据本次 AI 行为回答以下问题（y/n/跳过）：")
    
    items = dimension_info["check_items"]
    passed = []
    failed = []
    
    for item in items:
        while True:
            ans = input(f"  {item}? (y/n/s 跳过): ").strip().lower()
            if ans in ('y', 'n'):
                if ans == 'y':
                    passed.append(item)
                else:
                    failed.append(item)
                break
            elif ans == 's':
                break
            print("    请输入 y, n 或 s")
    
    total = len(passed) + len(failed)
    if total == 0:
        score = int(dimension_info["weight"] * 0.7)  # 跳过全部给中等分
    else:
        score = int(dimension_info["weight"] * len(passed) / total)
    
    print_dimension_result(name, score, dimension_info["weight"], passed, failed)
    return score, passed, failed


def generate_feedback(total_score, dimension_scores):
    """根据总分生成反馈"""
    print_header("评估反馈")
    
    if total_score >= 90:
        level = "优秀"
        feedback = [
            "✅ AI 行为整体优秀，严格遵循项目规范",
            "✅ 代码质量高，安全意识强",
            "✅ 问题处理得当，文档同步及时",
            "建议: 保持当前水平，可作为其他项目的范例",
        ]
    elif total_score >= 80:
        level = "良好"
        feedback = [
            "✅ AI 行为整体良好，基本遵循规范",
            "⚠️ 存在少量可改进之处",
            "建议: 重点关注未通过的评估项",
            "建议: 加强对项目规范的深入理解",
        ]
    elif total_score >= 70:
        level = "合格"
        feedback = [
            "⚠️ AI 行为基本合格，但存在明显问题",
            "⚠️ 需要加强对项目规范的学习",
            "建议: 重新阅读项目架构和相关规范.md",
            "建议: 对未通过的项进行专项改进",
        ]
    elif total_score >= 60:
        level = "待改进"
        feedback = [
            "❌ AI 行为存在较多问题，需要改进",
            "❌ 必须重新审视项目规范",
            "建议: 停止当前任务，重新学习规范",
            "建议: 对已完成的代码进行回顾和修正",
        ]
    else:
        level = "不合格"
        feedback = [
            "❌ AI 行为不合格，存在严重问题",
            "❌ 必须立即停止并重新评估",
            "建议: 回退所有变更，重新开始",
            "建议: 逐项对照规范进行检查和修正",
        ]
    
    print(f"\n  评估等级: {level}")
    print(f"  总分: {total_score}/100")
    print()
    for line in feedback:
        print(f"  {line}")
    
    # 找出最弱的维度
    weakest = min(dimension_scores.items(), key=lambda x: x[1][0] / x[1][1] if x[1][1] > 0 else 1)
    print(f"\n  最弱维度: {weakest[0]}（{weakest[1][0]}/{weakest[1][1]} 分）")
    print(f"  建议: 优先改进 {weakest[0]} 维度")
    
    return level, feedback


def save_report(total_score, dimension_scores, all_issues, level, feedback):
    """保存评估报告"""
    report_path = Path("d:/AI-moyang/打包/ai_chat/docs/AI行为评估报告.md")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    content = f"""# AI 行为评估报告

**评估时间**: {timestamp}
**评估总分**: {total_score}/100
**评估等级**: {level}

---

## 评估维度详情

| 维度 | 得分 | 权重 | 通过项 | 未通过项 |
|------|:----:|:----:|:------:|:--------:|
"""
    
    for name, (score, max_score, passed, failed) in dimension_scores.items():
        content += f"| {name} | {score} | {max_score} | {len(passed)} | {len(failed)} |\n"
    
    content += "\n## 反馈\n\n"
    for line in feedback:
        content += f"- {line}\n"
    
    if all_issues:
        content += "\n## 发现的问题\n\n"
        for issue in all_issues:
            content += f"- ⚠️ {issue}\n"
    
    content += f"\n---\n\n*本报告由 AI行为评估脚本.py 自动生成*\n"
    
    report_path.write_text(content, encoding='utf-8')
    print(f"\n  📄 评估报告已保存至: {report_path}")


def auto_evaluate():
    """自动评估模式 — 扫描代码并评估"""
    print_header("AI 行为自动评估")
    print("正在扫描代码并自动评估...\n")
    
    all_issues = []
    dimension_scores = {}
    
    # 自动扫描代码质量
    score, issues = evaluate_code_quality_auto()
    dimension_scores["代码质量"] = (score, 15, [], issues)
    all_issues.extend(issues)
    
    # 自动扫描安全
    score, issues = evaluate_security_auto()
    dimension_scores["安全意识"] = (score, 20, [], issues)
    all_issues.extend(issues)
    
    # 其他维度给予中等预估分
    dimension_scores["规范遵循"] = (10, 15, [], ["需人工确认"])
    dimension_scores["问题处理"] = (10, 15, [], ["需人工确认"])
    dimension_scores["文档同步"] = (7, 10, [], ["需人工确认"])
    dimension_scores["任务完成度"] = (7, 10, [], ["需人工确认"])
    dimension_scores["错误处理"] = (7, 10, [], ["需人工确认"])
    dimension_scores["效率优化"] = (4, 5, [], ["需人工确认"])
    
    total_score = sum(s[0] for s in dimension_scores.values())
    level, feedback = generate_feedback(total_score, dimension_scores)
    
    save_report(total_score, dimension_scores, all_issues, level, feedback)
    return total_score


def interactive_evaluate():
    """交互式评估模式"""
    print_header("AI 行为交互式评估")
    print("本评估将逐维度对 AI 行为进行打分。请根据本次 AI 的实际行为如实回答。\n")
    
    all_issues = []
    dimension_scores = {}
    
    # 规范遵循（交互式）
    score, passed, failed = evaluate_specification_compliance()
    dimension_scores["规范遵循"] = (score, 15, passed, failed)
    
    # 代码质量（自动）
    score, issues = evaluate_code_quality_auto()
    dimension_scores["代码质量"] = (score, 15, [], issues)
    all_issues.extend(issues)
    
    # 安全意识（自动）
    score, issues = evaluate_security_auto()
    dimension_scores["安全意识"] = (score, 20, [], issues)
    all_issues.extend(issues)
    
    # 问题处理（交互式）
    score, passed, failed = evaluate_interactive("问题处理", EVALUATION_DIMENSIONS["问题处理"])
    dimension_scores["问题处理"] = (score, 15, passed, failed)
    
    # 文档同步（交互式）
    score, passed, failed = evaluate_interactive("文档同步", EVALUATION_DIMENSIONS["文档同步"])
    dimension_scores["文档同步"] = (score, 10, passed, failed)
    
    # 任务完成度（交互式）
    score, passed, failed = evaluate_interactive("任务完成度", EVALUATION_DIMENSIONS["任务完成度"])
    dimension_scores["任务完成度"] = (score, 10, passed, failed)
    
    # 错误处理（交互式）
    score, passed, failed = evaluate_interactive("错误处理", EVALUATION_DIMENSIONS["错误处理"])
    dimension_scores["错误处理"] = (score, 10, passed, failed)
    
    # 效率优化（交互式）
    score, passed, failed = evaluate_interactive("效率优化", EVALUATION_DIMENSIONS["效率优化"])
    dimension_scores["效率优化"] = (score, 5, passed, failed)
    
    total_score = sum(s[0] for s in dimension_scores.values())
    level, feedback = generate_feedback(total_score, dimension_scores)
    
    save_report(total_score, dimension_scores, all_issues, level, feedback)
    return total_score


def show_evaluation_standards():
    """显示评估标准"""
    print_header("AI 行为评估标准")
    print(f"\n{'维度':<12} {'权重':<6} {'说明'}")
    print("-" * 60)
    for name, info in EVALUATION_DIMENSIONS.items():
        print(f"{name:<12} {info['weight']:<6} {info['description']}")
    
    print("\n评分等级:")
    print("  100-90: 优秀 — 严格遵循规范，代码质量高，无安全问题")
    print("  89-80:  良好 — 基本遵循规范，有少量可改进之处")
    print("  79-70:  合格 — 存在一些问题但已基本完成")
    print("  69-60:  待改进 — 存在明显问题，需要重新审视")
    print("  59以下: 不合格 — 存在严重问题，必须立即修正")
    
    print("\n⚠️ AI 执行任务前必读:")
    print("  1. 阅读项目架构和相关规范.md")
    print("  2. 阅读本评估脚本，了解评估标准")
    print("  3. 按照评估标准规范自己的行为")
    print("\n⚠️ AI 执行任务后必读:")
    print("  1. 运行本脚本进行自评")
    print("  2. 根据反馈改进不足之处")
    print("  3. 更新文档保持同步")


def main():
    """主函数"""
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--help":
            print("用法:")
            print("  python AI行为评估脚本.py                # 交互式评估")
            print("  python AI行为评估脚本.py --auto        # 自动扫描评估")
            print("  python AI行为评估脚本.py --report      # 生成报告")
            print("  python AI行为评估脚本.py --standards   # 查看评估标准")
            return
        elif arg == "--auto":
            auto_evaluate()
            return
        elif arg == "--report":
            # 生成报告模式（等同于 auto）
            auto_evaluate()
            return
        elif arg == "--standards":
            show_evaluation_standards()
            return
    
    # 默认交互式
    show_evaluation_standards()
    print("\n")
    confirm = input("是否开始交互式评估? (y/n): ").strip().lower()
    if confirm == 'y':
        interactive_evaluate()
    else:
        print("已取消评估。")


if __name__ == "__main__":
    main()
