"""Provides the :class:`Arrow <arrow.parser.DateTimeParser>` class, a better way to parse datetime strings."""

import re
from datetime import datetime, timedelta, timezone
from datetime import tzinfo as dt_tzinfo
from functools import lru_cache
from typing import (
    Any,
    ClassVar,
    Dict,
    Iterable,
    List,
    Literal,
    Match,
    Optional,
    Pattern,
    SupportsFloat,
    SupportsInt,
    Tuple,
    TypedDict,
    Union,
    cast,
    overload,
)

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # type: ignore[import-not-found, no-redef]

from arrow import locales
from arrow.constants import DEFAULT_LOCALE
from arrow.util import next_weekday, normalize_timestamp


class ParserError(ValueError):
    """
    A custom exception class for handling parsing errors in the parser.

    Notes:
        This class inherits from the built-in `ValueError` class and is used to raise exceptions
        when an error occurs during the parsing process.
    """

    pass


# Allows for ParserErrors to be propagated from _build_datetime()
# when day_of_year errors occur.
# Before this, the ParserErrors were caught by the try/except in
# _parse_multiformat() and the appropriate error message was not
# transmitted to the user.
class ParserMatchError(ParserError):
    """
    This class is a subclass of the ParserError class and is used to raise errors that occur during the matching process.

    Notes:
        This class is part of the Arrow parser and is used to provide error handling when a parsing match fails.

    """

    pass


_WEEKDATE_ELEMENT = Union[str, bytes, SupportsInt, bytearray]

_FORMAT_TYPE = Literal[
    "YYYY",
    "YY",
    "MM",
    "M",
    "DDDD",
    "DDD",
    "DD",
    "D",
    "HH",
    "H",
    "hh",
    "h",
    "mm",
    "m",
    "ss",
    "s",
    "X",
    "x",
    "ZZZ",
    "ZZ",
    "Z",
    "S",
    "W",
    "MMMM",
    "MMM",
    "Do",
    "dddd",
    "ddd",
    "d",
    "a",
    "A",
]


class _Parts(TypedDict, total=False):
    """
    A dictionary that represents different parts of a datetime.

    :class:`_Parts` is a TypedDict that represents various components of a date or time,
    such as year, month, day, hour, minute, second, microsecond, timestamp, expanded_timestamp, tzinfo,
    am_pm, day_of_week, and weekdate.

    :ivar year: The year, if present, as an integer.
    :ivar month: The month, if present, as an integer.
    :ivar day_of_year: The day of the year, if present, as an integer.
    :ivar day: The day, if present, as an integer.
    :ivar hour: The hour, if present, as an integer.
    :ivar minute: The minute, if present, as an integer.
    :ivar second: The second, if present, as an integer.
    :ivar microsecond: The microsecond, if present, as an integer.
    :ivar timestamp: The timestamp, if present, as a float.
    :ivar expanded_timestamp: The expanded timestamp, if present, as an integer.
    :ivar tzinfo: The timezone info, if present, as a :class:`dt_tzinfo` object.
    :ivar am_pm: The AM/PM indicator, if present, as a string literal "am" or "pm".
    :ivar day_of_week: The day of the week, if present, as an integer.
    :ivar weekdate: The week date, if present, as a tuple of three integers or None.
    """

    year: int
    month: int
    day_of_year: int
    day: int
    hour: int
    minute: int
    second: int
    microsecond: int
    timestamp: float
    expanded_timestamp: int
    tzinfo: dt_tzinfo
    am_pm: Literal["am", "pm"]
    day_of_week: int
    weekdate: Tuple[_WEEKDATE_ELEMENT, _WEEKDATE_ELEMENT, Optional[_WEEKDATE_ELEMENT]]


