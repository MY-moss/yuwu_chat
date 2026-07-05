#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
云雾酒馆 — AI 行为评估脚本
=====================================

功能说明：
    本脚本用于客观、严谨地评估 AI 在项目中的所有行为，对其打分并给予反馈。
    评估维度扩展为 11 个：规范遵循、代码质量、安全意识、问题处理、文档同步、
    任务完成度、错误处理、效率优化、版本控制、规范阅读、记忆更新。

使用方法：
    python AI行为评估脚本.py                # 交互式评估当前会话
    python AI行为评估脚本.py --auto        # 自动扫描最近变更并评估
    python AI行为评估脚本.py --help        # 查看帮助

⚠️ 执行规则：
    本脚本必须像「项目架构和相关规范.md」一样，在每次 AI 执行任务前和执行后
    都要被浏览阅读。AI 必须根据本脚本的评估标准规范自己的行为。
    **不可修改**: 不可对`docs/AI行为评估脚本.py` 进行规则上的修改，除非是代码有问题或者技术有问题,或者已经通过管理员的审核后批准，或者管理员要求这么做

评分标准：
    100-95：优秀 — 严格遵循规范，代码质量高，无安全问题
    94-85：良好 — 基本遵循规范，有少量可改进之处
    84-75：合格 — 存在一些问题但已基本完成
    74-60：待改进 — 存在明显问题，需要重新审视
    59以下：不合格 — 存在严重问题，必须立即修正
