from app.connectors.base import OSINTConnector
from app.connectors.commoncrawl import CommonCrawlConnector
from app.connectors.darknet_onionclaw import OnionClawDarknetConnector
from app.connectors.crypto_blockchain_info import BlockchainInfoConnector
from app.connectors.crypto_blockchair import BlockchairConnector
from app.connectors.crypto_chainabuse import ChainabuseConnector
from app.connectors.crypto_etherscan import EtherscanConnector
from app.connectors.domain_crtsh import CrtShConnector
from app.connectors.domain_dns import DnsRecordsConnector
from app.connectors.domain_urlscan import UrlscanConnector
from app.connectors.domain_whois import RdapWhoisConnector
from app.connectors.phone_lookup import PhoneLookupConnector
from app.connectors.registry_blacklist import LocalBlacklistConnector
from app.connectors.registry_opencorporates import OpenCorporatesConnector
from app.connectors.infra_internetdb import InternetDbConnector
from app.connectors.journalism_aleph import AlephConnector
from app.connectors.registry_gleif import GleifConnector
from app.connectors.registry_sec_edgar import SecEdgarConnector
from app.connectors.sanctions_opensanctions import OpenSanctionsConnector
from app.connectors.search_ddg import DuckDuckGoConnector
from app.connectors.site_content import SiteContentConnector
from app.connectors.threat_openphish import OpenPhishConnector
from app.connectors.search_searx import SearxConnector
from app.connectors.social_telegram import TelegramPreviewConnector
from app.connectors.social_threat_actor_username import ThreatActorUsernameConnector
from app.connectors.social_username import UsernameEnumConnector
from app.connectors.wayback import WaybackConnector

ALL_CONNECTORS: list[OSINTConnector] = [
    SiteContentConnector(),
    SearxConnector(),
    DuckDuckGoConnector(),
    WaybackConnector(),
    CommonCrawlConnector(),
    CrtShConnector(),
    RdapWhoisConnector(),
    DnsRecordsConnector(),
    UrlscanConnector(),
    OpenCorporatesConnector(),
    SecEdgarConnector(),
    GleifConnector(),
    LocalBlacklistConnector(),
    OpenSanctionsConnector(),
    AlephConnector(),
    InternetDbConnector(),
    OpenPhishConnector(),
    PhoneLookupConnector(),
    BlockchainInfoConnector(),
    BlockchairConnector(),
    EtherscanConnector(),
    ChainabuseConnector(),
    UsernameEnumConnector(),
    TelegramPreviewConnector(),
    ThreatActorUsernameConnector(),
    OnionClawDarknetConnector(),
]
