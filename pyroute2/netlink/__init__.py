'''
Netlink basics
==============

General netlink packet structure::

    nlmsg packet:
        header
        data

Generic netlink message header::

    nlmsg header:
        uint32 length
        uint16 type
        uint16 flags
        uint32 sequence number
        uint32 pid

The `length` field is the length of all the packet, including
data and header. The `type` field is used to distinguish different
message types, commands etc. Please note, that there is no
explicit protocol field -- you choose a netlink protocol, when
you create a socket.

The `sequence number` is very important. Netlink is an asynchronous
protocol -- it means, that the packet order doesn't matter and is
not guaranteed. But responses to a request are always marked with
the same sequence number, so you can treat it as a cookie.

Please keep in mind, that a netlink request can initiate a
cascade of events, and netlink messages from these events can
carry sequence number == 0. E.g., it is so when you remove a
primary IP addr from an interface, when `promote_secondaries`
sysctl is set.

Beside of incapsulated headers and other protocol-specific data,
netlink messages can carry NLA (netlink attributes). NLA
structure is as follows::

    NLA header:
        uint16 length
        uint16 type
    NLA data:
        data-specific struct
        # optional:
        NLA
        NLA
        ...

So, NLA structures can be nested, forming a tree.

Complete structure of a netlink packet::

    nlmsg header:
        uint32 length
        uint16 type
        uint16 flags
        uint32 sequence number
        uint32 pid
    [ optional protocol-specific data ]
    [ optional NLA tree ]

More information about netlink protocol you can find in
the man pages.

Pyroute2 and netlink
====================

packets
-------

To simplify the development, pyroute2 provides an easy way to
describe packet structure. As an example, you can take the
ifaddrmsg description -- `pyroute2/netlink/rtnl/ifaddrmsg.py`.

To describe a packet, you need to inherit from `nlmsg` class::

    from pyroute2.netlink import nlmsg

    class foo_msg(nlmsg):
        fields = ( ... )
        nla_map = ( ... )

NLA are described in the same way, but the parent class should be
`nla`, instead of `nlmsg`. And yes, it is important to use the
proper parent class -- it affects the header structure.

fields attribute
----------------

The `fields` attribute describes the structure of the
protocol-specific data. It is a tuple of tuples, where each
member contains a field name and its data format.

Field data format should be specified as for Python `struct`
module. E.g., ifaddrmsg structure::

    struct ifaddrmsg {
        __u8  ifa_family;
        __u8  ifa_prefixlen;
        __u8  ifa_flags;
        __u8  ifa_scope;
        __u32 ifa_index;
    };

should be described as follows::

    class ifaddrmsg(nlmsg):
        fields = (('family', 'B'),
                  ('prefixlen', 'B'),
                  ('flags', 'B'),
                  ('scope', 'B'),
                  ('index', 'I'))

Format strings are passed directly to the `struct` module,
so you can use all the notations like `>I`, `16s` etc. All
fields are parsed from the stream separately, so if you
want to explicitly fix alignemt, as if it were C struct,
use the `pack` attribute::

    class tstats(nla):
        pack = 'struct'
        fields = (('version', 'H'),
                  ('ac_exitcode', 'I'),
                  ('ac_flag', 'B'),
                  ...)

Explicit padding bytes also can be used, when struct
packing doesn't work well::

    class ipq_mode_msg(nlmsg):
        pack = 'struct'
        fields = (('value', 'B'),
                  ('__pad', '7x'),
                  ('range', 'I'),
                  ('__pad', '12x'))


nla_map attribute
-----------------

The `nla_map` attribute is a tuple of NLA descriptions. Each
description is also a tuple in two different forms: either
two fields, name and format, or three fields: type, name and
format.

Please notice, that the format field is a string name of
corresponding NLA class::

    class ifaddrmsg(nlmsg):
        ...
        nla_map = (('IFA_UNSPEC',  'hex'),
                   ('IFA_ADDRESS', 'ipaddr'),
                   ('IFA_LOCAL', 'ipaddr'),
                   ...)

This code will create mapping, where IFA_ADDRESS NLA will be of
type 1 and IFA_LOCAL -- of type 2, etc. Both NLA will be decoded
as IP addresses (class `ipaddr`). IFA_UNSPEC will be of type 0,
and if it will be in the NLA tree, it will be just dumped in hex.

NLA class names are should be specified as strings, since they
are resolved in runtime.

There are several pre-defined NLA types, that you will get with
`nla` class:

    - `none` -- ignore this NLA
    - `flag` -- boolean flag NLA (no payload; NLA exists = True)
    - `uint8`, `uint16`, `uint32`, `uint64` -- unsigned int
    - `be8`, `be16`, `be32`, `be64` -- big-endian unsigned int
    - `ipaddr` -- IP address, IPv4 or IPv6
    - `ip4addr` -- only IPv4 address type
    - `ip6addr` -- only IPv6 address type
    - `target` -- a univeral target (IPv4, IPv6, MPLS)
    - `l2addr` -- MAC address
    - `hex` -- hex dump as a string -- useful for debugging
    - `cdata` -- a binary data
    - `string` -- UTF-8 string
    - `asciiz` -- zero-terminated ASCII string, no decoding
    - `array` -- array of simple types (uint8, uint16 etc.)

Please refer to `pyroute2/netlink/__init__.py` for details.

You can also make your own NLA descriptions::

    class ifaddrmsg(nlmsg):
        ...
        nla_map = (...
                   ('IFA_CACHEINFO', 'cacheinfo'),
                   ...)

        class cacheinfo(nla):
            fields = (('ifa_prefered', 'I'),
                      ('ifa_valid', 'I'),
                      ('cstamp', 'I'),
                      ('tstamp', 'I'))

Custom NLA descriptions should be defined in the same class,
where they are used.

Also, it is possible to use not autogenerated type numbers, as
for ifaddrmsg, but specify them explicitly::

    class iw_event(nla):
        ...
        nla_map = ((0x8B00, 'SIOCSIWCOMMIT', 'hex'),
                   (0x8B01, 'SIOCGIWNAME', 'hex'),
                   (0x8B02, 'SIOCSIWNWID', 'hex'),
                   (0x8B03, 'SIOCGIWNWID', 'hex'),
                   ...)

Here you can see custom NLA type numbers -- 0x8B00, 0x8B01 etc.
It is not permitted to mix these two forms in one class: you should
use ether autogenerated type numbers (two fields tuples), or
explicit numbers (three fields typles).

array types
-----------

There are different array-like NLA types in the kernel, and
some of them are covered by pyroute2. An array of simple type
elements::

    # declaration
    nla_map = (('NLA_TYPE', 'array(uint8)'), ...)

    # data layout
    +======+======+----------------------------
    | len  | type | uint8 | uint8 | uint 8 | ...
    +======+======+----------------------------

    # decoded
    {'attrs': [['NLA_TYPE', (2, 3, 4, 5, ...)], ...], ...}

An array of NLAs::

    # declaration
    nla_map = (('NLA_TYPE', '*type'), ...)

    # data layout
    +=======+=======+-----------------------+-----------------------+--
    | len   | type* | len  | type | payload | len  | type | payload | ...
    +=======+=======+-----------------------+-----------------------+--
    # type* -- in that case the type is OR'ed with NLA_F_NESTED

    # decoded
    {'attrs': [['NLA_TYPE', [payload, payload, ...]], ...], ...}

parsed netlink message
----------------------

Netlink messages are represented by pyroute2 as dictionaries
as follows::

    {'header': {'pid': ...,
                'length: ...,
                'flags': ...,
                'error': None,  # if you are lucky
                'type': ...,
                'sequence_number': ...},

     # fields attributes
     'field_name1': value,
     ...
     'field_nameX': value,

     # nla tree
     'attrs': [['NLA_NAME1', value],
               ...
               ['NLA_NAMEX', value],
               ['NLA_NAMEY', {'field_name1': value,
                              ...
                              'field_nameX': value,
                              'attrs': [['NLA_NAME.... ]]}]]}

As an example, a message from the wireless subsystem about new
scan event::

    {'index': 4,
     'family': 0,
     '__align': 0,
     'header': {'pid': 0,
                'length': 64,
                'flags': 0,
                'error': None,
                'type': 16,
                'sequence_number': 0},
     'flags': 69699,
     'ifi_type': 1,
     'event': 'RTM_NEWLINK',
     'change': 0,
     'attrs': [['IFLA_IFNAME', 'wlp3s0'],
               ['IFLA_WIRELESS',
                {'attrs': [['SIOCGIWSCAN',
                            '00:00:00:00:00:00:00:00:00:00:00:00']]}]]}

One important detail is that NLA chain is represented as a list of
elements `['NLA_TYPE', value]`, not as a dictionary. The reason is that
though in the kernel *usually* NLA chain is a dictionary, the netlink
protocol by itself doesn't require elements of each type to be unique.
In a message there may be several NLA of the same type.

encoding and decoding algo
--------------------------

The message encoding works as follows:

1. Reserve space for the message header (if there is)
2. Iterate defined `fields`, encoding values with `struct.pack()`
3. Iterate NLA from the `attrs` field, looking up types in `nla_map`
4. Encode the header

Since every NLA is also an `nlmsg` object, there is a recursion.

The decoding process is a bit simpler:

1. Decode the header
2. Iterate `fields`, decoding values with `struct.unpack()`
3. Iterate NLA until the message ends

If the `fields` attribute is an empty list, the step 2 will be skipped.
The step 3 will be skipped in the case of the empty `nla_map`. If both
attributes are empty lists, only the header will be encoded/decoded.

create and send messages
------------------------

Using high-level interfaces like `IPRoute` or `IPDB`, you will never
need to manually construct and send netlink messages. But in the case
you really need it, it is simple as well.

Having a description class, like `ifaddrmsg` from above, you need to:

    - instantiate it
    - fill the fields
    - encode the packet
    - send the encoded data

The code::

    from pyroute2.netlink import NLM_F_REQUEST
    from pyroute2.netlink import NLM_F_ACK
    from pyroute2.netlink import NLM_F_CREATE
    from pyroute2.netlink import NLM_F_EXCL
    from pyroute2.iproute import RTM_NEWADDR
    from pyroute2.netlink.rtnl.ifaddrmsg import ifaddrmsg

    ##
    # add an addr to an interface
    #

    # create the message
    msg = ifaddrmsg()

    # fill the protocol-specific fields
    msg['index'] = index  # index of the interface
    msg['family'] = AF_INET  # address family
    msg['prefixlen'] = 24  # the address mask
    msg['scope'] = scope  # see /etc/iproute2/rt_scopes

    # attach NLA -- it MUST be a list / mutable
    msg['attrs'] = [['IFA_LOCAL', '192.168.0.1'],
                    ['IFA_ADDRESS', '192.162.0.1']]

    # fill generic netlink fields
    msg['header']['sequence_number'] = nonce  # an unique seq number
    msg['header']['pid'] = os.getpid()
    msg['header']['type'] = RTM_NEWADDR
    msg['header']['flags'] = NLM_F_REQUEST |\\
                             NLM_F_ACK |\\
                             NLM_F_CREATE |\\
                             NLM_F_EXCL

    # encode the packet
    msg.encode()

    # send the buffer
    nlsock.sendto(msg.buf.getvalue(), (0, 0))

Please notice, that NLA list *MUST* be mutable.

------------------

Module contents:
'''

