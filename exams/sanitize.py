import bleach

# Matches exactly what app.js's Quill toolbars can produce: question/explanation
# toolbar is bold/italic/underline/ordered-list/bullet-list/link; option toolbar
# is bold/italic/underline only. Anything wider is unreachable from the actual
# editor config, so it's not allowed through here either.
ALLOWED_TAGS = ['p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li', 'a']
ALLOWED_ATTRS = {'a': ['href']}


def sanitize_html(value):
    if not value:
        return value
    return bleach.clean(value, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
