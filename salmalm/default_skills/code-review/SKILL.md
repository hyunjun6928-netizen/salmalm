# Code Review
> Review code files for security, performance, and readability issues.

## Instructions
1. Use `read_file` to load the target file
2. Analyze for:
   - **Security**: SQL injection, XSS, path traversal, hardcoded secrets, SSRF
   - **Performance**: N+1 queries, unnecessary loops, memory leaks
   - **Readability**: naming, complexity, dead code, missing error handling
3. Rate each category (1-10) and provide specific line-number references
4. Suggest concrete fixes with code snippets

## Output Format
```
## Security: X/10
- [Line N] Issue description → Fix suggestion

## Performance: X/10
- [Line N] Issue description → Fix suggestion

## Readability: X/10
- [Line N] Issue description → Fix suggestion

## Overall: X/10
Summary + top 3 priorities
```
