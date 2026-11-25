import re

from kb.corpus import DOCS

_STOP = frozenset(
    """
    the and for with this that from after what should check how does did are was were
    you your into over when where which while about not
    """.split()
)
_TOKEN = re.compile(r"[a-z0-9]+")


def search_runbooks(query: str, limit: int = 3) -> list[dict[str, str]]:
    terms = {
        token for token in _TOKEN.findall(query.lower()) if len(token) > 2 and token not in _STOP
    }
    if not terms:
        return []
    scored: list[tuple[int, dict[str, str]]] = []
    for doc in DOCS:
        haystack = f"{doc['title']} {doc['body']}".lower()
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score, doc))
    scored.sort(key=lambda item: (-item[0], item[1]["id"]))
    return [
        {"id": doc["id"], "title": doc["title"], "snippet": doc["body"][:280]}
        for _, doc in scored[:limit]
    ]
