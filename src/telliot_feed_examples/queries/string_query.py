""" :mod:`telliot_feed_examples.queries.string_query`

"""
# Copyright (c) 2021-, Tellor Development Community
# Distributed under the terms of the MIT License.
from dataclasses import dataclass

from telliot_feed_examples.dtypes.value_type import ValueType
from telliot_feed_examples.queries.json_query import JsonQuery


@dataclass
class StringQuery(JsonQuery):
    """Static Oracle Query

    A text query supports a question in the form of an arbitrary
    text.
    """

    #: Static query text
    text: str

    @property
    def value_type(self) -> ValueType:
        """Returns a default text response type."""
        return ValueType(abi_type="string", packed=False)
