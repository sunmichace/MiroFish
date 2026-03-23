#!/usr/bin/env python3
"""
研报 Markdown 数据清洗脚本
修复 front matter 中的 title / institution / author / tags 等字段质量问题，
为后续知识库入库做准备。

用法:
    # 预览模式（不写文件，只输出统计）
    python scripts/fix_research_md.py --dry-run

    # 实际执行
    python scripts/fix_research_md.py
"""

import argparse
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

SOURCE_DIR = (
    "/hdd/project/Investment/32｜通用爬虫/32.1｜wisburg智堡/omni_exports/ai_article"
)

# <source> 标签中英文机构缩写 → 中文标准名映射
INST_ABBR_MAP = {
    "GS": "高盛",
    "JPM": "摩根大通",
    "MS": "摩根士丹利",
    "UBS": "瑞银",
    "BofA": "美银美林",
    "BofAS": "美银美林",
    "DB": "德意志银行",
    "HSBC": "汇丰",
    "Barclays": "巴克莱",
    "CITI": "花旗",
    "Citi": "花旗",
    "Nomura": "野村",
    "NSC": "野村",
    "BCI": "巴克莱",
}

# institution 字段中不是真正机构名的值（实际是话题标签）
FAKE_INSTITUTIONS = {
    "中国经济", "全球经济", "美国经济", "日本经济", "欧洲经济",
    "新兴市场", "亚洲经济", "英国经济", "欧元区经济",
}

# 已知机构名集合（用于从 tags/title 中恢复 institution）
KNOWN_INSTITUTIONS = {
    "高盛", "摩根大通", "摩根士丹利", "美银美林", "瑞银", "花旗",
    "德意志银行", "汇丰", "巴克莱", "野村",
    "欧洲央行", "美联储", "日本央行", "英国央行", "法国央行", "德国央行",
    "亚洲开发银行", "国际清算银行", "纽约联储",
    "CharlesSchwab", "Amundi", "PIMCO",
    "罗素投资", "摩根大通资管", "嘉信理财", "摩根士丹利资管", "美银研究院",
    "高盛资管", "贝莱德", "威灵顿资管", "安石集团", "智堡精选", "施罗德",
    "彼得森国际经济研究所", "布鲁盖尔研究所", "东方汇理",
}

# author 字段中实际是机构名的关键词
INST_AUTHOR_KEYWORDS = [
    "央行", "银行", "联储", "研究院", "研究所", "资管",
    "PIMCO", "Amundi", "CharlesSchwab", "嘉信", "开发银行",
    "清算银行", "布鲁盖尔", "彼得森", "罗素", "威灵顿",
    "贝莱德", "安石", "智堡", "施罗德",
]

# ---------------------------------------------------------------------------
# YAML 手工解析 / 序列化（避免引入 PyYAML 依赖 + 保持格式稳定）
# ---------------------------------------------------------------------------


def parse_frontmatter(text: str) -> tuple[dict | None, str]:
    """从 markdown 文本中解析 YAML front matter，返回 (fm_dict, body)。"""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
    if not m:
        return None, text

    fm_raw = m.group(1)
    body = m.group(2)

    fm: dict = {}
    current_key = None
    list_buffer: list[str] = []

    for line in fm_raw.split("\n"):
        # list item
        list_m = re.match(r'^- "?(.*?)"?\s*$', line)
        if list_m and current_key:
            list_buffer.append(list_m.group(1))
            continue

        # flush previous list
        if list_buffer and current_key:
            fm[current_key] = list_buffer
            list_buffer = []

        # key: value
        kv_m = re.match(r'^(\w[\w_]*)\s*:\s*(.*?)\s*$', line)
        if kv_m:
            current_key = kv_m.group(1)
            val = kv_m.group(2).strip('"').strip("'")
            if val == "":
                # might be a list starting next line
                fm[current_key] = val
            elif val.lower() in ("true", "false"):
                fm[current_key] = val.lower() == "true"
            else:
                try:
                    fm[current_key] = int(val)
                except ValueError:
                    fm[current_key] = val

    # flush trailing list
    if list_buffer and current_key:
        fm[current_key] = list_buffer

    return fm, body