import traceback
import logging
import struct
import types
import sys
import io
import re

from socket import inet_pton
from socket import inet_ntop
from socket import AF_INET
from socket import AF_INET6
from socket import AF_UNSPEC
from pyroute2.common import AF_MPLS
from pyroute2.common import hexdump
from pyroute2.common import basestring
from pyroute2.netlink.exceptions import NetlinkError
from pyroute2.netlink.exceptions import NetlinkDecodeError
from pyroute2.netlink.exceptions import NetlinkNLADecodeError

# make pep8 happy
_ne = NetlinkError        # reexport for compatibility
_de = NetlinkDecodeError  #


class NotInitialized(Exception):
    pass

_letters = re.compile('[A-Za-z]')
_fmt_letters = re.compile('[^!><@=][!><@=]')

##
# That's a hack for the code linter, which works under
# Python3, see unicode reference in the code below
if sys.version[0] == '3':
    unicode = str

NLMSG_MIN_TYPE = 0x10

GENL_NAMSIZ = 16    # length of family name
GENL_MIN_ID = NLMSG_MIN_TYPE
GENL_MAX_ID = 1023

GENL_ADMIN_PERM = 0x01
GENL_CMD_CAP_DO = 0x02
GENL_CMD_CAP_DUMP = 0x04
GENL_CMD_CAP_HASPOL = 0x08

