"""Structural article IDs for the 2026 handbook, assigned before token splitting.

Semantic cNNN IDs require an explicit annotation map; never infer them from
the first article mentioned in a token chunk or from evaluation answers.
"""
import re
import json
import hashlib
from pathlib import Path

from langchain_core.documents import Document


HANDBOOK = "广东工业大学2026学生手册.md"
PREFIXES = {
    "普通高等学校学生管理规定": "gdut26-sm",
    "广东工业大学学生管理规定": "gdut26-gdut-sm",
    "广东工业大学全日制普通本科学生学籍管理实施办法": "gdut26-ug-status",
    "广东工业大学学分认定实施细则": "gdut26-credit",
    "广东工业大学学士学位授予工作细则": "gdut26-degree",
    "广东工业大学学生违纪处分办法": "gdut26-discipline",
    "广东工业大学学生申诉处理办法": "gdut26-appeal",
    "广东工业大学学生违纪处分听证实施办法": "gdut26-hearing",
    "广东工业大学交换学生管理规定": "gdut26-exchange",
    "广东工业大学全日制本科学生综合素质测评实施办法": "gdut26-assessment",
    "广东工业大学全日制本科学生奖学金评定办法": "gdut26-scholarship",
    "广东工业大学学生资助工作实施办法": "gdut26-aid",
    "广东工业大学图书馆读者借阅管理规定": "gdut26-library",
    "广东工业大学学生宿舍管理规定": "gdut26-dorm",
    "广东工业大学校园网管理办法": "gdut26-network",
}
NUMBER = "[零一二三四五六七八九十百]+"
TITLE = re.compile(r"(?m)^### (.+)$")
STRUCTURE = re.compile(rf"(?m)^(?:#{{1,6}}[ \t]+)?第({NUMBER})(章|节)[ \t]+([^\n]+)$")
ARTICLE = re.compile(rf"(?m)(?<!\S)第({NUMBER})条[ \t]+")


def chinese_number(value):
    digits = dict(zip("零一二三四五六七八九", range(10)))
    total, digit = 0, 0
    for char in value:
        if char in digits:
            digit = digits[char]
        elif char in ("十", "百"):
            total += (digit or 1) * {"十": 10, "百": 100}[char]
            digit = 0
        else:
            raise ValueError(f"Invalid Chinese number: {value}")
    return total + digit


def split_handbook(text, filename=HANDBOOK, *, apply_mapping=True):
    """Keep all text, using explicit chapter/section/article boundaries."""
    titles = list(TITLE.finditer(text))
    documents = []

    def append(content, section, doc_id=None, article=None, prefix=None, chapter=None):
        if content.strip():
            metadata = {"source": filename, "file_type": "md", "section": section}
            if doc_id:
                metadata["doc_id"] = doc_id
            if article is not None and prefix:
                metadata.update(policy_prefix=prefix, article=article, chapter=chapter or 0)
            documents.append(Document(page_content=content.strip(), metadata=metadata))

    append(text[:titles[0].start()] if titles else text, "正文")
    for index, title in enumerate(titles):
        end = titles[index + 1].start() if index + 1 < len(titles) else len(text)
        body = text[title.end():end]
        name = title[1].strip()
        prefix = PREFIXES.get(re.sub(r"\s+", "", name))
        boundaries = [(m.start(), "structure", m) for m in STRUCTURE.finditer(body)]
        boundaries += [(m.start(), "article", m) for m in ARTICLE.finditer(body)]
        boundaries.sort(key=lambda item: item[0])
        chapter = subsection = None
        chapter_title = section_title = ""
        leading_end = boundaries[0][0] if boundaries else len(body)
        append(text[title.start():title.end()] + body[:leading_end], name)
        for offset, (start, kind, match) in enumerate(boundaries):
            stop = boundaries[offset + 1][0] if offset + 1 < len(boundaries) else len(body)
            doc_id = None
            if kind == "structure":
                if match[2] == "章":
                    chapter = chinese_number(match[1])
                    chapter_title = f"第{match[1]}章 {match[3].strip()}"
                    subsection, section_title = None, ""
                else:
                    subsection = chinese_number(match[1])
                    section_title = f"第{match[1]}节 {match[3].strip()}"
            elif prefix and chapter is not None:
                doc_id = f"{prefix}-ch{chapter:02d}"
                if subsection is not None:
                    doc_id += f"-s{subsection:02d}"
                doc_id += f"-a{chinese_number(match[1]):03d}"
            section = " > ".join(part for part in (name, chapter_title, section_title) if part)
            append(body[start:stop], section, doc_id,
                   chinese_number(match[1]) if kind == "article" else None, prefix, chapter)
    return apply_semantic_map(documents, text) if apply_mapping else documents


def apply_semantic_map(documents, text):
    mapping = json.loads(Path(__file__).with_name("handbook_map.json").read_text(encoding="utf-8"))
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != mapping["source_sha256"]:
        raise ValueError("Handbook changed; review handbook_map.json before rebuilding the index")
    replacements, consumed = {}, set()
    for group in mapping["groups"]:
        first, last = group["articles"]
        selected = [(i, d) for i, d in enumerate(documents)
                    if d.metadata.get("policy_prefix") == group["prefix"]
                    and d.metadata.get("chapter") == (group["chapter"] or 0)
                    and first <= d.metadata.get("article", -1) <= last]
        numbers = [d.metadata["article"] for _, d in selected]
        if numbers != list(range(first, last + 1)):
            raise ValueError(f"Missing or duplicated article boundaries for {group['id']}: {numbers}")
        indices = {i for i, _ in selected}
        if consumed & indices:
            raise ValueError(f"Overlapping semantic groups: {group['id']}")
        consumed.update(indices)
        metadata = dict(selected[0][1].metadata, doc_id=group["id"],
                        annotation_version=mapping["version"], source_sha256=mapping["source_sha256"])
        metadata.pop("article", None)
        replacements[selected[0][0]] = Document(
            page_content="\n\n".join(d.page_content for _, d in selected), metadata=metadata)
    result = [replacements.get(i, d) for i, d in enumerate(documents)
              if i not in consumed or i in replacements]
    for document in result:
        document.metadata.update(annotation_version=mapping["version"], source_sha256=mapping["source_sha256"])
    return result
