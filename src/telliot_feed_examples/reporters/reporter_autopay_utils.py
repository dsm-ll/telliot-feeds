import asyncio
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from multicall import Call
from multicall import Multicall
from multicall import multicall
from multicall.constants import MULTICALL2_ADDRESSES
from multicall.constants import MULTICALL_ADDRESSES
from multicall.constants import Network
from telliot_core.tellor.tellorflex.autopay import TellorFlexAutopayContract
from telliot_core.utils.response import error_status
from telliot_core.utils.timestamp import TimeStamp
from web3.main import Web3

from telliot_feed_examples.feeds import CATALOG_FEEDS
from telliot_feed_examples.queries.query_catalog import query_catalog
from telliot_feed_examples.utils.log import get_logger

logger = get_logger(__name__)

# add testnet support for multicall that aren't avaialable in the package
Network.Mumbai = 80001
MULTICALL_ADDRESSES[Network.Mumbai] = MULTICALL2_ADDRESSES[
    Network.Mumbai
] = "0x35583BDef43126cdE71FD273F5ebeffd3a92742A"
Network.ArbitrumRinkeby = 421611
MULTICALL_ADDRESSES[Network.ArbitrumRinkeby] = MULTICALL2_ADDRESSES[
    Network.ArbitrumRinkeby
] = "0xf609687230a65E8bd14caceDEfCF2dea9c15b242"
Network.OptimismKovan = 69
MULTICALL_ADDRESSES[Network.OptimismKovan] = MULTICALL2_ADDRESSES[
    Network.OptimismKovan
] = "0xf609687230a65E8bd14caceDEfCF2dea9c15b242"


async def run_in_subprocess(coro: Any, *args: Any, **kwargs: Any) -> Any:
    return await asyncio.get_event_loop().run_in_executor(ThreadPoolExecutor(16), coro, *args, **kwargs)


multicall.run_in_subprocess = run_in_subprocess

# Mapping of queryId to query tag for supported queries
CATALOG_QUERY_IDS = {query_catalog._entries[tag].query.query_id: tag for tag in query_catalog._entries}


@dataclass
class Tag:
    query_tag: str
    feed_id: str


@dataclass
class FeedDetails:
    """Data types for feed details contract response"""

    reward: int
    balance: int
    startTime: int
    interval: int
    window: int
    priceThreshold: int
    feedsWithFundingIndex: int