#
# List of reserved static generic netlink identifiers:
#
GENL_ID_GENERATE = 0
GENL_ID_CTRL = NLMSG_MIN_TYPE

#
# Controller
#

CTRL_CMD_UNSPEC = 0x0
CTRL_CMD_NEWFAMILY = 0x1
CTRL_CMD_DELFAMILY = 0x2
CTRL_CMD_GETFAMILY = 0x3
CTRL_CMD_NEWOPS = 0x4
CTRL_CMD_DELOPS = 0x5
CTRL_CMD_GETOPS = 0x6
CTRL_CMD_NEWMCAST_GRP = 0x7
CTRL_CMD_DELMCAST_GRP = 0x8
CTRL_CMD_GETMCAST_GRP = 0x9  # unused


CTRL_ATTR_UNSPEC = 0x0
CTRL_ATTR_FAMILY_ID = 0x1
CTRL_ATTR_FAMILY_NAME = 0x2
CTRL_ATTR_VERSION = 0x3
CTRL_ATTR_HDRSIZE = 0x4
CTRL_ATTR_MAXATTR = 0x5
CTRL_ATTR_OPS = 0x6
CTRL_ATTR_MCAST_GROUPS = 0x7

CTRL_ATTR_OP_UNSPEC = 0x0
CTRL_ATTR_OP_ID = 0x1
CTRL_ATTR_OP_FLAGS = 0x2

CTRL_ATTR_MCAST_GRP_UNSPEC = 0x0
CTRL_ATTR_MCAST_GRP_NAME = 0x1
CTRL_ATTR_MCAST_GRP_ID = 0x2


#  Different Netlink families
#
NETLINK_ROUTE = 0            # Routing/device hook
NETLINK_UNUSED = 1           # Unused number
NETLINK_USERSOCK = 2         # Reserved for user mode socket protocols
NETLINK_FIREWALL = 3         # Firewalling hook
NETLINK_INET_DIAG = 4        # INET socket monitoring
NETLINK_NFLOG = 5            # netfilter/iptables ULOG
NETLINK_XFRM = 6             # ipsec
NETLINK_SELINUX = 7          # SELinux event notifications
NETLINK_ISCSI = 8            # Open-iSCSI
NETLINK_AUDIT = 9            # auditing
NETLINK_FIB_LOOKUP = 10
NETLINK_CONNECTOR = 11
NETLINK_NETFILTER = 12       # netfilter subsystem
NETLINK_IP6_FW = 13
NETLINK_DNRTMSG = 14         # DECnet routing messages
NETLINK_KOBJECT_UEVENT = 15  # Kernel messages to userspace
NETLINK_GENERIC = 16
# leave room for NETLINK_DM (DM Events)
NETLINK_SCSITRANSPORT = 18   # SCSI Transports

# NLA flags
NLA_F_NESTED = 1 << 15
NLA_F_NET_BYTEORDER = 1 << 14


# Netlink message flags values (nlmsghdr.flags)
#
NLM_F_REQUEST = 1    # It is request message.
NLM_F_MULTI = 2    # Multipart message, terminated by NLMSG_DONE
NLM_F_ACK = 4    # Reply with ack, with zero or error code
NLM_F_ECHO = 8    # Echo this request
# Modifiers to GET request
NLM_F_ROOT = 0x100    # specify tree    root
NLM_F_MATCH = 0x200    # return all matching
NLM_F_ATOMIC = 0x400    # atomic GET
NLM_F_DUMP = (NLM_F_ROOT | NLM_F_MATCH)
# Modifiers to NEW request
NLM_F_REPLACE = 0x100    # Override existing
NLM_F_EXCL = 0x200    # Do not touch, if it exists
NLM_F_CREATE = 0x400    # Create, if it does not exist
NLM_F_APPEND = 0x800    # Add to end of list

NLMSG_NOOP = 0x1    # Nothing
NLMSG_ERROR = 0x2    # Error
NLMSG_DONE = 0x3    # End of a dump
NLMSG_OVERRUN = 0x4    # Data lost
NLMSG_CONTROL = 0xe    # Custom message type for messaging control
NLMSG_TRANSPORT = 0xf    # Custom message type for NL as a transport
NLMSG_MIN_TYPE = 0x10    # < 0x10: reserved control messages
NLMSG_MAX_LEN = 0xffff  # Max message length

mtypes = {1: 'NLMSG_NOOP',
          2: 'NLMSG_ERROR',
          3: 'NLMSG_DONE',
          4: 'NLMSG_OVERRUN'}

IPRCMD_NOOP = 0
IPRCMD_STOP = 1
IPRCMD_ACK = 2
IPRCMD_ERR = 3
IPRCMD_REGISTER = 4
IPRCMD_RELOAD = 5
IPRCMD_ROUTE = 6
IPRCMD_CONNECT = 7
IPRCMD_DISCONNECT = 8
IPRCMD_SERVE = 9
IPRCMD_SHUTDOWN = 10
IPRCMD_SUBSCRIBE = 11
IPRCMD_UNSUBSCRIBE = 12
IPRCMD_PROVIDE = 13
IPRCMD_REMOVE = 14
IPRCMD_DISCOVER = 15
IPRCMD_UNREGISTER = 16