def serialize_frontmatter(fm: dict) -> str:
    """将 dict 序列化为 YAML front matter 字符串（含 --- 分隔符）。"""
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f'- "{item}"')
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, int):
            lines.append(f"{k}: {v}")
        else:
            # 字符串：如果包含特殊字符则加引号
            sv = str(v)
            if any(c in sv for c in ':"\'{}[]#&*!|>%@`'):
                lines.append(f'{k}: "{sv}"')
            else:
                lines.append(f"{k}: {sv}")
    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 修复逻辑
# ---------------------------------------------------------------------------


def extract_real_title(title: str, institution: str) -> tuple[str, list[str]]:
    """
    从标签拼接式 title 中提取真正的报告标题和标签列表。

    输入: "巴克莱-全球经济-经济-美国经济-...-全球经济周报: 忽略颠簸"
    输出: ("全球经济周报: 忽略颠簸", ["全球经济", "经济", "美国经济", ...])
    """
    # 去掉机构前缀
    if institution and title.startswith(institution + "-"):
        without_inst = title[len(institution) + 1 :]
    else:
        without_inst = title

    parts = without_inst.split("-")
    if len(parts) <= 1:
        return without_inst.strip(), []

    # 策略：从左到右扫描，找到第一个"标题特征"的 part
    # 标题特征：包含冒号/长度>15/包含年份数字模式
    title_start_idx = len(parts)
    for i, p in enumerate(parts):
        ps = p.strip()
        # 包含冒号 → 一定是标题
        if ":" in ps or "：" in ps:
            title_start_idx = i
            break
        # 长度 > 15 且不是已知标签模式 → 很可能是标题
        if len(ps) > 15:
            title_start_idx = i
            break

    # 如果没找到明确标题，取最后一个 part
    if title_start_idx >= len(parts):
        title_start_idx = len(parts) - 1

    extracted_tags = [p.strip() for p in parts[:title_start_idx] if p.strip()]
    real_title = "-".join(parts[title_start_idx:]).strip()

    return real_title, extracted_tags


def parse_source_tag(body: str) -> dict:
    """
    从正文 <source> 标签中提取结构化信息。

    返回: {
        "source_institution": "GS" | None,
        "source_institution_cn": "高盛" | None,
        "source_author": "Friedrich Schaper" | None,
        "source_date": "2025-08-29" | None,
    }
    """
    result = {
        "source_institution": None,
        "source_institution_cn": None,
        "source_author": None,
        "source_date": None,
    }

    m = re.search(r"<source>(.*?)</source>", body)
    if not m:
        return result

    src = m.group(1).strip()

    # 提取机构
    inst_m = re.search(r"引用了(\w+)的研究员", src)
    if inst_m:
        abbr = inst_m.group(1)
        result["source_institution"] = abbr
        result["source_institution_cn"] = INST_ABBR_MAP.get(abbr, abbr)

    # 提取作者
    author_m = re.search(r"研究员\s*(.+?)的报告", src)
    if author_m:
        result["source_author"] = author_m.group(1).strip()

    # 提取日期 → 统一为 YYYY-MM-DD
    date_m = re.search(r"发布于[：:]?\s*(.+?)[\s。]*$", src)
    if date_m:
        raw_date = date_m.group(1).strip().rstrip("。").strip()
        result["source_date"] = normalize_date(raw_date)

    return result


