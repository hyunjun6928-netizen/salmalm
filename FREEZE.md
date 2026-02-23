# 🧊 FEATURE FREEZE — 2026-02-23 ~ 2026-03-09

## Rules
1. **NO new features** — zero new endpoints, UI panels, or tools
2. **Bug fixes ONLY** — only if user-reported and breaking
3. **NO version bumps** unless critical security patch
4. **Test daily** — run `salmalm doctor` and monitor logs
5. **Document** — update docs site, README, changelog only

## Goal
2 weeks of stable operation without hotfixes.
Score target: 70 → 80/100.

## Allowed
- Documentation updates
- Test coverage improvements
- README/changelog updates
- Log review and minor log message improvements

## Forbidden
- New API endpoints
- New UI components
- New tools or features
- Refactoring that changes behavior
- "Quick fix" chains (the 똥꼬쇼)

## Break conditions
- Critical security vulnerability (P0)
- Data loss bug
- Complete service failure

## Status
⚠️ **Freeze has been broken repeatedly** — multiple bug fixes and improvements landed during the freeze period (v0.19.25–v0.19.39). The intent remains valid but enforcement has been relaxed for critical fixes.

---
*"통제할 수 없는 것에 동요하지 않고, 자신의 역할에 충실하라." — 마르쿠스 아우렐리우스*