class DateTimeParser:
    """A :class:`DateTimeParser <arrow.arrow.parser>` object

    Contains the regular expressions and functions to parse and split the input strings into tokens and eventually
    produce a datetime that is used by :class:`Arrow <arrow.arrow.Arrow>` internally.

    :param locale: the locale string
    :param cache_size: the size of the LRU cache used for regular expressions. Defaults to 0.

    """

    _FORMAT_RE: ClassVar[Pattern[str]] = re.compile(
        r"(YYY?Y?|MM?M?M?|Do|DD?D?D?|d?d?d?d|HH?|hh?|mm?|ss?|S+|ZZ?Z?|a|A|x|X|W)"
    )
    _ESCAPE_RE: ClassVar[Pattern[str]] = re.compile(r"\[[^\[\]]*\]")

    _ONE_OR_TWO_DIGIT_RE: ClassVar[Pattern[str]] = re.compile(r"\d{1,2}")
    _ONE_OR_TWO_OR_THREE_DIGIT_RE: ClassVar[Pattern[str]] = re.compile(r"\d{1,3}")
    _ONE_OR_MORE_DIGIT_RE: ClassVar[Pattern[str]] = re.compile(r"\d+")
    _TWO_DIGIT_RE: ClassVar[Pattern[str]] = re.compile(r"\d{2}")
    _THREE_DIGIT_RE: ClassVar[Pattern[str]] = re.compile(r"\d{3}")
    _FOUR_DIGIT_RE: ClassVar[Pattern[str]] = re.compile(r"\d{4}")
    _TZ_Z_RE: ClassVar[Pattern[str]] = re.compile(r"([\+\-])(\d{2})(?:(\d{2}))?|Z")
    _TZ_ZZ_RE: ClassVar[Pattern[str]] = re.compile(r"([\+\-])(\d{2})(?:\:(\d{2}))?|Z")
    _TZ_NAME_RE: ClassVar[Pattern[str]] = re.compile(r"\w[\w+\-/]+")
    # NOTE: timestamps cannot be parsed from natural language strings (by removing the ^...$) because it will
    # break cases like "15 Jul 2000" and a format list (see issue #447)
    _TIMESTAMP_RE: ClassVar[Pattern[str]] = re.compile(r"^\-?\d+\.?\d+$")
    _TIMESTAMP_EXPANDED_RE: ClassVar[Pattern[str]] = re.compile(r"^\-?\d+$")
    _TIME_RE: ClassVar[Pattern[str]] = re.compile(
        r"^(\d{2})(?:\:?(\d{2}))?(?:\:?(\d{2}))?(?:([\.\,])(\d+))?$"
    )
    _WEEK_DATE_RE: ClassVar[Pattern[str]] = re.compile(
        r"(?P<year>\d{4})[\-]?W(?P<week>\d{2})[\-]?(?P<day>\d)?"
    )

    _BASE_INPUT_RE_MAP: ClassVar[Dict[_FORMAT_TYPE, Pattern[str]]] = {
        "YYYY": _FOUR_DIGIT_RE,
        "YY": _TWO_DIGIT_RE,
        "MM": _TWO_DIGIT_RE,
        "M": _ONE_OR_TWO_DIGIT_RE,
        "DDDD": _THREE_DIGIT_RE,
        "DDD": _ONE_OR_TWO_OR_THREE_DIGIT_RE,
        "DD": _TWO_DIGIT_RE,
        "D": _ONE_OR_TWO_DIGIT_RE,
        "HH": _TWO_DIGIT_RE,
        "H": _ONE_OR_TWO_DIGIT_RE,
        "hh": _TWO_DIGIT_RE,
        "h": _ONE_OR_TWO_DIGIT_RE,
        "mm": _TWO_DIGIT_RE,
        "m": _ONE_OR_TWO_DIGIT_RE,
        "ss": _TWO_DIGIT_RE,
        "s": _ONE_OR_TWO_DIGIT_RE,
        "X": _TIMESTAMP_RE,
        "x": _TIMESTAMP_EXPANDED_RE,
        "ZZZ": _TZ_NAME_RE,
        "ZZ": _TZ_ZZ_RE,
        "Z": _TZ_Z_RE,
        "S": _ONE_OR_MORE_DIGIT_RE,
        "W": _WEEK_DATE_RE,
    }

    SEPARATORS: ClassVar[List[str]] = ["-", "/", "."]

    locale: locales.Locale
    _input_re_map: Dict[_FORMAT_TYPE, Pattern[str]]

    def __init__(self, locale: str = DEFAULT_LOCALE, cache_size: int = 0) -> None:
        """
        Contains the regular expressions and functions to parse and split the input strings into tokens and eventually
        produce a datetime that is used by :class:`Arrow <arrow.arrow.Arrow>` internally.

        :param locale: the locale string
        :type locale: str
        :param cache_size: the size of the LRU cache used for regular expressions. Defaults to 0.
        :type cache_size: int
        """
        self.locale = locales.get_locale(locale)
        self._input_re_map = self._BASE_INPUT_RE_MAP.copy()
        self._input_re_map.update(
            {
                "MMMM": self._generate_choice_re(
                    self.locale.month_names[1:], re.IGNORECASE
                ),
                "MMM": self._generate_choice_re(
                    self.locale.month_abbreviations[1:], re.IGNORECASE
                ),
                "Do": re.compile(self.locale.ordinal_day_re),
                "dddd": self._generate_choice_re(
                    self.locale.day_names[1:], re.IGNORECASE
                ),
                "ddd": self._generate_choice_re(
                    self.locale.day_abbreviations[1:], re.IGNORECASE
                ),
                "d": re.compile(r"[1-7]"),
                "a": self._generate_choice_re(
                    (self.locale.meridians["am"], self.locale.meridians["pm"])
                ),
                # note: 'A' token accepts both 'am/pm' and 'AM/PM' formats to
                # ensure backwards compatibility of this token
                "A": self._generate_choice_re(self.locale.meridians.values()),
            }
        )
        if cache_size > 0:
            self._generate_pattern_re = lru_cache(maxsize=cache_size)(  # type: ignore
                self._generate_pattern_re
            )

    # TODO: since we support more than ISO 8601, we should rename this function
    # IDEA: break into multiple functions
    def parse_iso(
        self, datetime_string: str, normalize_whitespace: bool = False
    ) -> datetime:
        """
        Parses a datetime string using a ISO 8601-like format.

        :param datetime_string: The datetime string to parse.
        :param normalize_whitespace: Whether to normalize whitespace in the datetime string (default is False).
        :type datetime_string: str
        :type normalize_whitespace: bool
        :returns: The parsed datetime object.
        :rtype: datetime
        :raises ParserError: If the datetime string is not in a valid ISO 8601-like format.

        Usage::
        >>> import arrow.parser
        >>> arrow.parser.DateTimeParser().parse_iso('2021-10-12T14:30:00')
        datetime.datetime(2021, 10, 12, 14, 30)

        """
        pass

    def parse(
        self,
        datetime_string: str,
        fmt: Union[List[str], str],
        normalize_whitespace: bool = False,
    ) -> datetime:
        """
        Parses a datetime string using a specified format.

        :param datetime_string: The datetime string to parse.
        :param fmt: The format string or list of format strings to use for parsing.
        :param normalize_whitespace: Whether to normalize whitespace in the datetime string (default is False).
        :type datetime_string: str
        :type fmt: Union[List[str], str]
        :type normalize_whitespace: bool
        :returns: The parsed datetime object.
        :rtype: datetime
        :raises ParserMatchError: If the datetime string does not match the specified format.

        Usage::

        >>> import arrow.parser
        >>> arrow.parser.DateTimeParser().parse('2021-10-12 14:30:00', 'YYYY-MM-DD HH:mm:ss')
        datetime.datetime(2021, 10, 12, 14, 30)


        """
        pass

    def _generate_pattern_re(self, fmt: str) -> Tuple[List[_FORMAT_TYPE], Pattern[str]]:
        """
        Generates a regular expression pattern from a format string.

        :param fmt: The format string to convert into a regular expression pattern.
        :type fmt: str
        :returns: A tuple containing a list of format tokens and the corresponding regular expression pattern.
        :rtype: Tuple[List[_FORMAT_TYPE], Pattern[str]]
        :raises ParserError: If an unrecognized token is encountered in the format string.
        """
        pass

    @overload
    def _parse_token(
        self,
        token: Literal[
            "YYYY",
            "YY",
            "MM",
            "M",
            "DDDD",
            "DDD",
            "DD",
            "D",
            "Do",
            "HH",
            "hh",
            "h",
            "H",
            "mm",
            "m",
            "ss",
            "s",
            "x",
        ],
        value: Union[str, bytes, SupportsInt, bytearray],
        parts: _Parts,
    ) -> None: ...  # pragma: no cover

    @overload
    def _parse_token(
        self,
        token: Literal["X"],
        value: Union[str, bytes, SupportsFloat, bytearray],
        parts: _Parts,
    ) -> None: ...  # pragma: no cover

    @overload
    def _parse_token(
        self,
        token: Literal["MMMM", "MMM", "dddd", "ddd", "S"],
        value: Union[str, bytes, bytearray],
        parts: _Parts,
    ) -> None: ...  # pragma: no cover

    @overload
    def _parse_token(
        self,
        token: Literal["a", "A", "ZZZ", "ZZ", "Z"],
        value: Union[str, bytes],
        parts: _Parts,
    ) -> None: ...  # pragma: no cover

    @overload
    def _parse_token(
        self,
        token: Literal["W"],
        value: Tuple[_WEEKDATE_ELEMENT, _WEEKDATE_ELEMENT, Optional[_WEEKDATE_ELEMENT]],
        parts: _Parts,
    ) -> None: ...  # pragma: no cover

    def _parse_token(
        self,
        token: Any,
        value: Any,
        parts: _Parts,
    ) -> None:
        """
        Parse a token and its value, and update the `_Parts` dictionary with the parsed values.

        The function supports several tokens, including "YYYY", "YY", "MMMM", "MMM", "MM", "M", "DDDD", "DDD", "DD", "D", "Do", "dddd", "ddd", "HH", "H", "mm", "m", "ss", "s", "S", "X", "x", "ZZZ", "ZZ", "Z", "a", "A", and "W". Each token is matched and the corresponding value is parsed and added to the `_Parts` dictionary.

        :param token: The token to parse.
        :type token: Any
        :param value: The value of the token.
        :type value: Any
        :param parts: A dictionary to update with the parsed values.
        :type parts: _Parts
        :raises ParserMatchError: If the hour token value is not between 0 and 12 inclusive for tokens "a" or "A".

        """
        pass

    @staticmethod
    def _build_datetime(parts: _Parts) -> datetime:
        """
        Build a datetime object from a dictionary of date parts.

        :param parts: A dictionary containing the date parts extracted from a date string.
        :type parts: dict
        :return: A datetime object representing the date and time.
        :rtype: datetime.datetime
        """
        pass

    def _parse_multiformat(self, string: str, formats: Iterable[str]) -> datetime:
        """
        Parse a date and time string using multiple formats.

        Tries to parse the provided string with each format in the given `formats`
        iterable, returning the resulting `datetime` object if a match is found. If no
        format matches the string, a `ParserError` is raised.

        :param string: The date and time string to parse.
        :type string: str
        :param formats: An iterable of date and time format strings to try, in order.
        :type formats: Iterable[str]
        :returns: The parsed date and time.
        :rtype: datetime.datetime
        :raises ParserError: If no format matches the input string.
        """
        pass

    # generates a capture group of choices separated by an OR operator
    @staticmethod
    def _generate_choice_re(
        choices: Iterable[str], flags: Union[int, re.RegexFlag] = 0
    ) -> Pattern[str]:
        """
        Generate a regular expression pattern that matches a choice from an iterable.

        Takes an iterable of strings (`choices`) and returns a compiled regular expression
        pattern that matches any of the choices. The pattern is created by joining the
        choices with the '|' (OR) operator, which matches any of the enclosed patterns.

        :param choices: An iterable of strings to match.
        :type choices: Iterable[str]
        :param flags: Optional regular expression flags. Default is 0.
        :type flags: Union[int, re.RegexFlag], optional
        :returns: A compiled regular expression pattern that matches any of the choices.
        :rtype: re.Pattern[str]
        """
        pass


class TzinfoParser:
    """
    Parser for timezone information.
    """

    _TZINFO_RE: ClassVar[Pattern[str]] = re.compile(
        r"^(?:\(UTC)*([\+\-])?(\d{2})(?:\:?(\d{2}))?"
    )

    @classmethod
    def parse(cls, tzinfo_string: str) -> dt_tzinfo:
        """
        Parse a timezone string and return a datetime timezone object.

        :param tzinfo_string: The timezone string to parse.
        :type tzinfo_string: str
        :returns: The parsed datetime timezone object.
        :rtype: datetime.timezone
        :raises ParserError: If the timezone string cannot be parsed.
        """
        pass
