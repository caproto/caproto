"""
typing functions back-ported from 3.8 for Python 3.7 compatibility.
"""

import collections
import sys
import typing

if sys.version_info >= (3, 8):
    from typing import get_args, get_origin
elif sys.version_info <= (3, 6) or not hasattr(typing, '_GenericAlias'):
    raise ImportError('Sorry, this is an unsupported version of Python :(')
else:
    def get_origin(tp):
        """Get the unsubscripted version of a type.
        This supports generic types, Callable, Tuple, Union, Literal, Final and ClassVar.
        Return None for unsupported types. Examples::
            get_origin(Literal[42]) is Literal
            get_origin(int) is None
            get_origin(ClassVar[int]) is ClassVar
            get_origin(Generic) is Generic
            get_origin(Generic[T]) is Generic
            get_origin(Union[T, int]) is Union
            get_origin(List[Tuple[T, T]][int]) == list
        """
        if isinstance(tp, typing._GenericAlias):
            return tp.__origin__
        if tp is typing.Generic:
            return typing.Generic
        return None

    def get_args(tp):
        """Get type arguments with all substitutions performed.
        For unions, basic simplifications used by Union constructor are performed.
        Examples::
            get_args(Dict[str, int]) == (str, int)
            get_args(int) == ()
            get_args(Union[int, Union[T, int], str][int]) == (int, str)
            get_args(Union[int, Tuple[T, int]][str]) == (int, Tuple[str, int])
            get_args(Callable[[], T][int]) == ([], int)
        """
        if isinstance(tp, typing._GenericAlias) and not tp._special:
            res = tp.__args__
            if get_origin(tp) is collections.abc.Callable and res[0] is not typing.Ellipsis:
                res = (list(res[:-1]), res[-1])
            return res
        return ()
