"""
Helper functions for decoding query data and submitted values.
"""
from logging import Logger
import click
import eth_abi
from typing import Any, Union, Optional

from telliot_feeds.queries.abi_query import AbiQuery
from telliot_feeds.queries.json_query import JsonQuery
from telliot_feeds.queries.legacy_query import LegacyRequest
from telliot_feeds.queries.query import OracleQuery
from telliot_feeds.queries.query_catalog import query_catalog
from telliot_core.utils.response import ResponseStatus
from telliot_core.utils.response import error_status
from telliot_feeds.queries.utils import choose_query_type


def bytes_from_string(string: str, err_msg: str, log: Union[print, click.echo, Logger] = print) -> tuple[ResponseStatus, Optional[bytes]]:
    """Ensure valid hex string and convert to bytes."""
    if len(string) > 2 and string[:2] == "0x":
        string = string[2:]

    try:
        return ResponseStatus(), bytes.fromhex(string)  # type: ignore
    except ValueError as e:
        return error_status(note=err_msg, e=e, log=log), None


def decode_query_data(query_data: str, log: Union[print, click.echo, Logger] = print) -> tuple[ResponseStatus, Optional[OracleQuery]]:
    """Decode query data."""
    if len(query_data) > 2 and query_data[:2] == "0x":
        query_data = query_data[2:]

    status, query_data_bytes = bytes_from_string(
        string=query_data,
        err_msg=(
            "Invalid query data. Only hex strings accepted as input. Example Snapshot query data:\n"
            "0x00000000000000000000000000000000000000000000000000000000000000400"
            "0000000000000000000000000000000000000000000000000000000000000800000"
            "000000000000000000000000000000000000000000000000000000000008536e617"
            "073686f740000000000000000000000000000000000000000000000000000000000"
            "0000000000000000000000000000000000000000000000000000800000000000000"
            "0000000000000000000000000000000000000000000000000200000000000000000"
            "0000000000000000000000000000000000000000000000406363653937363061646"
            "5613930363137363934306165356664303562633030376363393235326235323438"
            "333230363538303036333534383463623563623537"
        ),
        log=log,
        )
    if not status.ok:
        return status, None

    q = None
    for query in (AbiQuery, LegacyRequest, JsonQuery):
        q = query.get_query_from_data(query_data_bytes)  # type: ignore
        if q:
            break

    if not q:
        return error_status(note="Unable to decode query data.", log=log), None
    
    log(f"Decoded query from data: {q}")
    return ResponseStatus(), q


def decode_submit_value_bytes(query: OracleQuery, submit_value_bytes: str, log: Union[print, click.echo, Logger] = print) -> tuple[ResponseStatus, Optional[Any]]:
    """Decode reported data."""
    if len(submit_value_bytes) > 2 and submit_value_bytes[:2] == "0x":
        submit_value_bytes = submit_value_bytes[2:]

    status, submit_value_bytes = bytes_from_string(
        string=submit_value_bytes,
        err_msg=(
            "Invalid submit value bytes. Only hex strings accepted as input. Example Snapshot submit value bytes:\n"
            "0x0000000000000000000000000000000000000000000000000000000000000001"
        ),
        log=log,
        )
    if not status.ok:
        return status, None

    if isinstance(submit_value_bytes, bytes):
        try:
            decoded = query.value_type.decode(submit_value_bytes)
            log(f"Decoded value: {decoded}")
            return ResponseStatus(), decoded
        except (eth_abi.exceptions.InsufficientDataBytes, eth_abi.exceptions.NonEmptyPaddingBytes) as e:
            error_status(
                note=f"Unable to decode value using query type: {query.__class__.__name__}",
                e=e,
                log=log,
            ), None



def query_from_type_string(type_string: str) -> OracleQuery:
    """Get query from type string."""
    for entry in query_catalog._entries.values():
        if entry.query_type == type_string:
            return entry.query

    raise ValueError(f"Unsupported query type: {type_string}")
