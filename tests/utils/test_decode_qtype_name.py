from telliot_feeds.utils.query_search_utils import decode_typ_name


def test_decode_qtype_name():
    # query data with non empty bytes error
    querydata = "0x00000000000000000000000000000000000000000000000000000000000000400000000000000000000000000000000000000000000000000000000000000080000000000000000000000000000000000000000000000000000000000000000745564d43616c6c000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000ae7ab96520de3a18e5e111b5eaab095312d7fe840000000000000000000000000000000000000000000000000000000000000060000000000000000000000000000000000000000000000000000000000000002470a082310000000000000000000000004e518e2b4e1649974d29e0697818d6e030e328cf00000000000000000000000000000000000000000000000000000000"  # noqa: E501
    assert decode_typ_name(bytes.fromhex(querydata[2:])) == ""
