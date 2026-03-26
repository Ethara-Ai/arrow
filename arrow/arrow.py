"""
Provides the :class:`Arrow <arrow.arrow.Arrow>` class, an enhanced ``datetime``
replacement.

"""

import calendar
import re
import sys
from datetime import date as dt_date
from datetime import datetime as dt_datetime
from datetime import time as dt_time
from datetime import timedelta, timezone
from datetime import tzinfo as dt_tzinfo
from math import trunc
from time import struct_time
from typing import (
    Any,
    ClassVar,
    Final,
    Generator,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Tuple,
    Union,
    cast,
    overload,
)

from dateutil import tz as dateutil_tz
from dateutil.relativedelta import relativedelta

from arrow import formatter, locales, parser, util
from arrow.constants import DEFAULT_LOCALE, DEHUMANIZE_LOCALES
from arrow.locales import TimeFrameLiteral

TZ_EXPR = Union[dt_tzinfo, str]

_T_FRAMES = Literal[
    "year",
    "years",
    "month",
    "months",
    "day",
    "days",
    "hour",
    "hours",
    "minute",
    "minutes",
    "second",
    "seconds",
    "microsecond",
    "microseconds",
    "week",
    "weeks",
    "quarter",
    "quarters",
]

_BOUNDS = Literal["[)", "()", "(]", "[]"]

_GRANULARITY = Literal[
    "auto",
    "second",
    "minute",
    "hour",
    "day",
    "week",
    "month",
    "quarter",
    "year",
]


