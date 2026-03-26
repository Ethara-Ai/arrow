"""Provides the :class:`Arrow <arrow.formatter.DateTimeFormatter>` class, an improved formatter for datetimes."""

import re
from datetime import datetime, timedelta, timezone
from typing import Final, Optional, Pattern, cast

from arrow import locales
from arrow.constants import DEFAULT_LOCALE

FORMAT_ATOM: Final[str] = "YYYY-MM-DD HH:mm:ssZZ"
FORMAT_COOKIE: Final[str] = "dddd, DD-MMM-YYYY HH:mm:ss ZZZ"
FORMAT_RFC822: Final[str] = "ddd, DD MMM YY HH:mm:ss Z"
FORMAT_RFC850: Final[str] = "dddd, DD-MMM-YY HH:mm:ss ZZZ"
FORMAT_RFC1036: Final[str] = "ddd, DD MMM YY HH:mm:ss Z"
FORMAT_RFC1123: Final[str] = "ddd, DD MMM YYYY HH:mm:ss Z"
FORMAT_RFC2822: Final[str] = "ddd, DD MMM YYYY HH:mm:ss Z"
FORMAT_RFC3339: Final[str] = "YYYY-MM-DD HH:mm:ssZZ"
FORMAT_RFC3339_STRICT: Final[str] = "YYYY-MM-DDTHH:mm:ssZZ"
FORMAT_RSS: Final[str] = "ddd, DD MMM YYYY HH:mm:ss Z"
FORMAT_W3C: Final[str] = "YYYY-MM-DD HH:mm:ssZZ"


class DateTimeFormatter:
    # This pattern matches characters enclosed in square brackets are matched as
    # an atomic group. For more info on atomic groups and how to they are
    # emulated in Python's re library, see https://stackoverflow.com/a/13577411/2701578

    _FORMAT_RE: Final[Pattern[str]] = re.compile(
        r"(\[(?:(?=(?P<literal>[^]]))(?P=literal))*\]|YYY?Y?|MM?M?M?|Do|DD?D?D?|d?dd?d?|HH?|hh?|mm?|ss?|SS?S?S?S?S?|ZZ?Z?|a|A|X|x|W)"
    )

    locale: locales.Locale

    def __init__(self, locale: str = DEFAULT_LOCALE) -> None:
        self.locale = locales.get_locale(locale)


