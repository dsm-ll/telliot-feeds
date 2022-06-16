"""Datafeed for current price of TRB in USD used by LegacyQueryReporter."""
from telliot_feed_examples.datafeed import DataFeed
from telliot_feed_examples.queries import LegacyRequest

from telliot_feed_examples.sources.price.spot.coinbase import CoinbaseSpotPriceSource
from telliot_feed_examples.sources.price.spot.coingecko import CoinGeckoSpotPriceSource
from telliot_feed_examples.sources.price_aggregator import PriceAggregator

trb_usd_median_feed = DataFeed(
    query=LegacyRequest(legacy_id=50),
    source=PriceAggregator(
        asset="trb",
        currency="usd",
        algorithm="median",
        sources=[
            CoinGeckoSpotPriceSource(asset="trb", currency="usd"),
            CoinbaseSpotPriceSource(asset="trb", currency="usd"),
        ],
    ),
)
