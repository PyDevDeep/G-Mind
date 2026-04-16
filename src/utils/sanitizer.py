from bs4 import BeautifulSoup


def extract_clean_text(html_content: str) -> str:
    """
    Видаляє всі HTML/XML теги та скрипти. Залишає чистий текст для LLM.
    """
    if not html_content:
        return ""

    soup: BeautifulSoup = BeautifulSoup(html_content, "html.parser")

    # Видаляємо невидимий код
    for element in soup(["script", "style", "meta", "noscript"]):
        element.decompose()

    return str(soup.get_text(separator=" ", strip=True))
