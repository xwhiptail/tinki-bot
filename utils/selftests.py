from utils.url_rewriter import rewrite_social_urls
from utils.calculator import maybe_calculate_reply
from utils.letter_counter import maybe_count_letter_reply


def run_url_selftests():
    test_cases = [
        ("twitter basic", "check this https://twitter.com/foo/bar", "check this https://vxtwitter.com/foo/bar"),
        ("twitter www", "link: https://www.twitter.com/foo/bar", "link: https://vxtwitter.com/foo/bar"),
        ("x.com", "post: https://x.com/foo/status/12345", "post: https://fixvx.com/foo/status/12345"),
        ("instagram", "pic: https://www.instagram.com/p/ABC123", "pic: https://eeinstagram.com/p/ABC123"),
        ("tiktok", "vid: https://www.tiktok.com/@user/video/987654321", "vid: https://tnktok.com/@user/video/987654321"),
        ("reddit", "thread: https://www.reddit.com/r/test/comments/abc123/slug", "thread: https://rxddit.com/r/test/comments/abc123/slug"),
        ("no-change", "hello there", "hello there"),
    ]
    results = []
    for name, original, expected in test_cases:
        got = rewrite_social_urls(original)
        if got == expected:
            results.append((name, True, None))
        else:
            results.append((name, False, f"expected `{expected}` but got `{got}`"))
    return results


def run_calculate_selftests():
    cases = [
        ("calc addition",       "2 + 2",          "4"),
        ("calc what-is prefix", "what is 10 + 5", "15"),
        ("calc x-multiply",     "3x4",             "12"),
        ("calc division",       "10 / 4",          "2.5"),
        ("calc large number",   "1000000 + 1",     "1,000,001"),
        ("calc non-expression", "hello world",      None),
        ("calc div-by-zero",    "5 / 0",            None),
    ]
    results = []
    for name, inp, expected in cases:
        got = maybe_calculate_reply(inp)
        if expected is None:
            ok = got is None
            reason = None if ok else f"expected None but got `{got}`"
        else:
            ok = got is not None and expected in got
            reason = None if ok else f"expected `{expected}` in result but got `{got}`"
        results.append((name, ok, reason))
    return results


def run_letter_count_selftests():
    cases = [
        ("letter r in strawberry",  "how many r's in strawberry",  "3"),
        ("letter s in mississippi", "how many s's in mississippi", "4"),
        ("letter e in cheese",      "how many e's in cheese?",     "3"),
        ("letter zero count",       "how many z's in apple",       "0"),
        ("letter no match",         "what time is it",              None),
    ]
    results = []
    for name, inp, expected in cases:
        got = maybe_count_letter_reply(inp)
        if expected is None:
            ok = got is None
            reason = None if ok else f"expected None but got `{got}`"
        else:
            ok = got is not None and expected in got
            reason = None if ok else f"expected `{expected}` in result but got `{got}`"
        results.append((name, ok, reason))
    return results
