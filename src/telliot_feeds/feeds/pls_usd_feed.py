"""Example datafeed used by PLSUSDReporter."""
from telliot_feeds.datafeed import DataFeed
from telliot_feeds.queries.price.spot_price import SpotPrice
from telliot_feeds.sources.price.spot.coingecko import CoinGeckoSpotPriceSource
from telliot_feeds.sources.price.spot.coinpaprika import CoinpaprikaSpotPriceSource
from telliot_feeds.sources.price.spot.uniswapV3 import UniswapV3PriceSource
from telliot_feeds.sources.price.spot.pulsex_subgraph import PulseXSubgraphSource
from telliot_feeds.sources.price_aggregator import PriceAggregator
import os
from dotenv import load_dotenv
load_dotenv()

if os.getenv("NETWORK_ID") == "943":
    pls_usd_median_feed = DataFeed(
        query=SpotPrice(asset="PLS", currency="USD"),
        source=PriceAggregator(
            asset="pls",
            currency="usd",
            algorithm="median",
            sources=[
                PulseXSubgraphSource(asset="wpls", currency="usd"), 
            ],
        ),
    )
else:
    pls_usd_median_feed = DataFeed(
        query=SpotPrice(asset="PLS", currency="USD"),
        source=PriceAggregator(
            asset="pls",
            currency="usd",
            algorithm="median",
            sources=[
                CoinGeckoSpotPriceSource(asset="pls", currency="usd"),
                CoinpaprikaSpotPriceSource(asset="pls-pulsechain", currency="usd"),
                UniswapV3PriceSource(asset="pls", currency="usd"),
                PulseXSubgraphSource(asset="wpls", currency="usd"), 
            ],
        ),
    )
