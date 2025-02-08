import errno
from collections.abc import AsyncGenerator, Generator
from typing import Union

import pytest
import pytest_asyncio

from pyroute2 import NDB, netns
from pyroute2.common import uifname
from pyroute2.iproute.linux import AsyncIPRoute, IPRoute
from pyroute2.netlink.exceptions import NetlinkError
from pyroute2.netlink.rtnl import IFNAMSIZ
from pyroute2.netlink.rtnl.ifinfmsg import ifinfmsg


class TestInterface:
    '''Test interface spec.

    Provided by `test_link` fixture.

    Provides shortcuts to some important interface properties,
    like `TestInterface.index` or `TestInterface.netns`.
    '''

    def __init__(self, index: int, ifname: str, address: str, nsname: str):
        if index <= 1:
            raise TypeError('test interface index must be > 1')
        if not 1 < len(ifname) <= IFNAMSIZ:
            raise TypeError(
                'test interface ifname length must be from 2 to IFNAMSIZ'
            )
        self._index = index
        self._ifname = ifname
        self._address = address
        self._netns = nsname

    @property
    def index(self) -> int:
        '''Test interface index.

        Is always greater than 1, as index 1 has the the loopback interface.
        '''
        return self._index

    @property
    def ifname(self) -> str:
        '''Test interface ifname.

        The name length must be greater than 1 and less or equal IFNAMSIZ.
        '''
        return self._ifname

    @property
    def address(self) -> str:
        '''Test interface MAC address.

        In the form `xx:xx:xx:xx:xx:xx`.'''
        return self._address

    @property
    def netns(self) -> str:
        '''Test interface netns.

        A string name of the network namespace.'''
        return self._netns


class TestContext:
    '''The test context.

    Provided by `async_context` and `sync_context` fixtures.

    Provides convenient shortcuts to RTNL API, the network namespace
    name and the test interface spec.
    '''

    def __init__(
        self, ipr: Union[IPRoute, AsyncIPRoute], test_link: TestInterface
    ):
        self._ipr = ipr
        self._test_link = test_link

    @property
    def ipr(self) -> Union[IPRoute, AsyncIPRoute]:
        '''RTNL API.

        Return RTNL API instance, either IPRoute, or AsyncIPRoute.'''
        return self._ipr

    @property
    def test_link(self) -> TestInterface:
        '''Test interface spec.

        Return `TestInterface` object for the test interface.'''
        return self._test_link

    @property
    def netns(self) -> str:
        '''Network namespace.

        A string name of the network namespace.'''
        return self.ipr.status['netns']


@pytest.fixture(name='nsname')
def _nsname() -> Generator[str]:
    '''Network namespace.

    * **Name**: nsname
    * **Scope**: function

    Create a unique network namespace and yield its name. Remove
    the netns on cleanup.

    It's safe to create and modify interfaces, addresses, routes etc.
    in the test network namespace, as it is disconnected from the main
    system, and the test cleanup will remove the namespace with all
    its content.

    Example usage:

    .. code::

        def test_list_interfaces(nsname):
            subprocess.Popen(
                ['ip', 'netns', 'exec', nsname, 'ip', 'link'],
                stdout=subprocess.PIPE,
            )
            ...

    '''
    nsname = uifname()
    netns.create(nsname)
    with IPRoute(netns=nsname) as ipr:
        ipr.link('set', index=1, state='up')
        ipr.poll(ipr.addr, 'dump', address='127.0.0.1', timeout=5)
    yield nsname
    try:
        netns.remove(nsname)
    except OSError:
        pass


@pytest.fixture(name='test_link_ifinfmsg')
def _test_link_ifinfmsg(nsname: str) -> Generator[ifinfmsg]:
    '''Test interface ifinfmsg.

    * **Name**: test_link_ifinfmsg
    * **Scope**: function
    * **Depends**: nsname

    Create a test interface in the test netns and yield ifinfmsg. Remove
    the interface on cleanup.

    This fixture depends on **nsname**, and it means that the network
    namespace will be created automatically if you use this fixture.

    Example usage:

    .. code::

        def test_check_interface(nsname, test_link_ifinfmsg):
            link = test_link_ifinfmsg
            ns = ['ip', 'netns', 'exec', nsname]
            up = ['ip', 'link', 'set', 'dev', link.get('ifname'), 'up']
            subprocess.Popen(ns + up)
            ...
    '''
    ifname = uifname()
    with IPRoute(netns=nsname) as ipr:
        ipr.link('add', ifname=ifname, kind='dummy', state='up')
        (link,) = ipr.poll(ipr.link, 'dump', ifname=ifname, timeout=5)
        yield link
        try:
            ipr.link('del', index=link.get('index'))
        except NetlinkError as e:
            if e.code != errno.ENODEV:
                raise


