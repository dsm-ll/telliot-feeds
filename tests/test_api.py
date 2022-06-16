import pytest
from brownie import accounts
from telliot_core.apps.core import TelliotCore
from telliot_feed_examples.datafeed import DataFeed
from telliot_feed_examples.queries.api_query import APIQuery
from web3.datastructures import AttributeDict

from telliot_feed_examples.reporters.tellorflex import TellorFlexReporter
from telliot_feed_examples.sources.api_source import APIQuerySource

url_test = "https://taylorswiftapi.herokuapp.com/get"
key_str_test = "quote"
api_feed = DataFeed(
    source=APIQuerySource(url=url_test, key_str=key_str_test),
    query=APIQuery(url=url_test, key_str=key_str_test),
)


@pytest.mark.skip
@pytest.mark.asyncio
async def test_api_reporter_submit_once(
    mumbai_test_cfg, mock_flex_contract, mock_autopay_contract, mock_token_contract
):
    """Test reporting bct/usd on mumbai."""
    async with TelliotCore(config=mumbai_test_cfg) as core:
        # get PubKey and PrivKey from config files
        account = core.get_account()

        flex = core.get_tellorflex_contracts()
        flex.oracle.address = mock_flex_contract.address
        flex.autopay.address = mock_autopay_contract.address
        flex.token.address = mock_token_contract.address

        flex.oracle.connect()
        flex.token.connect()
        flex.autopay.connect()

        # mint token and send to reporter address
        mock_token_contract.mint(account.address, 1000e18)

        # send eth from brownie address to reporter address for txn fees
        accounts[1].transfer(account.address, "1 ether")

        r = TellorFlexReporter(
            endpoint=core.endpoint,
            account=account,
            chain_id=80001,
            oracle=flex.oracle,
            token=flex.token,
            autopay=flex.autopay,
            transaction_type=0,
            datafeed=api_feed,
            max_fee=100,
        )

        ORACLE_ADDRESSES = {mock_flex_contract.address}

        tx_receipt, status = await r.report_once()

        # Reporter submitted
        if tx_receipt is not None and status.ok:
            assert isinstance(tx_receipt, AttributeDict)
            assert tx_receipt.to in ORACLE_ADDRESSES
        # Reporter did not submit
        else:
            assert not tx_receipt
            assert not status.ok
            assert (
                ("Currently in reporter lock." in status.error)
                or ("Current address disputed" in status.error)
                or ("Unable to retrieve updated datafeed" in status.error)
            )