SOL_NETLINK = 270

NETLINK_ADD_MEMBERSHIP = 1
NETLINK_DROP_MEMBERSHIP = 2
NETLINK_PKTINFO = 3
NETLINK_BROADCAST_ERROR = 4
NETLINK_NO_ENOBUFS = 5
NETLINK_RX_RING = 6
NETLINK_TX_RING = 7

clean_cbs = {}


class nlmsg_base(dict):
    '''
    Netlink base class. You do not need to inherit it directly, unless
    you're inventing completely new protocol structure.

    Use nlmsg or nla classes.

    The class provides several methods, but often one need to customize
    only `decode()` and `encode()`.
    '''

    fields = tuple()
    header = tuple()
    pack = None                  # pack pragma
    nla_array = False
    cell_header = None
    align = 4
    nla_map = {}                 # NLA mapping
    nla_flags = 0                # NLA flags
    nla_init = None              # NLA initstring
    value_map = {}
    __t_nla_map = None
    __r_nla_map = None

    def msg_align(self, l):
        return (l + self.align - 1) & ~ (self.align - 1)

    def __init__(self,
                 data=None,
                 offset=0,
                 length=None,
                 parent=None,
                 init=None):
        dict.__init__(self)
        for i in self.fields:
            self[i[0]] = 0  # FIXME: only for number values
        self._buf = None
        self.data = data
        self.offset = offset
        self.length = length or 0
        self.parent = parent
        self.prefix = None
        self.nla_init = init
        self['attrs'] = []
        self['value'] = NotInitialized
        self.value = NotInitialized
        # work only on non-empty mappings
        if self.nla_map:
            if self.__class__.__t_nla_map is not None:
                self.t_nla_map = self.__class__.__t_nla_map
                self.r_nla_map = self.__class__.__r_nla_map
            else:
                self.register_nlas()
        self.r_value_map = dict([(x[1], x[0]) for x in self.value_map.items()])
        if self.header:
            self['header'] = {}

    @property
    def buf(self):
        logging.error('nlmsg.buf is deprecated:\n%s',
                      ''.join(traceback.format_stack()))
        if self._buf is None:
            self._buf = io.BytesIO()
            self._buf.write(self.data[self.offset:self.length or None])
            self._buf.seek(0)
        return self._buf

    def copy(self):
        '''
        Return a decoded copy of the netlink message. Works
        correctly only if the message was encoded, or is
        received from the socket.
        '''
        ret = type(self)(self.buf.getvalue())
        ret.decode()
        return ret

    def reset(self, buf=None):
        self.data = bytearray()
        self.offset = 0

    def register_clean_cb(self, cb):
        global clean_cbs
        if self.parent is not None:
            return self.parent.register_clean_cb(cb)
        else:
            # get the msg_seq -- if applicable
            seq = self.get('header', {}).get('sequence_number', None)
            if seq is not None and seq not in clean_cbs:
                clean_cbs[seq] = []
            # attach the callback
            clean_cbs[seq].append(cb)

    def unregister_clean_cb(self):
        global clean_cbs
        seq = self.get('header', {}).get('sequence_number', None)
        msf = self.get('header', {}).get('flags', 0)
        if (seq is not None) and \
                (not msf & NLM_F_REQUEST) and \
                seq in clean_cbs:
            for cb in clean_cbs[seq]:
                try:
                    cb()
                except:
                    logging.error('Cleanup callback fail: %s' % (cb))
                    logging.error(traceback.format_exc())
            del clean_cbs[seq]

    def _strip_one(self, name):
        for i in tuple(self['attrs']):
            if i[0] == name:
                self['attrs'].remove(i)
        return self

    def strip(self, attrs):
        '''
        Remove an NLA from the attrs chain. The `attrs`
        parameter can be either string, or iterable. In
        the latter case, will be stripped NLAs, specified
        in the provided list.
        '''
        if isinstance(attrs, basestring):
            self._strip_one(attrs)
        else:
            for name in attrs:
                self._strip_one(name)
        return self

    def __ops(self, rvalue, op0, op1):
        lvalue = self.getvalue()
        res = self.__class__()
        for key in lvalue:
            if key not in ('header', 'attrs'):
                if op0 == '__sub__':
                    # operator -, complement
                    if (key not in rvalue) or (lvalue[key] != rvalue[key]):
                        res[key] = lvalue[key]
                elif op0 == '__and__':
                    # operator &, intersection
                    if (key in rvalue) and (lvalue[key] == rvalue[key]):
                        res[key] = lvalue[key]
        if 'attrs' in lvalue:
            res['attrs'] = []
            for attr in lvalue['attrs']:
                if isinstance(attr[1], nla):
                    diff = getattr(attr[1], op0)(rvalue.get_attr(attr[0]))
                    if diff is not None:
                        res['attrs'].append([attr[0], diff])
                else:
                    if op0 == '__sub__':
                        # operator -, complement
                        if rvalue.get_attr(attr[0]) != attr[1]:
                            res['attrs'].append(attr)
                    elif op0 == '__and__':
                        # operator &, intersection
                        if rvalue.get_attr(attr[0]) == attr[1]:
                            res['attrs'].append(attr)
        if not len(res):
            return None
        else:
            if 'header' in res:
                del res['header']
            if 'value' in res:
                del res['value']
            if 'attrs' in res and not len(res['attrs']):
                del res['attrs']
            return res

    def __sub__(self, rvalue):
        '''
        Subjunction operation.
        '''
        return self.__ops(rvalue, '__sub__', '__ne__')

    def __and__(self, rvalue):
        '''
        Conjunction operation.
        '''
        return self.__ops(rvalue, '__and__', '__eq__')

    def __eq__(self, rvalue):
        '''
        Having nla, we are able to use it in operations like::

            if nla == 'some value':
                ...
        '''
        lvalue = self.getvalue()
        if lvalue is self:
            for key in self:
                try:
                    lv = self.get(key)
                    rv = rvalue.get(key)
                    # this strange condition means a simple thing:
                    # None, 0, empty container and NotInitialized in
                    # that context should be treated as equal.
                    if (lv != rv) and not \
                            ((not lv or lv is NotInitialized) and
                             (not rv or rv is NotInitialized)):
                        return False
                except Exception:
                    # on any error -- is not equal
                    return False
            return True
        else:
            return lvalue == rvalue

    @classmethod
    def get_size(self):
        size = 0
        for field in self.fields:
            size += struct.calcsize(field[1])
        return size

    @classmethod
    def nla2name(self, name):
        '''
        Convert NLA name into human-friendly name

        Example: IFLA_ADDRESS -> address

        Requires self.prefix to be set
        '''
        return name[(name.find(self.prefix) + 1) * len(self.prefix):].lower()

    @classmethod
    def name2nla(self, name):
        '''
        Convert human-friendly name into NLA name

        Example: address -> IFLA_ADDRESS

        Requires self.prefix to be set
        '''
        name = name.upper()
        if name.find(self.prefix) == -1:
            name = "%s%s" % (self.prefix, name)
        return name

    def decode(self):
        '''
        Decode the message. The message should have the `buf`
        attribute initialized. e.g.::

            data = sock.recv(16384)
            msg = ifinfmsg(data)

        If you want to customize the decoding process, override
        the method, but don't forget to call parent's `decode()`::

            class CustomMessage(nlmsg):

                def decode(self):
                    nlmsg.decode(self)
                    ...  # do some custom data tuning
        '''
        offset = self.offset
        # decode the header
        if self.header is not None:
            for name, fmt in self.header:
                self['header'][name] = struct.unpack_from(fmt,
                                                          self.data,
                                                          offset)[0]
                offset += struct.calcsize(fmt)
            # update length from header
            # it can not be less than 4
            self.length = max(self['header']['length'], 4)
        # handle the array case
        if self.nla_array:
            self.setvalue([])
            while offset < self.offset + self.length:
                cell = type(self)(data=self.data,
                                  offset=offset,
                                  parent=self)
                cell.nla_array = False
                if cell.cell_header is not None:
                    cell.header = cell.cell_header
                cell.decode()
                self.value.append(cell)
                offset += (cell.length + 4 - 1) & ~ (4 - 1)
        else:
            # decode fields
            if self.pack == 'struct':
                names = []
                formats = []
                for field in self.fields:
                    names.append(field[0])
                    formats.append(field[1])
                fields = ((names, ''.join(formats)), )
            else:
                fields = self.fields

            for name, fmt in fields:
                if fmt in ('s', 'z'):
                    efmt = '%is' % (self.length - 4)
                else:
                    efmt = fmt

                size = struct.calcsize(efmt)
                value = struct.unpack_from(efmt, self.data, offset)
                offset += size

                if len(value) == 1:
                    self[name] = value[0]
                    # cut zero-byte from z-strings
                    # 0x00 -- python3; '\0' -- python2
                    if fmt == 'z' and self[name][-1] \
                            in (0x00, '\0'):
                        self[name] = self[name][:-1]
                else:
                    if self.pack == 'struct':
                        values = list(value)
                        for n in name:
                            if n[0] != '_':
                                self[n] = values.pop(0)
                    else:
                        self[name] = value

        global clean_cbs
        if clean_cbs:
            self.unregister_clean_cb()
        # decode NLA
        try:
            # read NLA chain
            if self.nla_map:
                offset = (offset + 4 - 1) & ~ (4 - 1)
                self.decode_nlas(offset)
        except Exception as e:
            logging.warning(traceback.format_exc())
            raise NetlinkNLADecodeError(e)
        if len(self['attrs']) == 0:
            del self['attrs']
        if self['value'] is NotInitialized:
            del self['value']

    def encode(self):
        '''
        Encode the message into the binary buffer::

            msg.encode()
            sock.send(msg.buf.getvalue())

        If you want to customize the encoding process, override
        the method::

            class CustomMessage(nlmsg):

                def encode(self):
                    ...  # do some custom data tuning
                    nlmsg.encode(self)
        '''
        offset = self.offset
        diff = 0
        # reserve space for the header
        if self.header is not None:
            hsize = struct.calcsize(''.join([x[1] for x in self.header]))
            self.data.extend([0] * hsize)
            offset += hsize

        # handle the array case
        if self.nla_array:
            for value in self.getvalue():
                cell = type(self)(data=self.data,
                                  offset=offset,
                                  parent=self)
                cell.nla_array = False
                if cell.cell_header is not None:
                    cell.header = cell.cell_header
                cell.setvalue(value)
                cell.encode()
                offset += (cell.length + 4 - 1) & ~ (4 - 1)
        elif self.getvalue() is not None:
            for name, fmt in self.fields:
                value = self[name]

                if fmt == 's':
                    length = len(value)
                    efmt = '%is' % (length)
                elif fmt == 'z':
                    length = len(value) + 1
                    efmt = '%is' % (length)
                else:
                    length = struct.calcsize(fmt)
                    efmt = fmt

                self.data.extend([0] * length)

                # in python3 we should force it
                if sys.version[0] == '3':
                    if isinstance(value, str):
                        value = bytes(value, 'utf-8')
                    elif isinstance(value, float):
                        value = int(value)
                elif sys.version[0] == '2':
                    if isinstance(value, unicode):
                        value = value.encode('utf-8')

                try:
                    if fmt[-1] == 'x':
                        struct.pack_into(efmt, self.data, offset)
                    elif type(value) in (list, tuple, set):
                        struct.pack_into(efmt, self.data, offset, *value)
                    else:
                        struct.pack_into(efmt, self.data, offset, value)
                except struct.error:
                    logging.error(''.join(traceback.format_stack()))
                    logging.error(traceback.format_exc())
                    logging.error("error pack: %s %s %s" %
                                  (efmt, value, type(value)))
                    raise

                offset += length

            diff = ((offset + 4 - 1) & ~ (4 - 1)) - offset
            offset += diff
            self.data.extend([0] * diff)
        # write NLA chain
        if self.nla_map:
            offset = self.encode_nlas(offset)
        # calculate the size and write it
        if self.header is not None:
            self.length = self['header']['length'] = (offset -
                                                      self.offset -
                                                      diff)
            offset = self.offset
            for name, fmt in self.header:
                struct.pack_into(fmt,
                                 self.data,
                                 offset,
                                 self['header'][name])
                offset += struct.calcsize(fmt)

    def setvalue(self, value):
        if isinstance(value, dict):
            self.update(value)
        else:
            try:
                value = self.r_value_map.get(value, value)
            except TypeError:
                pass
            self['value'] = value
            self.value = value

    def get_encoded(self, attr, default=None):
        '''
        Return the first encoded NLA by name
        '''
        return self.get_attr(attr, default, 'encoded')

    def get_attr(self, attr, default=None, fmt='raw'):
        '''
        Return the first attr by name or None
        '''
        try:
            attrs = self.get_attrs(attr, fmt)
        except KeyError:
            return default
        if attrs:
            return attrs[0]
        else:
            return default

    def get_attrs(self, attr, fmt='raw'):
        '''
        Return attrs by name
        '''
        fmt_map = {'raw': 1,
                   'encoded': 2}
        return [i[fmt_map[fmt]] for i in self['attrs'] if i[0] == attr]

    def load(self, dump):
        '''
        Load packet from a structure
        '''
        if isinstance(dump, dict):
            for (k, v) in dump.items():
                if k == 'header':
                    self['header'].load(dump['header'])
                else:
                    self[k] = v
        else:
            self.setvalue(dump)

    def dump(self):
        '''
        Dump packet as a simple types struct
        '''
        a = self.getvalue()
        if isinstance(a, dict):
            ret = {}
            for (k, v) in a.items():
                if k == 'header':
                    ret['header'] = a['header'].dump()
                elif k == 'attrs':
                    ret['attrs'] = attrs = []
                    for i in a['attrs']:
                        if isinstance(i[1], nlmsg_base):
                            attrs.append([i[0], i[1].dump()])
                        elif isinstance(i[1], set):
                            attrs.append([i[0], tuple(i[1])])
                        else:
                            attrs.append([i[0], i[1]])
                else:
                    ret[k] = v
        else:
            ret = a
        return ret

    def getvalue(self):
        '''
        Atomic NLAs return their value in the 'value' field,
        not as a dictionary. Complex NLAs return whole dictionary.
        '''
        if self.value != NotInitialized:
            # value decoded by custom decoder
            return self.value

        if 'value' in self and self['value'] != NotInitialized:
            # raw value got by generic decoder
            return self.value_map.get(self['value'], self['value'])

        return self

    def register_nlas(self):
        '''
        Convert 'nla_map' tuple into two dictionaries for mapping
        and reverse mapping of NLA types.

        ex: given::

            nla_map = (('TCA_HTB_UNSPEC', 'none'),
                       ('TCA_HTB_PARMS', 'htb_parms'),
                       ('TCA_HTB_INIT', 'htb_glob'))

        creates::

            t_nla_map = {0: (<class 'pyroute2...none'>, 'TCA_HTB_UNSPEC'),
                         1: (<class 'pyroute2...htb_parms'>, 'TCA_HTB_PARMS'),
                         2: (<class 'pyroute2...htb_glob'>, 'TCA_HTB_INIT')}
            r_nla_map = {'TCA_HTB_UNSPEC': (<class 'pyroute2...none'>, 0),
                         'TCA_HTB_PARMS': (<class 'pyroute2...htb_parms'>, 1),
                         'TCA_HTB_INIT': (<class 'pyroute2...htb_glob'>, 2)}

        nla_map format::

            nla_map = (([ID, ] NAME, TYPE[, FLAGS]), ...)

        Items in `[...]` are optional. If ID is not given, then the map will
        be autonumerated from 0. If flags are not given, they are 0 by default.

        '''
        # clean up NLA mappings
        self.t_nla_map = {}
        self.r_nla_map = {}

        # fix nla flags
        nla_map = []
        for item in self.nla_map:
            if not isinstance(item[-1], int):
                item = list(item)
                item.append(0)
            nla_map.append(item)

        # detect, whether we have pre-defined keys
        if not isinstance(nla_map[0][0], int):
            # create enumeration
            nla_types = enumerate((i[0] for i in nla_map))
            # that's a little bit tricky, but to reduce
            # the required amount of code in modules, we have
            # to jump over the head
            zipped = [(k[1][0], k[0][0], k[0][1], k[0][2]) for k in
                      zip(nla_map, nla_types)]
        else:
            zipped = nla_map

        for (key, name, nla_class, nla_flags) in zipped:
            # it is an array
            if nla_class[0] == '*':
                nla_class = nla_class[1:]
                nla_array = True
            else:
                nla_array = False
            # are there any init call in the string?
            lb = nla_class.find('(')
            rb = nla_class.find(')')
            if 0 < lb < rb:
                init = nla_class[lb + 1:rb]
                nla_class = nla_class[:lb]
            else:
                init = None
            # lookup NLA class
            if nla_class == 'recursive':
                nla_class = type(self)
            else:
                nla_class = getattr(self, nla_class)
            # update mappings
            prime = {'class': nla_class,
                     'type': key,
                     'name': name,
                     'nla_flags': nla_flags,
                     'nla_array': nla_array,
                     'init': init}
            self.t_nla_map[key] = self.r_nla_map[name] = prime

        self.__class__.__t_nla_map = self.t_nla_map
        self.__class__.__r_nla_map = self.r_nla_map

    def encode_nlas(self, offset):
        '''
        Encode the NLA chain. Should not be called manually, since
        it is called from `encode()` routine.
        '''
        for i in self['attrs']:
            if i[0] in self.r_nla_map:
                prime = self.r_nla_map[i[0]]
                msg_class = prime['class']
                # is it a class or a function?
                if isinstance(msg_class, types.FunctionType):
                    # if it is a function -- use it to get the class
                    msg_class = msg_class(self)
                # encode NLA
                nla = msg_class(data=self.data,
                                offset=offset,
                                parent=self,
                                init=prime['init'])
                nla.nla_flags |= prime['nla_flags']
                nla.nla_array = prime['nla_array']
                nla['header']['type'] = prime['type'] | nla.nla_flags
                nla.setvalue(i[1])
                try:
                    nla.encode()
                except:
                    raise
                else:
                    if len(i) == 2:
                        i.append(nla)
                    elif len(i) == 3:
                        i[2] = nla
                offset += (nla.length + 4 - 1) & ~ (4 - 1)
        return offset

    def decode_nlas(self, offset):
        '''
        Decode the NLA chain. Should not be called manually, since
        it is called from `decode()` routine.
        '''
        while offset - self.offset <= self.length - 4:
            nla = None
            # pick the length and the type
            (length, msg_type) = struct.unpack_from('HH', self.data, offset)
            # first two bits of msg_type are flags:
            msg_type = msg_type & ~(NLA_F_NESTED | NLA_F_NET_BYTEORDER)
            # rewind to the beginning
            length = min(max(length, 4), (self.length - offset + self.offset))
            # we have a mapping for this NLA
            if msg_type in self.t_nla_map:

                prime = self.t_nla_map[msg_type]
                # get the class
                msg_class = self.t_nla_map[msg_type]['class']
                # is it a class or a function?
                if isinstance(msg_class, types.FunctionType):
                    # if it is a function -- use it to get the class
                    msg_class = msg_class(self,
                                          data=self.data,
                                          offset=offset)
                # decode NLA
                nla = msg_class(data=self.data,
                                offset=offset,
                                parent=self,
                                init=prime['init'])
                nla.nla_array = prime['nla_array']
                try:
                    nla.decode()
                    nla.nla_flags = msg_type & (NLA_F_NESTED |
                                                NLA_F_NET_BYTEORDER)
                    msg_name = prime['name']
                except Exception:
                    logging.warning("decoding %s" % (prime['name']))
                    logging.warning(traceback.format_exc())
                    msg_name = 'UNDECODED'
                    msg_value = hexdump(str(self.data[offset:offset+length]))
                else:
                    msg_value = nla.getvalue()
            else:
                msg_name = 'UNKNOWN'
                msg_value = hexdump(str(self.data[offset:offset+length]))

            self['attrs'].append([msg_name, msg_value])
            offset += (length + 4 - 1) & ~ (4 - 1)


