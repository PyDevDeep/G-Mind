from bs4 import BeautifulSoup


def extract_clean_text(html_content: str) -> str:
    """Strip all HTML/XML tags and scripts, returning plain text for LLM input."""
    if not html_content:
        return ""

    soup: BeautifulSoup = BeautifulSoup(html_content, "html.parser")

    for element in soup(["script", "style", "meta", "noscript"]):
        element.decompose()

    return str(soup.get_text(separator=" ", strip=True))
