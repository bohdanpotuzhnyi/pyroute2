from pyroute2.common import uifname


def test_impl_lookup(ipr, link):
    assert len(ipr.link_lookup(ifname=link.get('ifname'))) == 1


def test_impl_add_bridge(ipr):
    brname = uifname()
    args = {
        'ifname': brname,
        'kind': 'bridge',
        'IFLA_BR_FORWARD_DELAY': 0,
        'IFLA_BR_STP_STATE': 0,
        'IFLA_BR_MCAST_SNOOPING': 0,
        'IFLA_BR_AGEING_TIME': 1500,
    }
    ipr.link('add', **args)
    link = [x for x in ipr.poll(ipr.link, 'dump', ifname=brname, timeout=5)][0]
    assert link.get(('linkinfo', 'data', 'br_forward_delay')) == 0
    assert link.get(('linkinfo', 'data', 'br_stp_state')) == 0
    assert link.get(('linkinfo', 'data', 'br_mcast_snooping')) == 0
    assert link.get(('linkinfo', 'data', 'br_ageing_time')) == 1500


def test_impl_add_vlan(ipr, link):
    vname = uifname()
    args = {
        'ifname': vname,
        'kind': 'vlan',
        'vlan_id': 1001,
        'link': link.get('index'),
    }
    ipr.link('add', **args)
    link = [x for x in ipr.poll(ipr.link, 'dump', ifname=vname, timeout=5)][0]
    assert link.get(('linkinfo', 'data', 'vlan_id')) == 1001
