"""Memory tools: memory_read, memory_write, memory_search, usage_report."""
from salmalm.tool_registry import register
from salmalm.constants import MEMORY_FILE, MEMORY_DIR
from salmalm.core import _tfidf, get_usage_report


@register('memory_read')
def handle_memory_read(args: dict) -> str:
    fname = args['file']
    if fname == 'MEMORY.md':
        p = MEMORY_FILE
    else:
        p = MEMORY_DIR / fname
    if not p.exists():
        return f'File not found: {fname}'
    return p.read_text(encoding='utf-8')[:30000]


@register('memory_write')
def handle_memory_write(args: dict) -> str:
    fname = args['file']
    if fname == 'MEMORY.md':
        p = MEMORY_FILE
    else:
        p = MEMORY_DIR / fname
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(args['content'], encoding='utf-8')
    return f'{fname} saved'


@register('memory_search')
def handle_memory_search(args: dict) -> str:
    query = args['query']
    max_results = args.get('max_results', 5)
    results = _tfidf.search(query, max_results)
    if not results:
        return f'No results for: "{query}"'
    out = []
    for score, label, lineno, snippet in results:
        out.append(f'{label}#{lineno} (similarity:{score:.3f})\n{snippet}\n')
    return '\n'.join(out)


@register('usage_report')
def handle_usage_report(args: dict) -> str:
    report = get_usage_report()
    lines = [f"SalmAlm Usage Report",
             f"Uptime: {report['elapsed_hours']}h",
             f"Input: {report['total_input']:,} tokens",
             f"Output: {report['total_output']:,} tokens",
             f"Total cost: ${report['total_cost']:.4f}", ""]
    for m, d in report.get('by_model', {}).items():
        lines.append(f"  {m}: {d['calls']}calls, ${d['cost']:.4f}")
    return '\n'.join(lines)
