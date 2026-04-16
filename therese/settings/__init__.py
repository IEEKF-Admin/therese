from split_settings.tools import include, optional

include(
    'base.py',
    optional('dev.py'),
    optional('prod.py'),
)