@pytest.fixture(name='test_link')
def _test_link(
    nsname: str, test_link_ifinfmsg: ifinfmsg
) -> Generator[TestInterface]:
    '''Test interface spec.

    * **Name**: test_link
    * **Scope**: function
    * **Depends**: nsname, test_link_ifinfmsg

    Yield `TestInterface` object for the test interface, providing
    a convenient way to access some important interface properties.
    '''
    yield TestInterface(
        index=test_link_ifinfmsg.get('index'),
        ifname=test_link_ifinfmsg.get('ifname'),
        address=test_link_ifinfmsg.get('address'),
        nsname=nsname,
    )


@pytest.fixture(name='test_link_address')
def _test_link_address(test_link: TestInterface) -> Generator[str]:
    '''Test interface MAC address.

    * **Name**: test_link_address
    * **Scope**: function
    * **Depends**: test_link

    Yield test interface MAC address. The network namespace and
    the test interface exist at this point.
    '''
    yield test_link.address


@pytest.fixture(name='test_link_index')
def _test_link_index(test_link: TestInterface) -> Generator[int]:
    '''Test interface MAC index.

    * **Name**: test_link_index
    * **Scope**: function
    * **Depends**: test_link

    Yield test interface index. The network namespace and
    the test interface exist at this point.
    '''
    yield test_link.index


@pytest.fixture(name='test_link_ifname')
def _test_link_ifname(test_link: TestInterface) -> Generator[str]:
    '''Test interface MAC ifname.

    * **Name**: test_link_ifname
    * **Scope**: function
    * **Depends**: test_link

    Yield test interface ifname. The network namespace and
    the test interface exist at this point.
    '''
    yield test_link.ifname


@pytest.fixture(name='tmp_link_ifname')
def _tmp_link_ifname(nsname: str) -> Generator[str]:
    '''Temporary link name.

    * **Name**: tmp_link_ifname
    * **Scope**: function
    * **Depends**: nsname

    Yield tmp link ifname, but don't create it. Try to remove
    the link on cleanup.
    '''
    ifname = uifname()
    with IPRoute(netns=nsname) as ipr:
        yield ifname
        try:
            (link,) = ipr.link('get', ifname=ifname)
            ipr.link('del', index=link.get('index'))
        except NetlinkError as e:
            if e.code != errno.ENODEV:
                raise


@pytest_asyncio.fixture(name='async_ipr')
async def _async_ipr(request, nsname: str) -> AsyncGenerator[AsyncIPRoute]:
    '''`AsyncIPRoute` instance.

    * **Name**: async_ipr
    * **Scope**: function
    * **Depends**: nsname

    Yield `AsyncIPRoute` instance, running within the test network namespace.
    You can provide additional keyword arguments to `AsyncIPRoute`:

    .. code::

        @pytest.mark.parametrize(
            'async_ipr',
            [
                {
                    'ext_ack': True,
                    'strict_check': True,
                },
            ],
            indirect=True
        )
        @pytest.mark.asyncio
        async def test_my_case(async_ipr):
            await async_ipr.link(...)
    '''
    kwarg = getattr(request, 'param', {})
    async with AsyncIPRoute(netns=nsname, **kwarg) as ipr:
        yield ipr


@pytest.fixture(name='sync_ipr')
def _sync_ipr(request, nsname: str) -> Generator[IPRoute]:
    '''`IPRoute` instance.

    * **Name**: sync_ipr
    * **Scope**: function
    * **Depends**: nsname

    Yield `IPRoute` instance, running within the test network namespace.
    You can provide additional keyword arguments to `IPRoute`:

    .. code::

        @pytest.mark.parametrize(
            'sync_ipr',
            [
                {
                    'ext_ack': True,
                    'strict_check': True,
                },
            ],
            indirect=True
        )
        def test_my_case(sync_ipr):
            sync_ipr.link(...)
    '''
    kwarg = getattr(request, 'param', {})
    with IPRoute(netns=nsname, **kwarg) as ipr:
        yield ipr


@pytest_asyncio.fixture(name='async_context')
async def _async_context(
    async_ipr: AsyncIPRoute, test_link: TestInterface
) -> AsyncGenerator[TestContext]:
    '''Asynchronous TestContext.

    * **Name**: async_context
    * **Scope**: function
    * **Depends**: async_ipr, test_link

    Yield `TestContext` with `AsyncIPRoute`.
    '''
    yield TestContext(async_ipr, test_link)


@pytest.fixture(name='sync_context')
def _sync_context(
    sync_ipr: IPRoute, test_link: TestInterface
) -> Generator[TestContext]:
    '''Synchronous TestContext.

    * **Name**: sync_context
    * **Scope**: function
    * **Depends**: sync_ipr, test_link

    Yield `TestContext` with `IPRoute`.
    '''
    yield TestContext(sync_ipr, test_link)


@pytest.fixture(name='ndb')
def _ndb(nsname: str) -> Generator[NDB]:
    '''NDB instance.

    * **Name**: ndb
    * **Scope**: function
    * **Depends**: nsname

    Yield `NDB` instance running in the test network namespace.
    '''
    with NDB(sources=[{'target': 'localhost', 'netns': nsname}]) as ndb:
        yield ndb