class Arrow:
    """An :class:`Arrow <arrow.arrow.Arrow>` object.

    Implements the ``datetime`` interface, behaving as an aware ``datetime`` while implementing
    additional functionality.

    :param year: the calendar year.
    :param month: the calendar month.
    :param day: the calendar day.
    :param hour: (optional) the hour. Defaults to 0.
    :param minute: (optional) the minute, Defaults to 0.
    :param second: (optional) the second, Defaults to 0.
    :param microsecond: (optional) the microsecond. Defaults to 0.
    :param tzinfo: (optional) A timezone expression.  Defaults to UTC.
    :param fold: (optional) 0 or 1, used to disambiguate repeated wall times. Defaults to 0.

    .. _tz-expr:

    Recognized timezone expressions:

        - A ``tzinfo`` object.
        - A ``str`` describing a timezone, similar to 'US/Pacific', or 'Europe/Berlin'.
        - A ``str`` in ISO 8601 style, as in '+07:00'.
        - A ``str``, one of the following:  'local', 'utc', 'UTC'.

    Usage::

        >>> import arrow
        >>> arrow.Arrow(2013, 5, 5, 12, 30, 45)
        <Arrow [2013-05-05T12:30:45+00:00]>

    """

    resolution: ClassVar[timedelta] = dt_datetime.resolution
    min: ClassVar["Arrow"]
    max: ClassVar["Arrow"]

    _ATTRS: Final[List[str]] = [
        "year",
        "month",
        "day",
        "hour",
        "minute",
        "second",
        "microsecond",
    ]
    _ATTRS_PLURAL: Final[List[str]] = [f"{a}s" for a in _ATTRS]
    _MONTHS_PER_QUARTER: Final[int] = 3
    _MONTHS_PER_YEAR: Final[int] = 12
    _SECS_PER_MINUTE: Final[int] = 60
    _SECS_PER_HOUR: Final[int] = 60 * 60
    _SECS_PER_DAY: Final[int] = 60 * 60 * 24
    _SECS_PER_WEEK: Final[int] = 60 * 60 * 24 * 7
    _SECS_PER_MONTH: Final[float] = 60 * 60 * 24 * 30.5
    _SECS_PER_QUARTER: Final[float] = 60 * 60 * 24 * 30.5 * 3
    _SECS_PER_YEAR: Final[int] = 60 * 60 * 24 * 365

    _SECS_MAP: Final[Mapping[TimeFrameLiteral, float]] = {
        "second": 1.0,
        "minute": _SECS_PER_MINUTE,
        "hour": _SECS_PER_HOUR,
        "day": _SECS_PER_DAY,
        "week": _SECS_PER_WEEK,
        "month": _SECS_PER_MONTH,
        "quarter": _SECS_PER_QUARTER,
        "year": _SECS_PER_YEAR,
    }

    _datetime: dt_datetime

    def __init__(
        self,
        year: int,
        month: int,
        day: int,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
        microsecond: int = 0,
        tzinfo: Optional[TZ_EXPR] = None,
        **kwargs: Any,
    ) -> None:
        if tzinfo is None:
            tzinfo = timezone.utc
        # detect that tzinfo is a pytz object (issue #626)
        elif (
            isinstance(tzinfo, dt_tzinfo)
            and hasattr(tzinfo, "localize")
            and hasattr(tzinfo, "zone")
            and tzinfo.zone
        ):
            tzinfo = parser.TzinfoParser.parse(tzinfo.zone)
        elif isinstance(tzinfo, str):
            tzinfo = parser.TzinfoParser.parse(tzinfo)

        fold = kwargs.get("fold", 0)

        self._datetime = dt_datetime(
            year, month, day, hour, minute, second, microsecond, tzinfo, fold=fold
        )

    # factories: single object, both original and from datetime.

    @classmethod
    def now(cls, tzinfo: Optional[dt_tzinfo] = None) -> "Arrow":
        """Constructs an :class:`Arrow <arrow.arrow.Arrow>` object, representing "now" in the given
        timezone.

        :param tzinfo: (optional) a ``tzinfo`` object. Defaults to local time.

        Usage::

            >>> arrow.now('Asia/Baku')
            <Arrow [2019-01-24T20:26:31.146412+04:00]>

        """
        pass

    @classmethod
    def utcnow(cls) -> "Arrow":
        """Constructs an :class:`Arrow <arrow.arrow.Arrow>` object, representing "now" in UTC
        time.

        Usage::

            >>> arrow.utcnow()
            <Arrow [2019-01-24T16:31:40.651108+00:00]>

        """
        pass

    @classmethod
    def fromtimestamp(
        cls,
        timestamp: Union[int, float, str],
        tzinfo: Optional[TZ_EXPR] = None,
    ) -> "Arrow":
        """Constructs an :class:`Arrow <arrow.arrow.Arrow>` object from a timestamp, converted to
        the given timezone.

        :param timestamp: an ``int`` or ``float`` timestamp, or a ``str`` that converts to either.
        :param tzinfo: (optional) a ``tzinfo`` object.  Defaults to local time.

        """
        pass

    @classmethod
    def utcfromtimestamp(cls, timestamp: Union[int, float, str]) -> "Arrow":
        """Constructs an :class:`Arrow <arrow.arrow.Arrow>` object from a timestamp, in UTC time.

        :param timestamp: an ``int`` or ``float`` timestamp, or a ``str`` that converts to either.

        """
        pass

    @classmethod
    def fromdatetime(cls, dt: dt_datetime, tzinfo: Optional[TZ_EXPR] = None) -> "Arrow":
        """Constructs an :class:`Arrow <arrow.arrow.Arrow>` object from a ``datetime`` and
        optional replacement timezone.

        :param dt: the ``datetime``
        :param tzinfo: (optional) A :ref:`timezone expression <tz-expr>`.  Defaults to ``dt``'s
            timezone, or UTC if naive.

        Usage::

            >>> dt
            datetime.datetime(2021, 4, 7, 13, 48, tzinfo=tzfile('/usr/share/zoneinfo/US/Pacific'))
            >>> arrow.Arrow.fromdatetime(dt)
            <Arrow [2021-04-07T13:48:00-07:00]>

        """
        pass

    @classmethod
    def fromdate(cls, date: dt_date, tzinfo: Optional[TZ_EXPR] = None) -> "Arrow":
        """Constructs an :class:`Arrow <arrow.arrow.Arrow>` object from a ``date`` and optional
        replacement timezone.  All time values are set to 0.

        :param date: the ``date``
        :param tzinfo: (optional) A :ref:`timezone expression <tz-expr>`.  Defaults to UTC.

        """
        pass

    @classmethod
    def strptime(
        cls, date_str: str, fmt: str, tzinfo: Optional[TZ_EXPR] = None
    ) -> "Arrow":
        """Constructs an :class:`Arrow <arrow.arrow.Arrow>` object from a date string and format,
        in the style of ``datetime.strptime``.  Optionally replaces the parsed timezone.

        :param date_str: the date string.
        :param fmt: the format string using datetime format codes.
        :param tzinfo: (optional) A :ref:`timezone expression <tz-expr>`.  Defaults to the parsed
            timezone if ``fmt`` contains a timezone directive, otherwise UTC.

        Usage::

            >>> arrow.Arrow.strptime('20-01-2019 15:49:10', '%d-%m-%Y %H:%M:%S')
            <Arrow [2019-01-20T15:49:10+00:00]>

        """
        pass

    @classmethod
    def fromordinal(cls, ordinal: int) -> "Arrow":
        """Constructs an :class:`Arrow <arrow.arrow.Arrow>` object corresponding
            to the Gregorian Ordinal.

        :param ordinal: an ``int`` corresponding to a Gregorian Ordinal.

        Usage::

            >>> arrow.fromordinal(737741)
            <Arrow [2020-11-12T00:00:00+00:00]>

        """
        pass

    # factories: ranges and spans

    @classmethod
    def range(
        cls,
        frame: _T_FRAMES,
        start: Union["Arrow", dt_datetime],
        end: Union["Arrow", dt_datetime, None] = None,
        tz: Optional[TZ_EXPR] = None,
        limit: Optional[int] = None,
    ) -> Generator["Arrow", None, None]:
        """Returns an iterator of :class:`Arrow <arrow.arrow.Arrow>` objects, representing
        points in time between two inputs.

        :param frame: The timeframe.  Can be any ``datetime`` property (day, hour, minute...).
        :param start: A datetime expression, the start of the range.
        :param end: (optional) A datetime expression, the end of the range.
        :param tz: (optional) A :ref:`timezone expression <tz-expr>`.  Defaults to
            ``start``'s timezone, or UTC if ``start`` is naive.
        :param limit: (optional) A maximum number of tuples to return.

        **NOTE**: The ``end`` or ``limit`` must be provided.  Call with ``end`` alone to
        return the entire range.  Call with ``limit`` alone to return a maximum # of results from
        the start.  Call with both to cap a range at a maximum # of results.

        **NOTE**: ``tz`` internally **replaces** the timezones of both ``start`` and ``end`` before
        iterating.  As such, either call with naive objects and ``tz``, or aware objects from the
        same timezone and no ``tz``.

        Supported frame values: year, quarter, month, week, day, hour, minute, second, microsecond.

        Recognized datetime expressions:

            - An :class:`Arrow <arrow.arrow.Arrow>` object.
            - A ``datetime`` object.

        Usage::

            >>> start = datetime(2013, 5, 5, 12, 30)
            >>> end = datetime(2013, 5, 5, 17, 15)
            >>> for r in arrow.Arrow.range('hour', start, end):
            ...     print(repr(r))
            ...
            <Arrow [2013-05-05T12:30:00+00:00]>
            <Arrow [2013-05-05T13:30:00+00:00]>
            <Arrow [2013-05-05T14:30:00+00:00]>
            <Arrow [2013-05-05T15:30:00+00:00]>
            <Arrow [2013-05-05T16:30:00+00:00]>

        **NOTE**: Unlike Python's ``range``, ``end`` *may* be included in the returned iterator::

            >>> start = datetime(2013, 5, 5, 12, 30)
            >>> end = datetime(2013, 5, 5, 13, 30)
            >>> for r in arrow.Arrow.range('hour', start, end):
            ...     print(repr(r))
            ...
            <Arrow [2013-05-05T12:30:00+00:00]>
            <Arrow [2013-05-05T13:30:00+00:00]>

        """
        pass

    def span(
        self,
        frame: _T_FRAMES,
        count: int = 1,
        bounds: _BOUNDS = "[)",
        exact: bool = False,
        week_start: int = 1,
    ) -> Tuple["Arrow", "Arrow"]:
        """Returns a tuple of two new :class:`Arrow <arrow.arrow.Arrow>` objects, representing the timespan
        of the :class:`Arrow <arrow.arrow.Arrow>` object in a given timeframe.

        :param frame: the timeframe.  Can be any ``datetime`` property (day, hour, minute...).
        :param count: (optional) the number of frames to span.
        :param bounds: (optional) a ``str`` of either '()', '(]', '[)', or '[]' that specifies
            whether to include or exclude the start and end values in the span. '(' excludes
            the start, '[' includes the start, ')' excludes the end, and ']' includes the end.
            If the bounds are not specified, the default bound '[)' is used.
        :param exact: (optional) whether to have the start of the timespan begin exactly
            at the time specified by ``start`` and the end of the timespan truncated
            so as not to extend beyond ``end``.
        :param week_start: (optional) only used in combination with the week timeframe. Follows isoweekday() where
            Monday is 1 and Sunday is 7.

        Supported frame values: year, quarter, month, week, day, hour, minute, second.

        Usage::

            >>> arrow.utcnow()
            <Arrow [2013-05-09T03:32:36.186203+00:00]>

            >>> arrow.utcnow().span('hour')
            (<Arrow [2013-05-09T03:00:00+00:00]>, <Arrow [2013-05-09T03:59:59.999999+00:00]>)

            >>> arrow.utcnow().span('day')
            (<Arrow [2013-05-09T00:00:00+00:00]>, <Arrow [2013-05-09T23:59:59.999999+00:00]>)

            >>> arrow.utcnow().span('day', count=2)
            (<Arrow [2013-05-09T00:00:00+00:00]>, <Arrow [2013-05-10T23:59:59.999999+00:00]>)

            >>> arrow.utcnow().span('day', bounds='[]')
            (<Arrow [2013-05-09T00:00:00+00:00]>, <Arrow [2013-05-10T00:00:00+00:00]>)

            >>> arrow.utcnow().span('week')
            (<Arrow [2021-02-22T00:00:00+00:00]>, <Arrow [2021-02-28T23:59:59.999999+00:00]>)

            >>> arrow.utcnow().span('week', week_start=6)
            (<Arrow [2021-02-20T00:00:00+00:00]>, <Arrow [2021-02-26T23:59:59.999999+00:00]>)

        """
        pass

    def floor(self, frame: _T_FRAMES, **kwargs: Any) -> "Arrow":
        """Returns a new :class:`Arrow <arrow.arrow.Arrow>` object, representing the "floor"
        of the timespan of the :class:`Arrow <arrow.arrow.Arrow>` object in a given timeframe.
        Equivalent to the first element in the 2-tuple returned by
        :func:`span <arrow.arrow.Arrow.span>`.

        :param frame: the timeframe.  Can be any ``datetime`` property (day, hour, minute...).
        :param week_start: (optional) only used in combination with the week timeframe. Follows isoweekday() where
            Monday is 1 and Sunday is 7.

        Usage::

            >>> arrow.utcnow().floor('hour')
            <Arrow [2013-05-09T03:00:00+00:00]>

            >>> arrow.utcnow().floor('week', week_start=7)
            <Arrow [2021-02-21T00:00:00+00:00]>

        """
        pass

    def ceil(self, frame: _T_FRAMES, **kwargs: Any) -> "Arrow":
        """Returns a new :class:`Arrow <arrow.arrow.Arrow>` object, representing the "ceiling"
        of the timespan of the :class:`Arrow <arrow.arrow.Arrow>` object in a given timeframe.
        Equivalent to the second element in the 2-tuple returned by
        :func:`span <arrow.arrow.Arrow.span>`.

        :param frame: the timeframe.  Can be any ``datetime`` property (day, hour, minute...).
        :param week_start: (optional) only used in combination with the week timeframe. Follows isoweekday() where
            Monday is 1 and Sunday is 7.

        Usage::

            >>> arrow.utcnow().ceil('hour')
            <Arrow [2013-05-09T03:59:59.999999+00:00]>

            >>> arrow.utcnow().ceil('week', week_start=7)
            <Arrow [2021-02-27T23:59:59.999999+00:00]>

        """
        pass

    @classmethod
    def span_range(
        cls,
        frame: _T_FRAMES,
        start: dt_datetime,
        end: dt_datetime,
        tz: Optional[TZ_EXPR] = None,
        limit: Optional[int] = None,
        bounds: _BOUNDS = "[)",
        exact: bool = False,
    ) -> Iterable[Tuple["Arrow", "Arrow"]]:
        """Returns an iterator of tuples, each :class:`Arrow <arrow.arrow.Arrow>` objects,
        representing a series of timespans between two inputs.

        :param frame: The timeframe.  Can be any ``datetime`` property (day, hour, minute...).
        :param start: A datetime expression, the start of the range.
        :param end: (optional) A datetime expression, the end of the range.
        :param tz: (optional) A :ref:`timezone expression <tz-expr>`.  Defaults to
            ``start``'s timezone, or UTC if ``start`` is naive.
        :param limit: (optional) A maximum number of tuples to return.
        :param bounds: (optional) a ``str`` of either '()', '(]', '[)', or '[]' that specifies
            whether to include or exclude the start and end values in each span in the range. '(' excludes
            the start, '[' includes the start, ')' excludes the end, and ']' includes the end.
            If the bounds are not specified, the default bound '[)' is used.
        :param exact: (optional) whether to have the first timespan start exactly
            at the time specified by ``start`` and the final span truncated
            so as not to extend beyond ``end``.

        **NOTE**: The ``end`` or ``limit`` must be provided.  Call with ``end`` alone to
        return the entire range.  Call with ``limit`` alone to return a maximum # of results from
        the start.  Call with both to cap a range at a maximum # of results.

        **NOTE**: ``tz`` internally **replaces** the timezones of both ``start`` and ``end`` before
        iterating.  As such, either call with naive objects and ``tz``, or aware objects from the
        same timezone and no ``tz``.

        Supported frame values: year, quarter, month, week, day, hour, minute, second, microsecond.

        Recognized datetime expressions:

            - An :class:`Arrow <arrow.arrow.Arrow>` object.
            - A ``datetime`` object.

        **NOTE**: Unlike Python's ``range``, ``end`` will *always* be included in the returned
        iterator of timespans.

        Usage:

            >>> start = datetime(2013, 5, 5, 12, 30)
            >>> end = datetime(2013, 5, 5, 17, 15)
            >>> for r in arrow.Arrow.span_range('hour', start, end):
            ...     print(r)
            ...
            (<Arrow [2013-05-05T12:00:00+00:00]>, <Arrow [2013-05-05T12:59:59.999999+00:00]>)
            (<Arrow [2013-05-05T13:00:00+00:00]>, <Arrow [2013-05-05T13:59:59.999999+00:00]>)
            (<Arrow [2013-05-05T14:00:00+00:00]>, <Arrow [2013-05-05T14:59:59.999999+00:00]>)
            (<Arrow [2013-05-05T15:00:00+00:00]>, <Arrow [2013-05-05T15:59:59.999999+00:00]>)
            (<Arrow [2013-05-05T16:00:00+00:00]>, <Arrow [2013-05-05T16:59:59.999999+00:00]>)
            (<Arrow [2013-05-05T17:00:00+00:00]>, <Arrow [2013-05-05T17:59:59.999999+00:00]>)

        """
        pass

    @classmethod
    def interval(
        cls,
        frame: _T_FRAMES,
        start: dt_datetime,
        end: dt_datetime,
        interval: int = 1,
        tz: Optional[TZ_EXPR] = None,
        bounds: _BOUNDS = "[)",
        exact: bool = False,
    ) -> Iterable[Tuple["Arrow", "Arrow"]]:
        """Returns an iterator of tuples, each :class:`Arrow <arrow.arrow.Arrow>` objects,
        representing a series of intervals between two inputs.

        :param frame: The timeframe.  Can be any ``datetime`` property (day, hour, minute...).
        :param start: A datetime expression, the start of the range.
        :param end: (optional) A datetime expression, the end of the range.
        :param interval: (optional) Time interval for the given time frame.
        :param tz: (optional) A timezone expression.  Defaults to UTC.
        :param bounds: (optional) a ``str`` of either '()', '(]', '[)', or '[]' that specifies
            whether to include or exclude the start and end values in the intervals. '(' excludes
            the start, '[' includes the start, ')' excludes the end, and ']' includes the end.
            If the bounds are not specified, the default bound '[)' is used.
        :param exact: (optional) whether to have the first timespan start exactly
            at the time specified by ``start`` and the final interval truncated
            so as not to extend beyond ``end``.

        Supported frame values: year, quarter, month, week, day, hour, minute, second

        Recognized datetime expressions:

            - An :class:`Arrow <arrow.arrow.Arrow>` object.
            - A ``datetime`` object.

        Recognized timezone expressions:

            - A ``tzinfo`` object.
            - A ``str`` describing a timezone, similar to 'US/Pacific', or 'Europe/Berlin'.
            - A ``str`` in ISO 8601 style, as in '+07:00'.
            - A ``str``, one of the following:  'local', 'utc', 'UTC'.

        Usage:

            >>> start = datetime(2013, 5, 5, 12, 30)
            >>> end = datetime(2013, 5, 5, 17, 15)
            >>> for r in arrow.Arrow.interval('hour', start, end, 2):
            ...     print(r)
            ...
            (<Arrow [2013-05-05T12:00:00+00:00]>, <Arrow [2013-05-05T13:59:59.999999+00:00]>)
            (<Arrow [2013-05-05T14:00:00+00:00]>, <Arrow [2013-05-05T15:59:59.999999+00:00]>)
            (<Arrow [2013-05-05T16:00:00+00:00]>, <Arrow [2013-05-05T17:59:59.999999+00:0]>)
        """
        pass

    # representations

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} [{self.__str__()}]>"

    def __str__(self) -> str:
        return self._datetime.isoformat()

    def __format__(self, formatstr: str) -> str:
        if len(formatstr) > 0:
            return self.format(formatstr)

        return str(self)

    def __hash__(self) -> int:
        return self._datetime.__hash__()

    # attributes and properties

    def __getattr__(self, name: str) -> Any:
        if name == "week":
            return self.isocalendar()[1]

        if name == "quarter":
            return int((self.month - 1) / self._MONTHS_PER_QUARTER) + 1

        if not name.startswith("_"):
            value: Optional[Any] = getattr(self._datetime, name, None)

            if value is not None:
                return value

        return cast(int, object.__getattribute__(self, name))

    @property
    def tzinfo(self) -> dt_tzinfo:
        """Gets the ``tzinfo`` of the :class:`Arrow <arrow.arrow.Arrow>` object.

        Usage::

            >>> arw=arrow.utcnow()
            >>> arw.tzinfo
            tzutc()

        """
        pass

    @property
    def datetime(self) -> dt_datetime:
        """Returns a datetime representation of the :class:`Arrow <arrow.arrow.Arrow>` object.

        Usage::

            >>> arw=arrow.utcnow()
            >>> arw.datetime
            datetime.datetime(2019, 1, 24, 16, 35, 27, 276649, tzinfo=tzutc())

        """
        pass

    @property
    def naive(self) -> dt_datetime:
        """Returns a naive datetime representation of the :class:`Arrow <arrow.arrow.Arrow>`
        object.

        Usage::

            >>> nairobi = arrow.now('Africa/Nairobi')
            >>> nairobi
            <Arrow [2019-01-23T19:27:12.297999+03:00]>
            >>> nairobi.naive
            datetime.datetime(2019, 1, 23, 19, 27, 12, 297999)

        """
        pass

    def timestamp(self) -> float:
        """Returns a timestamp representation of the :class:`Arrow <arrow.arrow.Arrow>` object, in
        UTC time.

        Usage::

            >>> arrow.utcnow().timestamp()
            1616882340.256501

        """
        pass

    @property
    def int_timestamp(self) -> int:
        """Returns an integer timestamp representation of the :class:`Arrow <arrow.arrow.Arrow>` object, in
        UTC time.

        Usage::

            >>> arrow.utcnow().int_timestamp
            1548260567

        """
        pass

    @property
    def float_timestamp(self) -> float:
        """Returns a floating-point timestamp representation of the :class:`Arrow <arrow.arrow.Arrow>`
        object, in UTC time.

        Usage::

            >>> arrow.utcnow().float_timestamp
            1548260516.830896

        """
        pass

    @property
    def fold(self) -> int:
        """Returns the ``fold`` value of the :class:`Arrow <arrow.arrow.Arrow>` object."""
        pass

    @property
    def ambiguous(self) -> bool:
        """Indicates whether the :class:`Arrow <arrow.arrow.Arrow>` object is a repeated wall time in the current
        timezone.

        """
        pass

    @property
    def imaginary(self) -> bool:
        """Indicates whether the :class: `Arrow <arrow.arrow.Arrow>` object exists in the current timezone."""
        pass

    # mutation and duplication.

    def clone(self) -> "Arrow":
        """Returns a new :class:`Arrow <arrow.arrow.Arrow>` object, cloned from the current one.

        Usage:

            >>> arw = arrow.utcnow()
            >>> cloned = arw.clone()

        """
        pass

    def replace(self, **kwargs: Any) -> "Arrow":
        """Returns a new :class:`Arrow <arrow.arrow.Arrow>` object with attributes updated
        according to inputs.

        Use property names to set their value absolutely::

            >>> import arrow
            >>> arw = arrow.utcnow()
            >>> arw
            <Arrow [2013-05-11T22:27:34.787885+00:00]>
            >>> arw.replace(year=2014, month=6)
            <Arrow [2014-06-11T22:27:34.787885+00:00]>

        You can also replace the timezone without conversion, using a
        :ref:`timezone expression <tz-expr>`::

            >>> arw.replace(tzinfo=tz.tzlocal())
            <Arrow [2013-05-11T22:27:34.787885-07:00]>

        """
        pass

    def shift(self, check_imaginary: bool = True, **kwargs: Any) -> "Arrow":
        """Returns a new :class:`Arrow <arrow.arrow.Arrow>` object with attributes updated
        according to inputs.

        Parameters:
        check_imaginary (bool): If True (default), will check for and resolve
        imaginary times (like during DST transitions). If False, skips this check.


        Use pluralized property names to relatively shift their current value:

        >>> import arrow
        >>> arw = arrow.utcnow()
        >>> arw
        <Arrow [2013-05-11T22:27:34.787885+00:00]>
        >>> arw.shift(years=1, months=-1)
        <Arrow [2014-04-11T22:27:34.787885+00:00]>

        Day-of-the-week relative shifting can use either Python's weekday numbers
        (Monday = 0, Tuesday = 1 .. Sunday = 6) or using dateutil.relativedelta's
        day instances (MO, TU .. SU).  When using weekday numbers, the returned
        date will always be greater than or equal to the starting date.

        Using the above code (which is a Saturday) and asking it to shift to Saturday:

        >>> arw.shift(weekday=5)
        <Arrow [2013-05-11T22:27:34.787885+00:00]>

        While asking for a Monday:

        >>> arw.shift(weekday=0)
        <Arrow [2013-05-13T22:27:34.787885+00:00]>

        """
        pass

    def to(self, tz: TZ_EXPR) -> "Arrow":
        """Returns a new :class:`Arrow <arrow.arrow.Arrow>` object, converted
        to the target timezone.

        :param tz: A :ref:`timezone expression <tz-expr>`.

        Usage::

            >>> utc = arrow.utcnow()
            >>> utc
            <Arrow [2013-05-09T03:49:12.311072+00:00]>

            >>> utc.to('US/Pacific')
            <Arrow [2013-05-08T20:49:12.311072-07:00]>

            >>> utc.to(tz.tzlocal())
            <Arrow [2013-05-08T20:49:12.311072-07:00]>

            >>> utc.to('-07:00')
            <Arrow [2013-05-08T20:49:12.311072-07:00]>

            >>> utc.to('local')
            <Arrow [2013-05-08T20:49:12.311072-07:00]>

            >>> utc.to('local').to('utc')
            <Arrow [2013-05-09T03:49:12.311072+00:00]>

        """
        pass

    # string output and formatting

    def format(
        self, fmt: str = "YYYY-MM-DD HH:mm:ssZZ", locale: str = DEFAULT_LOCALE
    ) -> str:
        """Returns a string representation of the :class:`Arrow <arrow.arrow.Arrow>` object,
        formatted according to the provided format string. For a list of formatting values,
        see :ref:`supported-tokens`

        :param fmt: the format string.
        :param locale: the locale to format.

        Usage::

            >>> arrow.utcnow().format('YYYY-MM-DD HH:mm:ss ZZ')
            '2013-05-09 03:56:47 -00:00'

            >>> arrow.utcnow().format('X')
            '1368071882'

            >>> arrow.utcnow().format('MMMM DD, YYYY')
            'May 09, 2013'

            >>> arrow.utcnow().format()
            '2013-05-09 03:56:47 -00:00'

        """
        pass

    def humanize(
        self,
        other: Union["Arrow", dt_datetime, None] = None,
        locale: str = DEFAULT_LOCALE,
        only_distance: bool = False,
        granularity: Union[_GRANULARITY, List[_GRANULARITY]] = "auto",
    ) -> str:
        """Returns a localized, humanized representation of a relative difference in time.

        :param other: (optional) an :class:`Arrow <arrow.arrow.Arrow>` or ``datetime`` object.
            Defaults to now in the current :class:`Arrow <arrow.arrow.Arrow>` object's timezone.
        :param locale: (optional) a ``str`` specifying a locale.  Defaults to 'en-us'.
        :param only_distance: (optional) returns only time difference eg: "11 seconds" without "in" or "ago" part.
        :param granularity: (optional) defines the precision of the output. Set it to strings 'second', 'minute',
                           'hour', 'day', 'week', 'month' or 'year' or a list of any combination of these strings

        Usage::

            >>> earlier = arrow.utcnow().shift(hours=-2)
            >>> earlier.humanize()
            '2 hours ago'

            >>> later = earlier.shift(hours=4)
            >>> later.humanize(earlier)
            'in 4 hours'

        """
        pass

    def dehumanize(self, input_string: str, locale: str = "en_us") -> "Arrow":
        """Returns a new :class:`Arrow <arrow.arrow.Arrow>` object, that represents
        the time difference relative to the attributes of the
        :class:`Arrow <arrow.arrow.Arrow>` object.

        :param timestring: a ``str`` representing a humanized relative time.
        :param locale: (optional) a ``str`` specifying a locale.  Defaults to 'en-us'.

        Usage::

                >>> arw = arrow.utcnow()
                >>> arw
                <Arrow [2021-04-20T22:27:34.787885+00:00]>
                >>> earlier = arw.dehumanize("2 days ago")
                >>> earlier
                <Arrow [2021-04-18T22:27:34.787885+00:00]>

                >>> arw = arrow.utcnow()
                >>> arw
                <Arrow [2021-04-20T22:27:34.787885+00:00]>
                >>> later = arw.dehumanize("in a month")
                >>> later
                <Arrow [2021-05-18T22:27:34.787885+00:00]>

        """
        pass

    # query functions

    def is_between(
        self,
        start: "Arrow",
        end: "Arrow",
        bounds: _BOUNDS = "()",
    ) -> bool:
        """Returns a boolean denoting whether the :class:`Arrow <arrow.arrow.Arrow>` object is between
        the start and end limits.

        :param start: an :class:`Arrow <arrow.arrow.Arrow>` object.
        :param end: an :class:`Arrow <arrow.arrow.Arrow>` object.
        :param bounds: (optional) a ``str`` of either '()', '(]', '[)', or '[]' that specifies
            whether to include or exclude the start and end values in the range. '(' excludes
            the start, '[' includes the start, ')' excludes the end, and ']' includes the end.
            If the bounds are not specified, the default bound '()' is used.

        Usage::

            >>> start = arrow.get(datetime(2013, 5, 5, 12, 30, 10))
            >>> end = arrow.get(datetime(2013, 5, 5, 12, 30, 36))
            >>> arrow.get(datetime(2013, 5, 5, 12, 30, 27)).is_between(start, end)
            True

            >>> start = arrow.get(datetime(2013, 5, 5))
            >>> end = arrow.get(datetime(2013, 5, 8))
            >>> arrow.get(datetime(2013, 5, 8)).is_between(start, end, '[]')
            True

            >>> start = arrow.get(datetime(2013, 5, 5))
            >>> end = arrow.get(datetime(2013, 5, 8))
            >>> arrow.get(datetime(2013, 5, 8)).is_between(start, end, '[)')
            False

        """
        pass

    # datetime methods

    def date(self) -> dt_date:
        """Returns a ``date`` object with the same year, month and day.

        Usage::

            >>> arrow.utcnow().date()
            datetime.date(2019, 1, 23)

        """
        pass

    def time(self) -> dt_time:
        """Returns a ``time`` object with the same hour, minute, second, microsecond.

        Usage::

            >>> arrow.utcnow().time()
            datetime.time(12, 15, 34, 68352)

        """
        pass

    def timetz(self) -> dt_time:
        """Returns a ``time`` object with the same hour, minute, second, microsecond and
        tzinfo.

        Usage::

            >>> arrow.utcnow().timetz()
            datetime.time(12, 5, 18, 298893, tzinfo=tzutc())

        """
        pass

    def astimezone(self, tz: Optional[dt_tzinfo]) -> dt_datetime:
        """Returns a ``datetime`` object, converted to the specified timezone.

        :param tz: a ``tzinfo`` object.

        Usage::

            >>> pacific=arrow.now('US/Pacific')
            >>> nyc=arrow.now('America/New_York').tzinfo
            >>> pacific.astimezone(nyc)
            datetime.datetime(2019, 1, 20, 10, 24, 22, 328172, tzinfo=tzfile('/usr/share/zoneinfo/America/New_York'))

        """
        pass

    def utcoffset(self) -> Optional[timedelta]:
        """Returns a ``timedelta`` object representing the whole number of minutes difference from
        UTC time.

        Usage::

            >>> arrow.now('US/Pacific').utcoffset()
            datetime.timedelta(-1, 57600)

        """
        pass

    def dst(self) -> Optional[timedelta]:
        """Returns the daylight savings time adjustment.

        Usage::

            >>> arrow.utcnow().dst()
            datetime.timedelta(0)

        """
        pass

    def timetuple(self) -> struct_time:
        """Returns a ``time.struct_time``, in the current timezone.

        Usage::

            >>> arrow.utcnow().timetuple()
            time.struct_time(tm_year=2019, tm_mon=1, tm_mday=20, tm_hour=15, tm_min=17, tm_sec=8, tm_wday=6, tm_yday=20, tm_isdst=0)

        """
        pass

    def utctimetuple(self) -> struct_time:
        """Returns a ``time.struct_time``, in UTC time.

        Usage::

            >>> arrow.utcnow().utctimetuple()
            time.struct_time(tm_year=2019, tm_mon=1, tm_mday=19, tm_hour=21, tm_min=41, tm_sec=7, tm_wday=5, tm_yday=19, tm_isdst=0)

        """
        pass

    def toordinal(self) -> int:
        """Returns the proleptic Gregorian ordinal of the date.

        Usage::

            >>> arrow.utcnow().toordinal()
            737078

        """
        pass

    def weekday(self) -> int:
        """Returns the day of the week as an integer (0-6).

        Usage::

            >>> arrow.utcnow().weekday()
            5

        """
        pass

    def isoweekday(self) -> int:
        """Returns the ISO day of the week as an integer (1-7).

        Usage::

            >>> arrow.utcnow().isoweekday()
            6

        """
        pass

    def isocalendar(self) -> Tuple[int, int, int]:
        """Returns a 3-tuple, (ISO year, ISO week number, ISO weekday).

        Usage::

            >>> arrow.utcnow().isocalendar()
            (2019, 3, 6)

        """
        pass

    def isoformat(self, sep: str = "T", timespec: str = "auto") -> str:
        """Returns an ISO 8601 formatted representation of the date and time.

        Usage::

            >>> arrow.utcnow().isoformat()
            '2019-01-19T18:30:52.442118+00:00'

        """
        pass

    def ctime(self) -> str:
        """Returns a ctime formatted representation of the date and time.

        Usage::

            >>> arrow.utcnow().ctime()
            'Sat Jan 19 18:26:50 2019'

        """
        pass

    def strftime(self, format: str) -> str:
        """Formats in the style of ``datetime.strftime``.

        :param format: the format string.

        Usage::

            >>> arrow.utcnow().strftime('%d-%m-%Y %H:%M:%S')
            '23-01-2019 12:28:17'

        """
        pass

    def for_json(self) -> str:
        """Serializes for the ``for_json`` protocol of simplejson.

        Usage::

            >>> arrow.utcnow().for_json()
            '2019-01-19T18:25:36.760079+00:00'

        """
        pass

    # math

    def __add__(self, other: Any) -> "Arrow":
        if isinstance(other, (timedelta, relativedelta)):
            return self.fromdatetime(self._datetime + other, self._datetime.tzinfo)

        return NotImplemented

    def __radd__(self, other: Union[timedelta, relativedelta]) -> "Arrow":
        return self.__add__(other)

    @overload
    def __sub__(self, other: Union[timedelta, relativedelta]) -> "Arrow":
        pass  # pragma: no cover

    @overload
    def __sub__(self, other: Union[dt_datetime, "Arrow"]) -> timedelta:
        pass  # pragma: no cover

    def __sub__(self, other: Any) -> Union[timedelta, "Arrow"]:
        if isinstance(other, (timedelta, relativedelta)):
            return self.fromdatetime(self._datetime - other, self._datetime.tzinfo)

        elif isinstance(other, dt_datetime):
            return self._datetime - other

        elif isinstance(other, Arrow):
            return self._datetime - other._datetime

        return NotImplemented

    def __rsub__(self, other: Any) -> timedelta:
        if isinstance(other, dt_datetime):
            return other - self._datetime

        return NotImplemented

    # comparisons

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, (Arrow, dt_datetime)):
            return False

        return self._datetime == self._get_datetime(other)

    def __ne__(self, other: Any) -> bool:
        if not isinstance(other, (Arrow, dt_datetime)):
            return True

        return not self.__eq__(other)

    def __gt__(self, other: Any) -> bool:
        if not isinstance(other, (Arrow, dt_datetime)):
            return NotImplemented

        return self._datetime > self._get_datetime(other)

    def __ge__(self, other: Any) -> bool:
        if not isinstance(other, (Arrow, dt_datetime)):
            return NotImplemented

        return self._datetime >= self._get_datetime(other)

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, (Arrow, dt_datetime)):
            return NotImplemented

        return self._datetime < self._get_datetime(other)

    def __le__(self, other: Any) -> bool:
        if not isinstance(other, (Arrow, dt_datetime)):
            return NotImplemented

        return self._datetime <= self._get_datetime(other)

    # internal methods
    @staticmethod
    def _get_tzinfo(tz_expr: Optional[TZ_EXPR]) -> dt_tzinfo:
        """Get normalized tzinfo object from various inputs."""
        pass

    @classmethod
    def _get_datetime(
        cls, expr: Union["Arrow", dt_datetime, int, float, str]
    ) -> dt_datetime:
        """Get datetime object from a specified expression."""
        pass

    @classmethod
    def _get_frames(cls, name: _T_FRAMES) -> Tuple[str, str, int]:
        """Finds relevant timeframe and steps for use in range and span methods.

        Returns a 3 element tuple in the form (frame, plural frame, step), for example ("day", "days", 1)

        """
        pass

    @classmethod
    def _get_iteration_params(cls, end: Any, limit: Optional[int]) -> Tuple[Any, int]:
        """Sets default end and limit values for range method."""
        pass

    @staticmethod
    def _is_last_day_of_month(date: "Arrow") -> bool:
        """Returns a boolean indicating whether the datetime is the last day of the month."""
        pass


Arrow.min = Arrow.fromdatetime(dt_datetime.min)
Arrow.max = Arrow.fromdatetime(dt_datetime.max)
