"""Build search queries for the search-based sources from all applicants.

Each applicant contributes (target role x city) pairs, plus a (role, country,
remote) pair when they are open to remote work. Ordering, so that when a
source caps its queries the most useful searches survive:
  1. pairs wanted by more applicants first;
  2. then round-robin across applicants: everyone's best role (their first
     target role, in their first city) before anyone's second, so one user
     with many roles can't use up the whole budget.
Cost grows with distinct roles/places, not with the number of users.
"""


def _clean(text):
    return " ".join((text or "").split())


def _wanted(applicant):
    """This applicant's targets, best first: role by role, cities before remote."""
    roles = [_clean(r) for r in applicant.get("target_roles") or [] if _clean(r)]
    places = [p for p in applicant.get("locations") or [] if isinstance(p, dict)]
    out = []
    for role in roles:
        for place in places:
            if _clean(place.get("city")):
                out.append((role, _clean(place.get("city")), _clean(place.get("country")),
                            _clean(place.get("country_code")).upper(), False))
        if applicant.get("open_to_remote"):
            countries = {(_clean(p.get("country")), _clean(p.get("country_code")).upper())
                         for p in places} or {("", "")}
            for country, code in sorted(countries):
                out.append((role, "", country, code, True))
    return out


def search_targets(applicants):
    """Return [{"role", "city", "country", "country_code", "remote"}], best first."""
    votes, best_turn, display = {}, {}, {}
    for applicant in applicants:
        seen = set()
        for turn, (role, city, country, code, remote) in enumerate(_wanted(applicant)):
            key = (role.lower(), city.lower(), code, remote)
            if key in seen:
                continue
            seen.add(key)
            votes[key] = votes.get(key, 0) + 1
            best_turn[key] = min(best_turn.get(key, turn), turn)
            display.setdefault(key, (role, city, country, code))

    order = sorted(votes, key=lambda k: (-votes[k], best_turn[k], k))
    return [dict(zip(("role", "city", "country", "country_code"), display[k]), remote=k[3])
            for k in order]