class nla_base(nlmsg_base):
    '''
    The NLA base class. Use `nla_header` class as the header.
    '''
    header = (('length', 'H'),
              ('type', 'H'))


class nlmsg_atoms(nlmsg_base):
    '''
    A collection of base NLA types
    '''
    class none(nla_base):
        '''
        'none' type is used to skip decoding of NLA. You can
        also use 'hex' type to dump NLA's content.
        '''
        def decode(self):
            nla_base.decode(self)
            self.value = None

    class flag(nla_base):
        '''
        'flag' type is used to denote attrs that have no payload
        '''
        fields = []

        def decode(self):
            nla_base.decode(self)
            self.value = True

    class uint8(nla_base):
        fields = [('value', 'B')]

    class uint16(nla_base):
        fields = [('value', 'H')]

    class uint32(nla_base):
        fields = [('value', 'I')]

    class uint64(nla_base):
        fields = [('value', 'Q')]

    class int32(nla_base):
        fields = [('value', 'i')]

    class be8(nla_base):
        fields = [('value', '>B')]

    class be16(nla_base):
        fields = [('value', '>H')]

    class be32(nla_base):
        fields = [('value', '>I')]

    class be64(nla_base):
        fields = [('value', '>Q')]

    class ipXaddr(nla_base):
        fields = [('value', 's')]
        family = None

        def encode(self):
            self['value'] = inet_pton(self.family, self.value)
            nla_base.encode(self)

        def decode(self):
            nla_base.decode(self)
            self.value = inet_ntop(self.family, self['value'])

    class ip4addr(ipXaddr):
        '''
        Explicit IPv4 address type class.
        '''
        family = AF_INET

    class ip6addr(ipXaddr):
        '''
        Explicit IPv6 address type class.
        '''
        family = AF_INET6

    class ipaddr(nla_base):
        '''
        This class is used to decode IP addresses according to
        the family. Socket library currently supports only two
        families, AF_INET and AF_INET6.

        We do not specify here the string size, it will be
        calculated in runtime.
        '''
        fields = [('value', 's')]

        def encode(self):
            # use real provided family, not implicit
            if self.value.find(':') > -1:
                family = AF_INET6
            else:
                family = AF_INET
            self['value'] = inet_pton(family, self.value)
            nla_base.encode(self)

        def decode(self):
            nla_base.decode(self)
            # use real provided family, not implicit
            if self.length > 8:
                family = AF_INET6
            else:
                family = AF_INET
            self.value = inet_ntop(family, self['value'])

    class target(nla_base):
        '''
        A universal target class. The target type depends on the msg
        family:

        * AF_INET: IPv4 addr, string: "127.0.0.1"
        * AF_INET6: IPv6 addr, string: "::1"
        * AF_MPLS: MPLS labels, 0 .. k: [{"label": 0x20, "ttl": 16}, ...]
        '''
        fields = [('value', 's')]
        family = None

        def get_family(self):
            if self.family is not None:
                return self.family
            pointer = self
            while pointer.parent is not None:
                pointer = pointer.parent
            return pointer.get('family', AF_UNSPEC)

        def encode(self):
            family = self.get_family()
            if family in (AF_INET, AF_INET6):
                self['value'] = inet_pton(family, self.value)
            elif family == AF_MPLS:
                self['value'] = b''
                if isinstance(self.value, (set, list, tuple)):
                    labels = self.value
                else:
                    if 'label' in self:
                        labels = [{'label': self.get('label', 0),
                                   'tc': self.get('tc', 0),
                                   'bos': self.get('bos', 0),
                                   'ttl': self.get('ttl', 0)}]
                    else:
                        labels = []
                for record in labels:
                    label = (record.get('label', 0) << 12) |\
                        (record.get('tc', 0) << 9) |\
                        ((1 if record.get('bos') else 0) << 8) |\
                        record.get('ttl', 0)
                    self['value'] += struct.pack('>I', label)
            else:
                raise TypeError('socket family not supported')
            nla_base.encode(self)

        def decode(self):
            nla_base.decode(self)
            family = self.get_family()
            if family in (AF_INET, AF_INET6):
                self.value = inet_ntop(family, self['value'])
            elif family == AF_MPLS:
                self.value = []
                for i in range(len(self['value']) // 4):
                    label = struct.unpack('>I', self['value'][i*4:i*4+4])[0]
                    record = {'label': (label & 0xFFFFF000) >> 12,
                              'tc': (label & 0x00000E00) >> 9,
                              'bos': (label & 0x00000100) >> 8,
                              'ttl': label & 0x000000FF}
                    self.value.append(record)
            else:
                raise TypeError('socket family not supported')

    class mpls_target(target):
        family = AF_MPLS

    class l2addr(nla_base):
        '''
        Decode MAC address.
        '''
        fields = [('value', '=6s')]

        def encode(self):
            self['value'] = struct.pack('BBBBBB',
                                        *[int(i, 16) for i in
                                          self.value.split(':')])
            nla_base.encode(self)

        def decode(self):
            nla_base.decode(self)
            self.value = ':'.join('%02x' % (i) for i in
                                  struct.unpack('BBBBBB', self['value']))

    class hex(nla_base):
        '''
        Represent NLA's content with header as hex string.
        '''
        fields = [('value', 's')]

        def decode(self):
            nla_base.decode(self)
            self.value = hexdump(self['value'])

    class array(nla_base):
        '''
        Array of simple data type
        '''
        fields = [('value', 's')]
        _fmt = None

        @property
        def fmt(self):
            # try to get format from parent
            # work only with elementary types
            if self._fmt is not None:
                return self._fmt
            try:
                fclass = getattr(self.parent, self.nla_init)
                self._fmt = fclass.fields[0][1]
            except Exception:
                self._fmt = self.nla_init
            return self._fmt

        def encode(self):
            fmt = '%s%i%s' % (self.fmt[:-1], len(self.value), self.fmt[-1:])
            self['value'] = struct.pack(fmt, self.value)
            nla_base.encode(self)

        def decode(self):
            nla_base.decode(self)
            data_length = len(self['value'])
            element_size = struct.calcsize(self.fmt)
            array_size = data_length // element_size
            trail = (data_length % element_size) or -data_length
            data = self['value'][:-trail]
            fmt = '%s%i%s' % (self.fmt[:-1], array_size, self.fmt[-1:])
            self.value = struct.unpack(fmt, data)

    class cdata(nla_base):
        '''
        Binary data
        '''
        fields = [('value', 's')]

    class string(nla_base):
        '''
        UTF-8 string.
        '''
        fields = [('value', 's')]

        def encode(self):
            if isinstance(self['value'], str) and sys.version[0] == '3':
                self['value'] = bytes(self['value'], 'utf-8')
            nla_base.encode(self)

        def decode(self):
            nla_base.decode(self)
            self.value = self['value']
            if sys.version_info[0] >= 3:
                try:
                    self.value = self.value.decode('utf-8')
                except UnicodeDecodeError:
                    pass  # Failed to decode, keep undecoded value

    class asciiz(string):
        '''
        Zero-terminated string.
        '''
        # FIXME: move z-string hacks from general decode here?
        fields = [('value', 'z')]

    # FIXME: support NLA_FLAG and NLA_MSECS as well.
    #
    # aliases to support standard kernel attributes:
    #
    binary = cdata       # NLA_BINARY
    nul_string = asciiz  # NLA_NUL_STRING


class nla(nla_base, nlmsg_atoms):
    '''
    Main NLA class
    '''
    def decode(self):
        nla_base.decode(self)
        del self['header']


class nlmsg(nlmsg_atoms):
    '''
    Main netlink message class
    '''
    header = (('length', 'I'),
              ('type', 'H'),
              ('flags', 'H'),
              ('sequence_number', 'I'),
              ('pid', 'I'))


class genlmsg(nlmsg):
    '''
    Generic netlink message
    '''
    fields = (('cmd', 'B'),
              ('version', 'B'),
              ('reserved', 'H'))


class ctrlmsg(genlmsg):
    '''
    Netlink control message
    '''
    # FIXME: to be extended
    nla_map = (('CTRL_ATTR_UNSPEC', 'none'),
               ('CTRL_ATTR_FAMILY_ID', 'uint16'),
               ('CTRL_ATTR_FAMILY_NAME', 'asciiz'),
               ('CTRL_ATTR_VERSION', 'uint32'),
               ('CTRL_ATTR_HDRSIZE', 'uint32'),
               ('CTRL_ATTR_MAXATTR', 'uint32'),
               ('CTRL_ATTR_OPS', '*ops'),
               ('CTRL_ATTR_MCAST_GROUPS', '*mcast_groups'))

    class ops(nla):
        nla_map = (('CTRL_ATTR_OP_UNSPEC', 'none'),
                   ('CTRL_ATTR_OP_ID', 'uint32'),
                   ('CTRL_ATTR_OP_FLAGS', 'uint32'))

    class mcast_groups(nla):
        nla_map = (('CTRL_ATTR_MCAST_GRP_UNSPEC', 'none'),
                   ('CTRL_ATTR_MCAST_GRP_NAME', 'asciiz'),
                   ('CTRL_ATTR_MCAST_GRP_ID', 'uint32'))