class AutopayCalls:
    def __init__(self, autopay: TellorFlexAutopayContract, catalog: Dict[bytes, str] = CATALOG_QUERY_IDS):
        self.autopay = autopay
        self.w3: Web3 = autopay.node._web3
        self.catalog = catalog

    async def get_current_feeds(self, require_success: bool = True) -> Any:
        """
        Getter of feed ids list for each query id in catalog from autopay, plus
        Getter of a query id report's timestamp index from oracle for a current timestamp
        and a timestamp from three months ago,
        used for getting all timestamps for the past three months.

        Reason of why three months: reporters can't claim tips from funded feeds past three months
        getting three months of timestamp is useful to determine if there will be balance if every eligible
        timestamp claims and draining the balance as a result
        """
        calls = []
        current_time = TimeStamp.now().ts
        three_mos_ago = current_time - 7889238  # 3 months in seconds
        for query_id, tag in self.catalog.items():
            if "legacy" in tag or "spot" in tag:
                calls.append(
                    Call(
                        self.autopay.address,
                        ["getCurrentFeeds(bytes32)(bytes32[])", query_id],
                        [[tag, None]],
                    )
                )
                calls.append(
                    Call(
                        self.autopay.address,
                        ["getIndexForDataBefore(bytes32,uint256)(bool,uint256)", query_id, current_time],
                        [["disregard_boolean", None], [(tag, "current_time"), None]],
                    )
                )
                calls.append(
                    Call(
                        self.autopay.address,
                        ["getIndexForDataBefore(bytes32,uint256)(bool,uint256)", query_id, three_mos_ago],
                        [["disregard_boolean", None], [(tag, "three_mos_ago"), None]],
                    )
                )
        multi_call = Multicall(calls=calls, _w3=self.w3, require_success=require_success)
        data = await multi_call.coroutine()
        # remove status boolean thats useless here
        data.pop("disregard_boolean")
        # {'ric-usd-spot': (b'c#\x81q\xbf\xcf\x91H?s\xbfx\xfe\x7fu!\x03w\xf5\x1dH\xda\x064\xa6\xd7*\xbfrU\x87*',),
        # ('ric-usd-spot', 'current_time'): 85, ('ric-usd-spot', 'three_mos_ago'): 1}
        return data

    async def get_feed_details(self, require_success: bool = True) -> Any:
        """
        Getter of timestamps for three months of reports from oracle using query id and index; also,
        Getter of feed details of all the feed ids for every query id, plus
        Getter of current values from oracle for every query id in catalog, used to measure determine
        if submitting a value now will be first in eligible window
        """
        current_feeds = await self.get_current_feeds()
        tags_with_feed_ids = {
            tag: feed_id for tag, feed_id in current_feeds.items() if type(tag) != tuple if len(current_feeds[tag]) > 0
        }
        # example: {'ric-usd-spot':
        # (b'c#\x81q\xbf\xcf\x91H?s\xbfx\xfe\x7fu!\x03w\xf5\x1dH\xda\x064\xa6\xd7*\xbfrU\x87*',)}
        # separate items from get_current_feeds() response
        idx_current = []  # indices for every query id reports' current timestamps
        idx_three_mos_ago = []  # indices for every query id reports' three months ago timestamps
        tags = []  # query tags from catalog
        for key in current_feeds:
            if type(key) == tuple and key[0] in tags_with_feed_ids:
                if key[1] == "current_time":
                    idx_current.append(current_feeds[key])
                    tags.append((key[0], tags_with_feed_ids[key[0]]))
                else:
                    idx_three_mos_ago.append(current_feeds[key])

        merged_indices = list(zip(idx_current, idx_three_mos_ago))
        merged_query_idx = dict(zip(tags, merged_indices))

        get_timestampby_query_id_n_idx_call = [
            Call(
                self.autopay.address,
                [
                    "getTimestampbyQueryIdandIndex(bytes32,uint256)(uint256)",
                    query_catalog._entries[tag].query.query_id,
                    idx,
                ],
                [[(tag, idx), None]],
            )
            for (tag, _), (end, start) in merged_query_idx.items()
            for idx in range(start, end)
        ]

        # convert feed details from tuples to list to be able to decrement balance
        def _to_list(val: Any) -> List[Any]:

            return list(val)

        get_data_feed_call = [
            Call(
                self.autopay.address,
                ["getDataFeed(bytes32)((uint256,uint256,uint256,uint256,uint256,uint256,uint256))", feed_id],
                [[("current_feeds", tag, feed_id.hex()), _to_list]],
            )
            for tag, feed_ids in merged_query_idx
            for feed_id in feed_ids
        ]
        get_current_values_call = [
            Call(
                self.autopay.address,
                ["getCurrentValue(bytes32)(bool,bytes,uint256)", query_catalog._entries[tag].query.query_id],
                [
                    [("current_values", tag), None],
                    [("current_values", tag, "current_price"), self._current_price],
                    [("current_values", tag, "timestamp"), None],
                ],
            )
            for tag, _ in merged_query_idx
        ]
        calls = get_data_feed_call + get_current_values_call + get_timestampby_query_id_n_idx_call
        multi_call = Multicall(calls=calls, _w3=self.w3, require_success=require_success)
        feed_details = await multi_call.coroutine()
        # {('current_feeds', 'ric-usd-spot', '63238171bfcf91483f73bf78fe7f75210377f51d48da0634a6d72abf7255872a'):
        # [50000000000000000000, 50000000000000000000, 1650644349, 86400, 3600, 0, 2]
        # ('current_values', 'ric-usd-spot'): True, ('current_values', 'ric-usd-spot', 'current_price'): 0.036731286,
        # ('current_values', 'ric-usd-spot', 'timestamp'): 1655137179
        return feed_details

    async def reward_claim_status(self, require_success: bool = True) -> Any:
        feed_details_before_check = await self.get_feed_details()
        # create a key to use for the first timestamp since it doesn't have a before value that needs to be checked
        feed_details_before_check[(0, 0)] = 0
        timestamp_before_key = (0, 0)

        feeds = {feed: details for feed, details in feed_details_before_check.items() if "current_feeds" in feed}
        current_values = {tag: price for tag, price in feed_details_before_check.items() if "current_values" in tag}
        reward_claimed_status_call = []
        for _, tag, feed_id in feeds:
            details = FeedDetails(*feeds[(_, tag, feed_id)])
            for keys in list(feed_details_before_check):
                if "current_feeds" not in keys and "current_values" not in keys:
                    if tag in keys:
                        is_first = _is_timestamp_first_in_window(
                            feed_details_before_check[timestamp_before_key],
                            feed_details_before_check[keys],
                            details.startTime,
                            details.window,
                            details.interval,
                        )
                        timestamp_before_key = keys
                        if is_first:
                            reward_claimed_status_call.append(
                                Call(
                                    self.autopay.address,
                                    [
                                        "getRewardClaimedStatus(bytes32,bytes32,uint256)(bool)",
                                        bytes.fromhex(feed_id),
                                        query_catalog._entries[tag].query.query_id,
                                        feed_details_before_check[keys],
                                    ],
                                    [[(tag, feed_id, feed_details_before_check[keys]), None]],
                                )
                            )

        multi_call = Multicall(calls=reward_claimed_status_call, _w3=self.w3, require_success=require_success)
        data = await multi_call.coroutine()

        return feeds, current_values, data

    # do i just the count of unclaimed timestamps
    async def get_current_tip(self, require_success: bool = False) -> Any:
        """
        Returns response from autopay getCurrenTip call
        require_success is False because autopay returns an
        error if tip amount is zero
        """
        calls = [
            Call(self.autopay.address, ["getCurrentTip(bytes32)(uint256)", query_id], [[self.catalog[query_id], None]])
            for query_id in self.catalog
        ]
        multi_call = Multicall(calls=calls, _w3=self.w3, require_success=require_success)
        data = await multi_call.coroutine()

        return data

    # Helper to decode price value from oracle
    def _current_price(self, *val: Any) -> Any:
        if len(val) > 1:
            if val[1] == b"":
                return val[1]
            return Web3.toInt(hexstr=val[1].hex()) / 1e18
        return Web3.toInt(hexstr=val[0].hex()) / 1e18 if val[0] != b"" else val[0]