"""

import os
import sys
import re
import datetime
import time
import subprocess
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
            "AI工作流指南.md 是否更新（如涉及文档体系）",
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
    },
    "版本控制": {
        "weight": 10,
        "description": "是否及时将更新提交并上传到 GitHub",
        "check_items": [
            "是否及时将更新上传到 GitHub",
            "commit 信息是否简洁明确",
            "是否只提交了预期文件",
            "是否避免提交敏感信息（密钥、密码）",
        ]
    },
    "规范阅读": {
        "weight": 5,
        "description": "当轮是否阅读项目架构和相关规范",
        "check_items": [
            "当轮是否阅读项目架构和相关规范",
        ]
    },
    "记忆更新": {
        "weight": 5,
        "description": "当轮是否更新项目架构和相关规范.md的待办与风险章节",
        "check_items": [
            "当轮是否更新待办优先级与已知风险",
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
        
        # 检查硬编码密码（排除配置中的默认管理员密码）
        password_contexts = [(i, l) for i, l in enumerate(lines, 1) if '123456' in l and 'admin' not in l.lower() and 'password' not in l.lower()]
        if password_contexts:
            for lineno, line in password_contexts[:3]:
                issues.append(f"app.py:{lineno} 发现硬编码密码 '123456'")
        
        # 检查 API_KEY 明文返回
        api_key_returns = re.findall(r'["\']api_key["\']\s*:\s*["\'][^*]', content)
        if api_key_returns:
            issues.append(f"app.py: 发现 {len(api_key_returns)} 处可能的 API_KEY 明文返回（非脱敏值）")
    
    # 检查 script.js
    script_js = src_path / "static" / "script.js"
    if script_js.exists():
        content = script_js.read_text(encoding='utf-8')
        
        # 检查 escapeHtml 是否存在
        has_escape_html = bool(re.search(r'(?:function|const|var|let)\s+escapeHtml\b', content))
        
        # 检查未转义的 innerHTML
        # 策略：有 escapeHtml 时检查常见可疑模式；无 escapeHtml 时标记所有 innerHTML
        if not has_escape_html:
            innerhtml_count = len(re.findall(r'innerHTML\s*[+]?=\s*', content))
            if innerhtml_count > 0:
                issues.append(f"script.js: {innerhtml_count} 处 innerHTML 赋值但无 escapeHtml 函数")
        else:
            # 检查直接变量赋值（不经过安全函数包装的常见变量名）
            unsafe_vars = [
                'html', 'content', 'text', 'data', 'result', 'full', 'json',
                'msg', 'reply', 'error', 'info', 'body', 'desc', 'name', 'value',
                'markdown', 'clean', 'breakdown', 'htmlContent', 'items', 'entries', 'listHtml'
            ]
            var_pattern = '|'.join(unsafe_vars)
            # 逐行扫描给出具体位置
            lines = content.split('\n')
            found_lines = []
            for i, line in enumerate(lines, 1):
                if not re.search(r'innerHTML\s*=\s*', line):
                    continue
                if re.search(r'(renderMarkdown|escapeHtml|DOMPurify)\s*\(', line):
                    continue
                m = re.search(r'innerHTML\s*=\s*(' + var_pattern + r')\b', line)
                if m:
                    found_lines.append(f"script.js:{i} ({m.group(1)})")
            if found_lines:
                detail = '; '.join(found_lines[:6])
                issues.append(f"script.js: {len(found_lines)} 处可能未转义的 innerHTML 赋值（{detail}）")
    
    # 检查 feedback.js
    feedback_js = src_path / "static" / "feedback.js"
    if feedback_js.exists():
        content = feedback_js.read_text(encoding='utf-8')
        if not re.search(r'(?:function|const|var|let)\s+escapeHtml\b', content):
            issues.append("feedback.js: 缺少 escapeHtml 函数")
    
    # 检查 Python 中的 bare except 用法（排除 app.py，已在上面逐行检查）
    py_dir = Path("d:/AI-moyang/打包/ai_chat/src/backend")
    if py_dir.exists():
        for py_file in py_dir.rglob("*.py"):
            if py_file.name == "app.py":
                continue
            content = py_file.read_text(encoding='utf-8', errors='ignore')
            bare_excepts = re.findall(r'^\s*except\s*:', content, re.MULTILINE)
            if bare_excepts:
                issues.append(f"{py_file.name}: 存在 {len(bare_excepts)} 处 bare except")
    
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
        
        # 检查 XSS 防护（支持 escapeHtml 和 escape_html）
        if 'def escape_html' not in content and 'def escapeHtml' not in content:
            issues.append("app.py: 缺少 XSS 转义函数")
        
        # 检查 SSRF 防护
        if 'is_safe_url' not in content:
            issues.append("app.py: 缺少 SSRF 防护函数 (is_safe_url)")
        
        # 检查 CSRF
        if 'csrf_protect' not in content.lower() and 'csrfprotect' not in content.lower():
            issues.append("app.py: 未配置 CSRF 保护")
        
        # 检查 Session Cookie 安全（需同时存在且值为安全值）
        if not re.search(r"SESSION_COOKIE_HTTPONLY[^=]*=\s*True", content):
            issues.append("app.py: SESSION_COOKIE_HTTPONLY 未设为 True")
        if not re.search(r"SESSION_COOKIE_SAMESITE[^=]*=\s*['\"]Lax['\"]", content):
            if not re.search(r"SESSION_COOKIE_SAMESITE[^=]*=\s*['\"]Strict['\"]", content):
                issues.append("app.py: SESSION_COOKIE_SAMESITE 未设为 Lax 或 Strict")
        
        # 检查 SQL 注入（参数化查询是安全的，f-string 拼接危险）
        sql_injection_patterns = re.findall(r'(?:execute|executemany)\(.*f["\']', content)
        if sql_injection_patterns:
            for s in sql_injection_patterns[:3]:
                issues.append(f"app.py: 发现可能的 SQL 注入（f-string拼接）")
        
        # 检查 SECRET_KEY 是否来自环境变量（安全）还是硬编码（可能不安全）
        secret_env = re.search(r'(?:os\.environ\.get|os\.getenv)\s*\(\s*["\']SECRET_KEY', content)
        if not secret_env:
            secret_hardcoded = re.search(r'SECRET_KEY\s*=\s*["\'](.+?)["\']', content, re.IGNORECASE)
            if secret_hardcoded:
                key = secret_hardcoded.group(1)
                weak_keys = {'secret', 'changeme', 'password', '123456', 'key'}
                if key.lower() in weak_keys or len(key) < 16:
                    issues.append("app.py: SECRET_KEY 强度不足（长度<16或使用了弱密钥）")
    
    # 检查 eval() 和 document.write() 危险用法
    js_dir = Path("d:/AI-moyang/打包/ai_chat/src/backend/static")
    if js_dir.exists():
        for js_file in js_dir.glob("*.js"):
            content = js_file.read_text(encoding='utf-8', errors='ignore')
            if 'eval(' in content:
                issues.append(f"{js_file.name}: 使用了 eval()")
            if 'document.write(' in content:
                issues.append(f"{js_file.name}: 使用了 document.write()")
            if 'console.log(' in content:
                issues.append(f"{js_file.name}: 存在 console.log（生产环境应移除）")
    
    script_js = src_path / "static" / "script.js"
    if script_js.exists():
        content = script_js.read_text(encoding='utf-8')
        
        # 检查 DOMPurify（有回退到 escapeHtml 也是可以接受的）
        if 'DOMPurify' not in content and 'escapeHtml' not in content:
            issues.append("script.js: 未使用 DOMPurify 或 escapeHtml 净化 HTML")
    
    if issues:
        print(f"  发现 {len(issues)} 个安全问题:")
        for issue in issues:
            print(f"  ⚠️ {issue}")
        severity = sum(
            5 if 'SQL' in i or 'XSS' in i or 'eval' in i or '未转义' in i or '缺少' in i else
            2 if 'console.log' in i or 'console' in i else 3
            for i in issues
        )
        score = max(0, 20 - severity)
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
                failed.append(f"{item} [跳过]")
                break
            print("    请输入 y, n 或 s")
    
    total = len(passed) + len(failed)
    if total == 0:
        score = 0  # 跳过全部给0分
    else:
        score = int(dimension_info["weight"] * len(passed) / total)
    
    print_dimension_result(name, score, dimension_info["weight"], passed, failed)
    return score, passed, failed


def generate_feedback(total_score, dimension_scores):
    """根据总分生成反馈"""
    print_header("评估反馈")
    
    if total_score >= 95:
        level = "优秀"
        feedback = [
            "✅ AI 行为整体优秀，严格遵循项目规范",
            "✅ 代码质量高，安全意识强",
            "✅ 问题处理得当，文档同步及时",
            "建议: 保持当前水平，可作为其他项目的范例",
        ]
    elif total_score >= 85:
        level = "良好"
        feedback = [
            "✅ AI 行为整体良好，基本遵循规范",
            "⚠️ 存在少量可改进之处",
            "建议: 重点关注未通过的评估项",
            "建议: 加强对项目规范的深入理解",
        ]
    elif total_score >= 75:
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
    
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(content, encoding='utf-8')
        print(f"\n  📄 评估报告已保存至: {report_path}")
    except Exception as e:
        print(f"\n  ⚠️ 评估报告保存失败: {e}")


def evaluate_specification_compliance_auto():
    """自动评估规范遵循度"""
    print_header("维度 1: 规范遵循度自动扫描")
    
    src_path = Path("d:/AI-moyang/打包/ai_chat/src/backend")
    release_path = Path("d:/AI-moyang/打包/ai_chat/release")
    issues = []
    passed = []
    
    # 检查 BASE_PATH 使用
    app_py = src_path / "app.py"
    if app_py.exists():
        content = app_py.read_text(encoding='utf-8')
        if 'BASE_PATH' in content and 'os.path.dirname' in content:
            passed.append("使用 BASE_PATH 相对路径处理")
        else:
            issues.append("未使用 BASE_PATH 相对路径处理")
        
        if "JSON_AS_ASCII" in content and "False" in content:
            passed.append("JSON_AS_ASCII 设为 False")
        else:
            issues.append("JSON_AS_ASCII 未设为 False")
        
        if 'threading.Lock()' in content:
            passed.append("JSON 文件操作使用 threading.Lock()")
        else:
            issues.append("JSON 文件操作未使用 threading.Lock()")
        
        if re.search(r'app\.run\s*\([^)]*port\s*=\s*9000', content):
            passed.append("端口保持 9000")
        else:
            issues.append("app.run 未使用 port=9000")
    
    # 检查文件同步
    sync_files = [
        'app.py',
        'static/script.js', 'static/style.css', 'static/feedback.js',
        'static/creative_showcase.html', 'static/feedback.css',
        'templates/index.html', 'templates/feedback.html',
        'templates/dashboard.html', 'templates/spectate.html',
    ]
    for f in sync_files:
        src_file = src_path / f
        rel_file = release_path / f
        if src_file.exists() and rel_file.exists():
            passed.append(f"{f} 已同步到 release/")
        elif src_file.exists() and not rel_file.exists():
            issues.append(f"{f} 未同步到 release/")
    
    if issues:
        print(f"  发现 {len(issues)} 个规范遵循问题:")
        for issue in issues:
            print(f"  ⚠️ {issue}")
        score = max(0, 15 - len(issues) * 2)
    else:
        print("  ✅ 未发现规范遵循问题")
        score = 15
    
    print(f"\n  规范遵循得分: {score}/15")
    return score, passed, issues


def evaluate_error_handling_auto():
    """自动评估错误处理"""
    print_header("维度 7: 错误处理自动扫描")
    
    src_path = Path("d:/AI-moyang/打包/ai_chat/src/backend")
    issues = []
    
    # 检查 app.py 的 try/except
    app_py = src_path / "app.py"
    if app_py.exists():
        content = app_py.read_text(encoding='utf-8')
        
        # 统计 try/except 数量
        try_count = content.count('try:')
        
        if try_count < 20:
            issues.append(f"app.py: try/except 使用较少 ({try_count}处，建议≥20)")
        
        # 检查关键函数是否有异常保护
        critical_functions = ['chat', 'call_ai', 'start_rpg', 'rpg_act', 'load_agents', 'load_worlds']
        for func in critical_functions:
            pattern = f'def {func}\\(.*?\\):'
            match = re.search(pattern, content, re.DOTALL)
            if match:
                start = match.end()
                end = content.find('\ndef ', start)
                if end == -1:
                    end = len(content)
                func_content = content[start:end]
                if 'try:' not in func_content:
                    issues.append(f"app.py: {func} 函数缺少 try/except 保护")
    
    # 检查 script.js 的 try/catch
    script_js = src_path / "static" / "script.js"
    if script_js.exists():
        content = script_js.read_text(encoding='utf-8')
        catch_count = content.count('catch')
        if catch_count < 25:
            issues.append(f"script.js: try/catch 使用较少 ({catch_count}处，建议≥25)")
    
    if issues:
        print(f"  发现 {len(issues)} 个错误处理问题:")
        for issue in issues:
            print(f"  ⚠️ {issue}")
        score = max(0, 10 - len(issues) * 2)
    else:
        print("  ✅ 未发现错误处理问题")
        score = 10
    
    print(f"\n  错误处理得分: {score}/10")
    return score, issues


def evaluate_document_sync_auto():
    """自动评估文档同步"""
    print_header("维度 5: 文档同步自动检查")
    
    docs_path = Path("d:/AI-moyang/打包/ai_chat/docs")
    issues = []
    passed = []
    
    required_docs = ['项目架构和相关规范.md', '问题反馈与报告.md', 'AI工作流指南.md', '优化建议.md', '已修复历史问题.md']
    for doc in required_docs:
        doc_file = docs_path / doc
        if doc_file.exists():
            passed.append(f"{doc} 存在")
        else:
            issues.append(f"{doc} 缺失")
    
    # 检查文档更新时间（最近3天，活跃项目应更频繁）
    three_days_ago = time.time() - 3 * 24 * 3600
    for doc in required_docs:
        doc_file = docs_path / doc
        if doc_file.exists():
            mtime = doc_file.stat().st_mtime
            if mtime >= three_days_ago:
                passed.append(f"{doc} 最近3天已更新")
            else:
                issues.append(f"{doc} 超过3天未更新")
    
    if issues:
        print(f"  发现 {len(issues)} 个文档同步问题:")
        for issue in issues:
            print(f"  ⚠️ {issue}")
        score = max(0, 10 - len(issues) * 2)
    else:
        print("  ✅ 文档同步良好")
        score = 10
    
    print(f"\n  文档同步得分: {score}/10")
    return score, passed, issues


def evaluate_efficiency_auto():
    """自动评估效率优化"""
    print_header("维度 8: 效率优化自动扫描")
    
    src_path = Path("d:/AI-moyang/打包/ai_chat/src/backend")
    issues = []
    
    # 检查 app.py 的重复查询
    app_py = src_path / "app.py"
    if app_py.exists():
        content = app_py.read_text(encoding='utf-8')
        
        # 检查重复导入
        import_lines = [l for l in content.split('\n') if l.startswith('import ') or l.startswith('from ')]
        import_counts = {}
        for line in import_lines:
            key = line.strip()
            import_counts[key] = import_counts.get(key, 0) + 1
        duplicate_imports = [k for k, v in import_counts.items() if v > 1]
        if duplicate_imports:
            issues.append(f"app.py: 存在重复导入 ({', '.join(duplicate_imports[:3])})")
    
    if issues:
        print(f"  发现 {len(issues)} 个效率优化问题:")
        for issue in issues:
            print(f"  ⚠️ {issue}")
        score = max(0, 5 - len(issues) * 1)
    else:
        print("  ✅ 未发现明显效率问题")
        score = 5
    
    print(f"\n  效率优化得分: {score}/5")
    return score, issues


def evaluate_version_control_auto():
    """自动评估版本控制 — 检查 git 提交记录"""
    print_header("维度 9: 版本控制自动扫描")
    
    project_root = Path("d:/AI-moyang/打包/ai_chat")
    git_exe = "D:/Github/Git1/Git/bin/git.exe"
    
    if not os.path.exists(git_exe):
        git_exe = "git"
    
    issues = []
    passed = []
    
    try:
        result = subprocess.run(
            [git_exe, "log", "--oneline", "-10"],
            capture_output=True, text=True, cwd=project_root, timeout=15, encoding='utf-8', errors='replace'
        )
        if result.returncode == 0 and result.stdout and result.stdout.strip():
            commits = result.stdout.strip().split('\n')
            commit_count = len(commits)
            passed.append(f"存在 {commit_count} 条最近提交记录")
            
            # 检查提交信息质量
            for c in commits[:3]:
                parts = c.split(' ', 1)
                if len(parts) < 2 or len(parts[1].strip()) < 5:
                    issues.append("存在过短的 commit 信息")
                    break
            
            # 检查是否有远程仓库且已同步
            remote_result = subprocess.run(
                [git_exe, "remote", "-v"],
                capture_output=True, text=True, cwd=project_root, timeout=5, encoding='utf-8', errors='replace'
            )
            if remote_result.returncode == 0 and remote_result.stdout.strip():
                passed.append("已配置远程仓库")
            else:
                issues.append("未找到远程仓库配置")
        else:
            issues.append("未找到 git 提交记录")
    except Exception as e:
        issues.append(f"无法检查 git 状态: {e}")
    
    if issues:
        print(f"  发现 {len(issues)} 个版本控制问题:")
        for issue in issues:
            print(f"  ⚠️ {issue}")
        score = max(0, 10 - len(issues) * 3)
    else:
        print("  ✅ 版本控制良好")
        score = 10
    
    print(f"\n  版本控制得分: {score}/10")
    return score, passed, issues


def evaluate_spec_reading_auto():
    """自动评估规范阅读 — 检查项目架构文件最近是否被修改（假设修改≈被阅读）"""
    print_header("维度 10: 规范阅读自动检查")
    
    docs_path = Path("d:/AI-moyang/打包/ai_chat/docs")
    spec_file = docs_path / "项目架构和相关规范.md"
    issues = []
    passed = []
    
    if spec_file.exists():
        passed.append("项目架构和相关规范.md 存在")
        mtime = spec_file.stat().st_mtime
        if time.time() - mtime < 3 * 24 * 3600:
            passed.append("最近3天内有修改记录")
        else:
            issues.append("项目架构和相关规范.md 超过3天未修改（可能未被重新阅读）")
    else:
        issues.append("项目架构和相关规范.md 缺失")
    
    if issues:
        score = max(0, 5 - len(issues) * 3)
    else:
        score = 5
    
    print(f"\n  规范阅读得分: {score}/5")
    return score, passed, issues


def evaluate_memory_update_auto():
    """自动评估记忆更新 — 检查项目架构和相关规范.md的待办与风险章节是否最近被更新"""
    print_header("维度 11: 记忆更新自动检查")

    docs_path = Path("d:/AI-moyang/打包/ai_chat/docs")
    memory_file = docs_path / "项目架构和相关规范.md"
    issues = []
    passed = []

    if memory_file.exists():
        passed.append("项目架构和相关规范.md 存在")
        mtime = memory_file.stat().st_mtime
        if time.time() - mtime < 3 * 24 * 3600:
            passed.append("最近3天内有更新记录")
        else:
            issues.append("项目架构和相关规范.md 超过3天未更新")
    else:
        issues.append("项目架构和相关规范.md 缺失")
    
    if issues:
        score = max(0, 5 - len(issues) * 3)
    else:
        score = 5
    
    print(f"\n  记忆更新得分: {score}/5")
    return score, passed, issues


def auto_evaluate():
    """自动评估模式 — 扫描代码并评估"""
    print_header("AI 行为自动评估")
    print("正在扫描代码并自动评估...\n")
    
    all_issues = []
    dimension_scores = {}
    
    # 规范遵循（自动）
    score, passed, issues = evaluate_specification_compliance_auto()
    dimension_scores["规范遵循"] = (score, 15, passed, issues)
    all_issues.extend(issues)
    
    # 代码质量（自动）
    score, issues = evaluate_code_quality_auto()
    dimension_scores["代码质量"] = (score, 15, [], issues)
    all_issues.extend(issues)
    
    # 安全意识（自动）
    score, issues = evaluate_security_auto()
    dimension_scores["安全意识"] = (score, 20, [], issues)
    all_issues.extend(issues)
    
    # 问题处理（自动 - 检查问题反馈与报告是否更新）
    docs_path = Path("d:/AI-moyang/打包/ai_chat/docs")
    issue_report = docs_path / "问题反馈与报告.md"
    if issue_report.exists():
        content = issue_report.read_text(encoding='utf-8')
        if re.search(r'第\d+轮修复', content):
            dimension_scores["问题处理"] = (12, 15, ["问题反馈与报告已更新"], [])
        else:
            dimension_scores["问题处理"] = (3, 15, [], ["问题反馈与报告可能未更新"])
    else:
        dimension_scores["问题处理"] = (2, 15, [], ["问题反馈与报告缺失"])
    
    # 文档同步（自动）
    score, passed, issues = evaluate_document_sync_auto()
    dimension_scores["文档同步"] = (score, 10, passed, issues)
    all_issues.extend(issues)
    
    # 任务完成度（自动 - 基于问题修复情况）
    if issue_report.exists():
        content = issue_report.read_text(encoding='utf-8')
        m = re.search(r'已修复\**:\s*(\d+)个', content)
        if m and int(m.group(1)) >= 200:
            dimension_scores["任务完成度"] = (8, 10, [f"已修复{m.group(1)}项，进度正常"], [])
        elif m:
            dimension_scores["任务完成度"] = (5, 10, [f"已修复{m.group(1)}项"], ["累计修复数偏低，需确认"])
        else:
            dimension_scores["任务完成度"] = (2, 10, [], ["无法获取修复进度"])
    else:
        dimension_scores["任务完成度"] = (1, 10, [], ["无法确认任务完成度"])
    
    # 错误处理（自动）
    score, issues = evaluate_error_handling_auto()
    dimension_scores["错误处理"] = (score, 10, [], issues)
    all_issues.extend(issues)
    
    # 效率优化（自动）
    score, issues = evaluate_efficiency_auto()
    dimension_scores["效率优化"] = (score, 5, [], issues)
    all_issues.extend(issues)
    
    # 版本控制（自动）
    score, passed, issues = evaluate_version_control_auto()
    dimension_scores["版本控制"] = (score, 10, passed, issues)
    all_issues.extend(issues)
    
    # 规范阅读（自动）
    score, passed, issues = evaluate_spec_reading_auto()
    dimension_scores["规范阅读"] = (score, 5, passed, issues)
    all_issues.extend(issues)
    
    # 记忆更新（自动）
    score, passed, issues = evaluate_memory_update_auto()
    dimension_scores["记忆更新"] = (score, 5, passed, issues)
    all_issues.extend(issues)
    
    raw_total = sum(s[0] for s in dimension_scores.values())
    total_score = min(100, max(0, int(raw_total * 100 / 120)))
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
    score, passed, failed = evaluate_interactive("规范遵循", EVALUATION_DIMENSIONS["规范遵循"])
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
    
    # 版本控制（交互式）
    score, passed, failed = evaluate_interactive("版本控制", EVALUATION_DIMENSIONS["版本控制"])
    dimension_scores["版本控制"] = (score, 10, passed, failed)
    
    # 规范阅读（交互式）
    score, passed, failed = evaluate_interactive("规范阅读", EVALUATION_DIMENSIONS["规范阅读"])
    dimension_scores["规范阅读"] = (score, 5, passed, failed)
    
    # 记忆更新（交互式）
    score, passed, failed = evaluate_interactive("记忆更新", EVALUATION_DIMENSIONS["记忆更新"])
    dimension_scores["记忆更新"] = (score, 5, passed, failed)
    
    raw_total = sum(s[0] for s in dimension_scores.values())
    total_score = min(100, max(0, int(raw_total * 100 / 120)))
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
    print("  100-95: 优秀 — 严格遵循规范，代码质量高，无安全问题")
    print("  94-85:  良好 — 基本遵循规范，有少量可改进之处")
    print("  84-75:  合格 — 存在一些问题但已基本完成")
    print("  74-60:  待改进 — 存在明显问题，需要重新审视")
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
            print("  python AI行为评估脚本.py --standards   # 查看评估标准")
            return
        elif arg == "--auto":
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