def normalize_date(raw: str) -> str | None:
    """尝试将各种日期格式统一为 YYYY-MM-DD，失败返回 None。"""
    if not raw:
        return None

    # 已经是标准格式
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw

    # 中文格式: 2025年10月13日
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # DD-Mon-YY: 15-Oct-25
    m = re.match(r"(\d{1,2})-(\w{3})-(\d{2,4})", raw)
    if m:
        try:
            dt = datetime.strptime(raw.rstrip(",").strip(), "%d-%b-%y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            try:
                dt = datetime.strptime(raw.rstrip(",").strip(), "%d-%b-%Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

    # DD Month YYYY: 12 September 2025
    m = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", raw)
    if m:
        try:
            dt = datetime.strptime(raw.strip(), "%d %B %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # DD/MM/YYYY: 14/10/2025
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", raw)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    # MM/DD/YYYY: 11/6/2025
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if month <= 12:
            return f"{year}-{month:02d}-{day:02d}"

    # YYYY-MM (partial)
    m = re.match(r"^(\d{4}-\d{2})$", raw)
    if m:
        return raw + "-01"

    # 2025年10月 (no day)
    m = re.match(r"(\d{4})年(\d{1,2})月$", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-01"

    return None


def extract_filename_metadata(filename: str) -> dict:
    """
    从文件名中提取元数据。
    格式: YYYYMMDD_机构-标签-...-标题_ID_kind28.md
    """
    result = {"fn_date": None, "fn_institution": None, "fn_id": None}

    base = filename.replace(".md", "")
    parts = base.split("_")

    if len(parts) >= 1 and re.match(r"^\d{8}$", parts[0]):
        d = parts[0]
        result["fn_date"] = f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    if len(parts) >= 2:
        tag_part = parts[1]
        first_tag = tag_part.split("-")[0] if "-" in tag_part else tag_part
        result["fn_institution"] = first_tag

    # ID is typically second-to-last part (before kind28)
    if len(parts) >= 3:
        for p in reversed(parts):
            if p.startswith("kind"):
                continue
            if re.match(r"^\d{4,6}$", p):
                result["fn_id"] = p
                break

    return result


def is_author_actually_institution(author: str) -> bool:
    """判断 author 字段是否实际上是机构名。"""
    if not author:
        return False
    return any(kw in author for kw in INST_AUTHOR_KEYWORDS)


def fix_file(filepath: str, dry_run: bool = False) -> dict:
    """
    修复单个 MD 文件，返回修改统计。
    """
    stats = Counter()

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    fm, body = parse_frontmatter(content)
    if fm is None:
        stats["skip_no_frontmatter"] += 1
        return stats

    filename = os.path.basename(filepath)
    fn_meta = extract_filename_metadata(filename)
    src_info = parse_source_tag(body)
    modified = False

    # --- 1. 修复 title：提取真正标题，保留原始 title 为 original_title ---
    old_title = fm.get("title", "")
    institution = fm.get("institution", "")
    if old_title and "-" in old_title:
        real_title, extracted_tags = extract_real_title(old_title, institution)
        if real_title and real_title != old_title:
            fm["original_title"] = old_title
            fm["title"] = real_title
            stats["fix_title"] += 1
            modified = True

            # 补充 tags
            existing_tags = fm.get("tags", []) or []
            if isinstance(existing_tags, str):
                existing_tags = [existing_tags]
            existing_set = set(existing_tags)
            new_tags = [t for t in extracted_tags if t not in existing_set]
            if new_tags:
                fm["tags"] = existing_tags + new_tags
                stats["fix_tags_enriched"] += 1

    # --- 2. 修复 institution：如果是假机构名，从 source / tags / title 修复 ---
    if institution in FAKE_INSTITUTIONS:
        new_inst = None
        # 优先用 <source> 中的机构
        if src_info["source_institution_cn"]:
            new_inst = src_info["source_institution_cn"]
            stats["fix_institution_from_source"] += 1
        else:
            # 从 tags 或 title 中的标签部分找已知机构名
            search_pool = list(fm.get("tags", []) or [])
            if old_title:
                search_pool.extend(p.strip() for p in old_title.split("-"))
            for candidate in search_pool:
                if candidate in KNOWN_INSTITUTIONS:
                    new_inst = candidate
                    stats["fix_institution_from_tags"] += 1
                    break
        if new_inst:
            fm["institution"] = new_inst
            modified = True
        else:
            stats["institution_still_fake"] += 1

    # --- 3. 修复 author ---
    author = fm.get("author", "")

    # 3a. author 为空 → 从 <source> 补充
    if not author and src_info["source_author"]:
        fm["author"] = src_info["source_author"]
        stats["fix_author_from_source"] += 1
        modified = True

    # 3b. author 是机构名 → 移到 institution_author，从 source 补人名
    elif is_author_actually_institution(author):
        fm["institution_author"] = author
        if src_info["source_author"]:
            fm["author"] = src_info["source_author"]
            stats["fix_author_was_institution"] += 1
        else:
            fm["author"] = ""
            stats["author_cleared_no_replacement"] += 1
        modified = True

    # --- 4. 添加 source_date（原始报告发布日期） ---
    if src_info["source_date"] and "source_date" not in fm:
        fm["source_date"] = src_info["source_date"]
        stats["add_source_date"] += 1
        modified = True

    # --- 5. 添加 source_institution（英文缩写） ---
    if src_info["source_institution"] and "source_institution" not in fm:
        fm["source_institution"] = src_info["source_institution"]
        stats["add_source_institution"] += 1
        modified = True

    # --- 6. 清理正文 ---
    new_body = body

    # 6a. 移除 _No body content found._ 标记
    if "_No body content found._" in new_body:
        new_body = new_body.replace("_No body content found._", "").rstrip() + "\n"
        stats["remove_no_body_marker"] += 1
        modified = True

    # --- 7. 确保 FM 字段顺序合理 ---
    ordered_fm = _reorder_fm(fm)

    # --- 写回 ---
    if modified and not dry_run:
        new_content = serialize_frontmatter(ordered_fm) + "\n" + new_body
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        stats["files_written"] += 1
    elif modified:
        stats["files_would_write"] += 1

    return stats


def _reorder_fm(fm: dict) -> dict:
    """按优先级重排 front matter 字段。"""
    priority = [
        "title", "original_title", "source", "kind", "published", "source_date",
        "readable", "vip_visibility",
        "institution", "source_institution", "institution_author",
        "author", "detail_type", "tags",
    ]
    ordered = {}
    for key in priority:
        if key in fm:
            ordered[key] = fm[key]
    # 剩余字段
    for key in fm:
        if key not in ordered:
            ordered[key] = fm[key]
    return ordered


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="研报 MD 数据清洗")
    parser.add_argument(
        "--dry-run", action="store_true", help="预览模式，不写文件"
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="只处理前 N 个文件（调试用）"
    )
    parser.add_argument(
        "--dir", type=str, default=SOURCE_DIR, help="MD 文件目录"
    )
    args = parser.parse_args()

    src_dir = args.dir
    if not os.path.isdir(src_dir):
        print(f"目录不存在: {src_dir}", file=sys.stderr)
        sys.exit(1)

    files = sorted(f for f in os.listdir(src_dir) if f.endswith(".md"))
    total = len(files)
    if args.limit > 0:
        files = files[: args.limit]

    print(f"{'[DRY RUN] ' if args.dry_run else ''}处理 {len(files)}/{total} 个文件...")
    print()

    total_stats = Counter()
    errors = []

    for i, filename in enumerate(files):
        filepath = os.path.join(src_dir, filename)
        try:
            stats = fix_file(filepath, dry_run=args.dry_run)
            total_stats += stats
        except Exception as e:
            errors.append((filename, str(e)))
            total_stats["errors"] += 1

        if (i + 1) % 2000 == 0:
            print(f"  进度: {i + 1}/{len(files)}")

    # 输出统计
    print()
    print("=" * 60)
    print("修复统计")
    print("=" * 60)
    for key, val in sorted(total_stats.items()):
        print(f"  {key}: {val}")

    if errors:
        print()
        print(f"错误 ({len(errors)}):")
        for fn, err in errors[:20]:
            print(f"  {fn[:60]}: {err[:80]}")

    print()
    if args.dry_run:
        print("这是预览模式，未修改任何文件。去掉 --dry-run 执行实际修改。")
    else:
        print("完成。")


if __name__ == "__main__":
    main()
