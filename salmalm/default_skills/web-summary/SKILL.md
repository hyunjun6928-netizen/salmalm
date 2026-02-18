# Web Summary
> Summarize any webpage or article into key points.

## Instructions
1. Use `web_fetch(url="<target_url>")` to get the page content
2. If the page is too long (>5000 chars), focus on:
   - Title and main headings
   - First and last paragraphs
   - Key data points and quotes
3. Produce a structured summary:
   - **TL;DR** (1-2 sentences)
   - **Key Points** (3-5 bullet points)
   - **Notable Quotes** (if any)
   - **Source**: original URL

## Tips
- For news articles: focus on who, what, when, where, why
- For technical docs: focus on API changes, breaking changes, new features
- For research papers: focus on abstract, methodology, results, conclusions
