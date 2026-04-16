from config import (
    TWITTER_COM_PATTERN,
    X_COM_PATTERN,
    INSTAGRAM_COM_PATTERN,
    TIKTOK_COM_PATTERN,
    REDDIT_COM_PATTERN,
)


def rewrite_social_urls(content: str) -> str:
    new_message = content
    if TWITTER_COM_PATTERN.search(new_message):
        new_message = TWITTER_COM_PATTERN.sub(r'https://vxtwitter.com/\2/\3', new_message)
    if X_COM_PATTERN.search(new_message):
        new_message = X_COM_PATTERN.sub('https://fixvx.com', new_message)
    if INSTAGRAM_COM_PATTERN.search(new_message):
        new_message = INSTAGRAM_COM_PATTERN.sub('https://eeinstagram.com', new_message)
    if TIKTOK_COM_PATTERN.search(new_message):
        new_message = TIKTOK_COM_PATTERN.sub('https://tnktok.com', new_message)
    if REDDIT_COM_PATTERN.search(new_message):
        new_message = REDDIT_COM_PATTERN.sub('https://rxddit.com', new_message)
    return new_message