async def get_feed_tip(query_id: bytes, autopay: TellorFlexAutopayContract) -> Any:

    if not autopay.connect().ok:
        msg = "can't suggest feed, autopay contract not connected"
        error_status(note=msg, log=logger.critical)
        return None
    single_query = {query_id: CATALOG_QUERY_IDS[query_id]}
    autopay_calls = AutopayCalls(autopay, catalog=single_query)
    feed_tips = await get_continuous_tips(autopay, autopay_calls)
    # {'trb-usd-legacy': 30000000000000000000}
    tips = feed_tips[CATALOG_QUERY_IDS[query_id]]
    return tips


async def get_one_time_tips(
    autopay: TellorFlexAutopayContract,
) -> Any:
    one_time_tips = AutopayCalls(autopay=autopay, catalog=CATALOG_QUERY_IDS)
    return await one_time_tips.get_current_tip()


async def get_continuous_tips(autopay: TellorFlexAutopayContract, tipping_feeds: Any = None) -> Any:
    if tipping_feeds is None:
        tipping_feeds = AutopayCalls(autopay=autopay, catalog=CATALOG_QUERY_IDS)
    current_feeds, current_values, claim_status = await tipping_feeds.reward_claim_status()
    current_feeds = _remaining_feed_balance(current_feeds, claim_status)
    current_feeds = {(key[1], key[2]): value for key, value in current_feeds.items()}
    values_filtered = {}
    for key, value in current_values.items():
        if len(key) > 2:
            values_filtered[(key[1], key[2])] = value
        else:
            values_filtered[key[1]] = value
    return await _get_feed_suggestion(current_feeds, values_filtered)


async def autopay_suggested_report(
    autopay: TellorFlexAutopayContract,
) -> Tuple[Optional[str], Any]:
    chain = autopay.node.chain_id
    if chain in (137, 80001, 69, 1666600000, 1666700000, 421611):
        assert isinstance(autopay, TellorFlexAutopayContract)
        # get query_ids with one time tips
        singletip_dict = await get_one_time_tips(autopay)
        # get query_ids with active feeds
        datafeed_dict = await get_continuous_tips(autopay)

        # remove none type
        single_tip_suggestion = {i: j for i, j in singletip_dict.items() if j}
        datafeed_suggestion = {i: j for i, j in datafeed_dict.items() if j}

        # combine feed dicts and add tips for duplicate query ids
        combined_dict = {
            key: _add_values(single_tip_suggestion.get(key), datafeed_suggestion.get(key))
            for key in single_tip_suggestion | datafeed_suggestion
        }
        # get feed with most tips
        tips_sorted = sorted(combined_dict.items(), key=lambda item: item[1], reverse=True)  # type: ignore
        if tips_sorted:
            suggested_feed = tips_sorted[0]
            return suggested_feed[0], suggested_feed[1]
        else:
            return None, None
    else:
        return None, None


