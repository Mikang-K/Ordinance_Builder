# Keyword hints used to match provision content to article interview keys.
# Each article key maps to phrases likely to appear in the corresponding provision.
_ARTICLE_HINTS: dict[str, list[str]] = {
    "목적": ["목적으로 한다", "이바지함을 목적", "목적"],
    "정의": ["이라 한다", "말한다", "이란 ", "정의"],
    "지원대상": ["지원 대상", "대상자", "자격 요건", "자격은", "으로 한다"],
    "지원내용": ["지원한다", "지급한다", "보조금으로", "지원 내용", "지원한다"],
    "지원금액": ["한도로 하며", "한도로 한다", "이내로", "만원", "예산의 범위"],
    "신청방법": ["신청", "제출하여야", "신청 방법", "제출 서류"],
    "심사선정": ["심사위원회", "심사·선정", "심사 기준", "선정한다"],
    "환수제재": ["환수", "반환", "제재", "지원을 제한"],
    "위임": ["규칙으로 정한다", "위임"],
}


def find_article_examples(
    article_key: str,
    article_examples: list[dict],
    max_count: int = 2,
) -> list[dict]:
    """
    Return up to max_count provisions from article_examples that match
    the given article_key based on keyword hints.

    Picks at most one example per ordinance to avoid redundancy.
    """
    hints = _ARTICLE_HINTS.get(article_key, [])
    if not hints or not article_examples:
        return []

    matched: list[dict] = []
    seen_ordinances: set[str] = set()

    for ex in article_examples:
        oid = ex.get("ordinance_id", "")
        if oid in seen_ordinances:
            continue
        content = ex.get("content_text", "")
        if any(hint in content for hint in hints):
            matched.append(ex)
            seen_ordinances.add(oid)
            if len(matched) >= max_count:
                break

    return matched


def format_examples_block(examples: list[dict]) -> str:
    """
    Format a list of provision examples into a readable reference block.
    Returns an empty string when examples is empty.
    """
    if not examples:
        return ""

    lines = []
    for ex in examples:
        region = ex.get("region_name", "")
        title = ex.get("ordinance_title", "")
        article = ex.get("article_no", "")
        content = ex.get("content_text", "")
        lines.append(f"  • **{region}** ({title}, {article})\n    \"{content}\"")

    return "\n\n> 💡 **유사 조례 참고 사례:**\n" + "\n".join(lines)