async def _get_feed_suggestion(feeds: Any, current_values: Any) -> Any:

    current_time = TimeStamp.now().ts
    query_id_with_tips = {}

    for query_tag, feed_id in feeds:  # i is (query_id,feed_id)
        if feeds[(query_tag, feed_id)] is not None:  # feed_detail[i] is (details)
            try:
                feed_details = FeedDetails(*feeds[(query_tag, feed_id)])
            except TypeError:
                msg = "couldn't decode feed details from contract"
                continue
            except Exception as e:
                msg = f"unknown error decoding feed details from contract: {e}"
                continue

        if feed_details.balance <= 0:
            continue
        num_intervals = math.floor((current_time - feed_details.startTime) / feed_details.interval)
        # Start time of latest submission window
        current_window_start = feed_details.startTime + (feed_details.interval * num_intervals)

        if not current_values[query_tag]:
            value_before_now = 0
            timestamp_before_now = 0
        else:
            value_before_now = current_values[(query_tag, "current_price")]
            timestamp_before_now = current_values[(query_tag, "timestamp")]

        rules = [
            (current_time - current_window_start) < feed_details.window,
            timestamp_before_now < current_window_start,
        ]
        if not all(rules):
            msg = f"{query_tag}, isn't eligible for a tip"
            error_status(note=msg, log=logger.info)
            continue

        if feed_details.priceThreshold == 0:
            if query_tag not in query_id_with_tips:
                query_id_with_tips[query_tag] = feed_details.reward
            else:
                query_id_with_tips[query_tag] += feed_details.reward
        else:
            datafeed = CATALOG_FEEDS[query_tag]
            value_now = await datafeed.source.fetch_new_datapoint()  # type: ignore
            if not value_now:
                note = f"Unable to fetch {datafeed} price for tip calculation"
                error_status(note=note, log=logger.warning)
                continue
            value_now = value_now[0]

            if value_before_now == 0:
                price_change = 10000

            elif value_now >= value_before_now:
                price_change = (10000 * (value_now - value_before_now)) / value_before_now

            else:
                price_change = (10000 * (value_before_now - value_now)) / value_before_now

            if price_change > feed_details.priceThreshold:
                if query_tag not in query_id_with_tips:
                    query_id_with_tips[query_tag] = feed_details.reward
                else:
                    query_id_with_tips[query_tag] += feed_details.reward
    # {'trb-usd-legacy': 30000000000000000000}
    return query_id_with_tips


def _add_values(x: Optional[int], y: Optional[int]) -> Optional[int]:
    """Helper function to add values when combining dicts with same key"""
    return sum((num for num in (x, y) if num is not None))


def _is_timestamp_first_in_window(
    timestamp_before: int, timestamp_to_check: int, feed_start_timestamp: int, feed_window: int, feed_interval: int
) -> bool:
    # Number of intervals since start time
    num_intervals = math.floor((timestamp_to_check - feed_start_timestamp) / feed_interval)
    # Start time of latest submission window
    current_window_start = feed_start_timestamp + (feed_interval * num_intervals)
    eligible = [(timestamp_to_check - current_window_start) < feed_window, timestamp_before < current_window_start]
    return all(eligible)


def _remaining_feed_balance(current_feeds: Any, reward_claimed_status: Any) -> Any:
    for _, tag, feed_id in current_feeds:
        details = FeedDetails(*current_feeds[_, tag, feed_id])
        balance = details.balance
        if balance > 0:
            for _tag, _feed_id, timestamp in reward_claimed_status:
                if balance > 0 and tag == _tag and feed_id == _feed_id:
                    if not reward_claimed_status[tag, feed_id, timestamp]:
                        balance -= details.reward
                        current_feeds[_, tag, feed_id][1] = max(balance, 0)
    return current_feeds
