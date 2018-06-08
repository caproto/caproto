import struct
import array
import logging
import copy

from collections import (OrderedDict, namedtuple)

from caproto import CaprotoError
from .helpers import FrozenDict
from .types import (FieldType, ComplexType, FieldDesc, FieldArrayType,
                    TypeCode,
                    type_to_array_code, _type_code_byte_size, Decoded,
                    type_name_to_type)
from .const import (MAX_INT32, SYS_ENDIAN)
from .introspection import (walk_field_description_with_values,
                            SelectedUnionValue, get_definition_from_namespaces,
                            definition_line_to_info, variant_desc_from_value,
                            generate_hash
                            )


logger = logging.getLogger(__name__)

IdCache = namedtuple('IdCache', 'ours theirs')
FieldDescCache = namedtuple('FdCache', 'user_types')

SerializeCache = namedtuple('SerializeCache',
                            'ours theirs user_types ioid_interfaces')
NullCache = SerializeCache(ours=FrozenDict(),
                           theirs=FrozenDict(),
                           user_types=FrozenDict(),
                           ioid_interfaces=FrozenDict(),
                           )


class SerializationFailure(CaprotoError):
    ...


def _serialize_field_data(desc, fd_byte, value, *,
                          endian, cache, nested_types):
    'Serialize data'
    serialized = []
    array_type = fd_byte.array_type
    type_name = fd_byte.type_name
    is_string = (type_name in ('string', 'bounded_string'))

    # TODO bounded string max
    if is_string:
        if array_type == FieldArrayType.scalar:
            value = [value]
        else:
            serialized = [serialize_size(len(value), endian=endian)]
        for v in value:
            encoded = v.encode('utf-8')
            serialized.extend([serialize_size(len(encoded), endian=endian),
                               encoded])
        return serialized
    else:
        try:
            len(value)
        except TypeError:
            value = (value, )

    if type_name == 'struct':
        serialized.append(serialize_size(len(value), endian=endian))
        for v in value:
            serialized.append(serialize_data(desc, v,
                                             endian=endian,
                                             cache=cache))
        return serialized

    if array_type.has_serialization_size or is_string:
        serialized.append(serialize_size(len(value), endian=endian))

    if type_name == 'any':
        if isinstance(value, (str, )):
            # TODO any other types potentially mistaken?
            value = (value, )

        serialized.extend(
            serialize_data(variant_desc_from_value('_unused_', v),
                           values=v, endian=endian, cache=cache,
                           nested_types=nested_types)
            for v in value
        )
    else:
        arr = array.array(type_to_array_code[type_name], value)
        if endian != SYS_ENDIAN:
            arr.byteswap()
        serialized.append(arr)

    return serialized


def _serialize_field_interface(desc, instruct_to_cache, *, endian, cache):
    'Serialize a field of introspection data'
    type_name = desc['type_name']
    array_type = desc['array_type']

    if type_name not in ('union', 'struct'):
        if array_type.has_field_desc_size:
            return [serialize_size(desc['size'], endian=endian)]
        else:
            return []

    struct_name = (desc['struct_name']
                   if desc['struct_name'] != _default_names[type_name]
                   else '')
    buf = _serialize_string(struct_name, endian=endian)

    fields = desc['fields']

    buf.append(serialize_size(len(fields), endian=endian))
    for name, field_desc in desc['fields'].items():
        buf.extend(_serialize_string(name, endian=endian))
        serialized = serialize_introspection_data(
            field_desc, instruct_to_cache=instruct_to_cache, endian=endian,
            cache=cache)

        buf.extend(serialized)
        # TODO id_ and tag may have to be stored in field_desc
    return buf


def serialize_introspection_data(desc, tag=None, instruct_to_cache=True,
                                 *, endian, cache, hash_key=None):
    '''Serialize field description introspection data

    Returns
    -------
    list_of_bytes
    '''
    if desc is None:
        return bytes([TypeCode.NULL_TYPE_CODE])

    type_name = desc['type_name']

    if (type_name in ('union', 'struct') and cache.theirs is not None
            and instruct_to_cache):
        if hash_key is None:
            hash_key = generate_hash(desc, cache=cache)

        if hash_key in cache.theirs:
            id_ = cache.theirs[hash_key]
            return [bytes([TypeCode.ONLY_ID_TYPE_CODE]),
                    serialize_identifier(id_, endian=endian)]

        if cache.theirs:
            # TODO: LRU cache with only 65k entries
            id_ = max(cache.theirs.values()) + 1
        else:
            id_ = 1

        cache.theirs[hash_key] = id_
        buf = [bytes([TypeCode.FULL_WITH_ID_TYPE_CODE]),
               serialize_identifier(id_, endian=endian)]
    else:
        buf = []

    buf.append(bytes(_fd_byte_from_desc(desc)))
    buf.extend(
        _serialize_field_interface(
            desc, instruct_to_cache=instruct_to_cache, endian=endian,
            cache=cache))
    return buf


def _fd_byte_from_desc(fd):
    'Field description dict -> FieldDesc'
    type_, type_specific = type_name_to_type[fd['type_name']]
    return FieldDesc(type_specific, fd['array_type'], type_)


def serialize_data(desc, values, *, endian, cache, nested_types=None):
    'Serialize data using its FieldDescription'
    serialized = []

    if nested_types is None:
        nested_types = desc.get('nested_types', {})

    for info in walk_field_description_with_values(desc, values,
                                                   cache.user_types):
        fd = info.field_desc
        value = info.value

        type_name = fd['type_name']
        meta = None
        if type_name == 'any':
            fd = value.field_desc
            value = value.value
            meta = bytes(_fd_byte_from_desc(fd))
            # TODO rework this like deserialize_data to make handling similar
            # between the complex types (also, this won't handle variant arrays
            # as-is)
        elif isinstance(value, SelectedUnionValue):
            meta = serialize_size(value.selector, endian=endian)
            value = value.value

        if meta is not None:
            serialized.append(meta)

        try:
            field_bytes = _serialize_field_data(fd, info.fd_byte, value,
                                                endian=endian, cache=cache,
                                                nested_types=nested_types)
        except Exception as ex:
            raise SerializationFailure(
                f'Serializing {value!r} to {info.fd_byte}') from ex

        serialized.extend(field_bytes)

    return b''.join(serialized)


def serialize_size(sz, *, endian):
    'Sizes/lengths are encoded in 3 ways, depending on the size'
    if sz is None:
        # TODO_DOCS: this is misrepresented in the docs
        # an empty size is represented as 255 (-1)
        return struct.pack(endian + 'B', 255)
    elif sz < 254:
        return struct.pack(endian + 'B', sz)
    elif sz < MAX_INT32:
        return struct.pack(endian + 'BI', 254, sz)

    return struct.pack(endian + 'BIQ', 254, MAX_INT32, sz)


def _deserialize_size(buf, *, endian):
    # TODO_DOCS: this is misrepresented in the docs
    b0 = buf[0]
    if b0 == 255:
        # null size
        return Decoded(data=None, buffer=buf[1:], offset=1)
    elif b0 < 254:
        return Decoded(data=b0, buffer=buf[1:], offset=1)

    int32, = struct.unpack(endian + 'I', buf[1:5])
    if int32 != MAX_INT32:
        return Decoded(data=int32, buffer=buf[5:], offset=5)

    return Decoded(data=struct.unpack(endian + 'Q', buf[5:13])[0],
                   buffer=buf[13:],
                   offset=13)


def serialize_identifier(id_, *, endian):
    return struct.pack(endian + 'h', id_)


def deserialize_identifier(buf, *, endian):
    # NOTE: IDs signed according to docs?
    return Decoded(data=struct.unpack(endian + 'h', buf[:2])[0],
                   buffer=buf[2:],
                   offset=2)


def deserialize_introspection_data(buf, *, endian, cache, data=None, depth=0,
                                   nested_types=None):
    if data is None:
        data = {}
    if depth == 0 and nested_types is None:
        nested_types = OrderedDict()

    buf = memoryview(buf)
    type_code = buf[0]
    interface_id = None
    offset = 0

    if type_code == TypeCode.NULL_TYPE_CODE:
        return Decoded(data=None, buffer=buf[1:], offset=1)
    elif type_code == TypeCode.FULL_TAGGED_ID_TYPE_CODE:
        # TODO: type of tag is unclear?
        raise NotImplementedError('TODO')
    elif type_code in (TypeCode.ONLY_ID_TYPE_CODE,
                       TypeCode.FULL_WITH_ID_TYPE_CODE):
        buf = buf[1:]
        offset = 1

        interface_id, buf, off = deserialize_identifier(buf, endian=endian)
        offset += off

        if type_code == TypeCode.ONLY_ID_TYPE_CODE:
            if cache.ours is None:
                raise KeyError('Referencing empty cache')
            intf = copy.deepcopy(cache.ours[interface_id])
            intf.update(data)
            return Decoded(data=intf, buffer=buf, offset=offset)

        # otherwise, fall through...

    fd_byte, buf, off = _deserialize_field_desc_byte(buf)
    offset += off

    intf, buf, off = _deserialize_field_interface(fd_byte, buf, data,
                                                  endian=endian, cache=cache,
                                                  depth=depth,
                                                  nested_types=nested_types)
    offset += off

    if depth == 0 and 'struct_name' in intf:
        # Summarize types defined inside the structure
        intf['nested_types'] = nested_types

    if interface_id is not None:
        cache.ours[interface_id] = intf
    return Decoded(data=intf, buffer=buf, offset=offset)


def _deserialize_field_desc_byte(buf):
    fd_byte = FieldDesc.from_buffer(bytearray(buf[:1]))
    buf, offset = buf[1:], 1
    return Decoded(data=fd_byte, buffer=buf, offset=offset)


def _serialize_string(string, *, endian):
    '''
    Serialize a string

    Returns
    -------
    [serialized_length, serialized_utf8_bytestring]
    '''
    encoded = string.encode('utf-8')
    return [serialize_size(len(encoded), endian=endian), encoded]


def _deserialize_string(buf, *, endian):
    sz, buf, consumed = _deserialize_size(buf, endian=endian)
    return Decoded(data=str(buf[:sz], 'utf-8'),
                   buffer=buf[sz:],
                   offset=consumed + sz)


# Names represented as zero-length strings when serialized
_default_names = {
    'struct': 'structure',
    'union': 'union',
}


def _deserialize_field_interface(field_desc, buf, data,
                                 *, endian, cache, nested_types, depth):
    offset = 0
    field_type, array_type = field_desc.type, field_desc.array_type
    data['array_type'] = array_type
    data['type_name'] = field_desc.type_name

    # scalar = (array_type == FieldArrayType.scalar)

    if array_type.has_field_desc_size:
        size, buf, off = _deserialize_size(buf, endian=endian)
        offset += off
        data['size'] = size

    if field_type == FieldType.complex:
        complex_type = field_desc.type_specific
        # DOCS_TODO docs don't mention next value is number of elements

        if complex_type in (ComplexType.union, ComplexType.structure):
            if array_type == FieldArrayType.variable_array:
                # full field description for this, not just fields
                data['struct_name'] = ''
                field_data = dict(name='')
                st, buf, off = deserialize_introspection_data(
                    buf, endian=endian, cache=cache,
                    nested_types=nested_types, data=field_data,
                    depth=depth + 1)
                offset += off
                data['fields'] = OrderedDict([('', st)])
                return Decoded(data=data, buffer=buf, offset=offset)

            struct_name, buf, off = _deserialize_string(buf, endian=endian)
            offset += off

            if struct_name:
                nested_types[struct_name] = data
            else:
                # NOTE: mirroring pvData here, zero-length struct name means
                # that a default name should be used
                struct_name = _default_names[data['type_name']]

            data['struct_name'] = struct_name

            if 'name' not in data:
                # this happens for a top-level structure
                data['name'] = struct_name

            num_fields, buf, off = _deserialize_size(buf, endian=endian)
            offset += off

            fields = OrderedDict()
            for field in range(num_fields):
                field_name, buf, off = _deserialize_string(buf, endian=endian)
                offset += off

                field_data = dict(name=field_name)

                st, buf, off = deserialize_introspection_data(
                    buf, endian=endian, cache=cache,
                    nested_types=nested_types, data=field_data,
                    depth=depth + 1)
                offset += off
                fields[field_name] = st

            data['fields'] = fields
        elif complex_type == ComplexType.bounded_string:
            size, buf, off = _deserialize_size(buf, endian=endian)
            offset += off
            data['size'] = size

    return Decoded(data=data, buffer=buf, offset=offset)


def _deserialize_complex_data(fd, buf, *, endian, cache, nested_types):
    'Deserialize data from a struct, variant, or union'
    array_type = fd['array_type']
    type_name = fd['type_name']

    if array_type != FieldArrayType.scalar:
        count, buf, off = _deserialize_size(buf, endian=endian)
        offset = off
    else:
        count = 1
        offset = 0

    data = []
    for i in range(count):
        if type_name == 'struct':
            # consistent value interface for structs
            value_intf = fd
            # TODO_DOCS i don't believe this is documented
            if array_type == FieldArrayType.scalar:
                filled = True
            else:
                filled = buf[0]
                buf = buf[1:]
                offset += 1
            if not filled:
                data.append(None)
                continue
        elif type_name == 'any':
            # get the field description
            value_intf, buf, off = deserialize_introspection_data(
                buf, endian=endian, cache=cache, depth=1,
                data=dict(name=fd['name']),
                nested_types=nested_types)
            offset += off
        else:  # union
            field_index, buf, off = _deserialize_size(buf, endian=endian)
            offset += off

            fields = fd['fields']
            selector_key = tuple(fields.keys())[field_index]
            value_intf = fields[selector_key]

        if value_intf is None:
            # can be none for variant types
            di = None
        else:
            di, buf, off = deserialize_data(
                value_intf, buf, endian=endian, cache=cache,
                nested_types=nested_types)
            offset += off

        if type_name == 'union':
            di = OrderedDict(
                [('_selector_', field_index),
                 (selector_key, di),
                 ]
            )

        data.append(di)

    if array_type == FieldArrayType.scalar:
        data = data[0]

    return Decoded(data=data, buffer=buf, offset=offset)


def _deserialize_data_from_field_desc(fd, buf,
                                      *, endian, cache, nested_types):
    'Given field description metadata, deserialize data from a single field'
    type_name = fd['type_name']

    if type_name in ('any', 'union', 'struct'):
        return _deserialize_complex_data(fd, buf, endian=endian, cache=cache,
                                         nested_types=nested_types)

    offset = 0
    array_type = fd['array_type']
    is_string = (type_name in ('string', 'bounded_string'))

    fd_byte = _fd_byte_from_desc(fd)
    if array_type.has_serialization_size:
        size, buf, off = _deserialize_size(buf, endian=endian)
        offset += off
    else:
        size = fd.get('size', 1)

    if is_string:
        value = []
        if fd_byte.array_type == FieldArrayType.scalar:
            size = 1
        for i in range(size):
            string_, buf, off = _deserialize_string(buf, endian=endian)
            offset += off
            value.append(string_)
    else:
        byte_size = size * _type_code_byte_size[type_name]

        value = array.array(type_to_array_code[type_name])
        if len(buf) < byte_size:
            raise SerializationFailure(
                f'Deserialization buffer does not hold all values. Expected '
                f'byte length {byte_size}, actual length {len(buf)}. '
                f'Value of type {type_name}[{size}] at offset of {offset}'
            )

        value.frombytes(buf[:byte_size])
        if endian != SYS_ENDIAN:
            value.byteswap()

        buf = buf[byte_size:]
        offset += byte_size

    if array_type == FieldArrayType.scalar and size == 1:
        value = value[0]

    return Decoded(data=value, buffer=buf, offset=offset)


def deserialize_data(fd, buf, *, endian, cache, nested_types=None,
                     bitset=None):
    'Deserialize data associated with a field description'
    if fd is None or not fd:
        raise ValueError('Must specify field description')

    buf = memoryview(buf)

    if nested_types is None:
        nested_types = fd.get('nested_types', {})

    fd = get_definition_from_namespaces(fd, nested_types, cache.user_types)

    if 'fields' not in fd:
        # A single value - don't make it into a dictionary
        # TODO investigate recursion here when struct name is not found
        # TODO simple test is to undefined 'channel_with_id'
        return _deserialize_data_from_field_desc(
            fd, buf, endian=endian, cache=cache, nested_types=nested_types)

    # debug_logging = logger.isEnabledFor(logging.DEBUG)
    debug_logging = True
    ret = OrderedDict()
    offset = 0

    for index, (field_name, fd) in enumerate(fd['fields'].items()):
        if bitset is not None and index not in bitset:
            logger.debug('At offset %d field: %s (%s) skipped by bitset',
                         offset, field_name, bitset)
            continue

        logger.debug('Offset: %d Field: %s (%s)', offset, field_name,
                     fd['type_name'])

        fd = get_definition_from_namespaces(fd, nested_types,
                                            cache.user_types)
        deserialized = _deserialize_data_from_field_desc(
            fd, buf, endian=endian, cache=cache, nested_types=nested_types)

        if deserialized is not None:
            start_buf = buf

            data, buf, off = deserialized
            offset += off
            ret[field_name] = data

            if debug_logging:
                logger.debug("Deserialized: %s",
                             ' '.join(hex(v)
                                      for v in start_buf[:min((off, 1000))]))
                logger.debug("-> %s = %s", field_name, repr(data)[:1000])

    return Decoded(data=ret, buffer=buf, offset=offset)


def serialize_pvrequest(req, instruct_to_cache=True,
                        *, endian, cache):
    'Serialize a PVRequest - string or structure'
    from .pvrequest import (pvrequest_string_to_structure,
                            pvrequest_to_structure, PVRequest)
    if isinstance(req, str):
        desc = pvrequest_string_to_structure(req)
    elif isinstance(req, PVRequest):
        desc = pvrequest_to_structure(req)
    else:
        assert isinstance(req, dict)
        desc = req
    return serialize_introspection_data(
        desc, instruct_to_cache=instruct_to_cache, endian=endian, cache=cache)


def deserialize_pvrequest(req, *, endian):
    raise NotImplementedError('TODO')


# Look-up table for bitsets
_bitset_lut = [1 << i for i in range(8)]


def serialize_bitset(bitset, *, endian):
    'Serialize a BitSet'
    if not bitset:
        return serialize_size(0, endian=endian)

    start = 0
    end = 7
    current = 0
    ret = bytearray()

    for bit in sorted(set(bitset)):
        while bit > end:
            ret.append(current)
            current = 0
            start, end = start + 8, end + 8
        current |= _bitset_lut[bit - start]

    if current:
        ret.append(current)

    return serialize_size(len(ret), endian=endian) + ret


def deserialize_bitset(buf, *, endian):
    'Deserialize a BitSet'
    sz, buf, offset = _deserialize_size(buf, endian=endian)

    byte_start = 0
    bitset = set()
    for ch in buf[:sz]:
        for bit_num, mask in enumerate(_bitset_lut):
            if ch & mask:
                bitset.add(byte_start + bit_num)
        byte_start += 8

    return Decoded(data=bitset, buffer=buf[sz:], offset=offset + sz)


def serialize_message_field(type_name, field_name, value,
                            *, endian, cache,
                            instruct_to_cache=True,
                            interface=None,
                            nested_types=None):
    if type_name == 'FieldDesc':
        return serialize_introspection_data(
            value, instruct_to_cache=instruct_to_cache, endian=endian,
            cache=cache)
    elif type_name == 'BitSet':
        return serialize_bitset(value, endian=endian)
    elif type_name == 'PVRequest':
        return serialize_pvrequest(value, instruct_to_cache=instruct_to_cache,
                                   endian=endian, cache=cache)
    elif type_name == 'PVField':
        return serialize_data(interface, values=value, endian=endian,
                              cache=cache)

    declaration = '{} {}'.format(type_name, field_name)
    fd = definition_line_to_info(declaration, nested_types=nested_types,
                                 user_types=cache.user_types, has_fields=False)
    return [serialize_data(fd, values=value, endian=endian, cache=cache)]


def deserialize_message_field(buf, type_name, field_name,
                              *, endian, cache,
                              interface=None, nested_types=None, bitset=None):
    if type_name == 'FieldDesc':
        return deserialize_introspection_data(buf, cache=cache, endian=endian)
    elif type_name == 'BitSet':
        return deserialize_bitset(buf, endian=endian)
    elif type_name == 'PVRequest':
        return deserialize_pvrequest(buf, endian=endian)
    elif type_name == 'PVField':
        return deserialize_data(interface, buf, endian=endian, cache=cache,
                                bitset=bitset)

    # TODO create these definitions globally for all non-fixed-length array
    #      types (i introduced a weird e.g. int[] in type names which
    #      probably should be rethought)
    declaration = '{} {}'.format(type_name, field_name)
    fd = definition_line_to_info(declaration, nested_types=nested_types,
                                 user_types=cache.user_types, has_fields=False)
    return deserialize_data(fd, buf, cache=cache, endian=endian, bitset=bitset)


# TODO: inconsistently semi-private serialization functions

# TOOD: speedup thoughts
#   - cache generated field desc metadata (for common types, etc)
#   - experiment with storing struct.pack() args for simple structure types,
#     then serialization is a matter of enumerating format strings and values

# TODO: bounded string untested; bounded_string array unsupported in C++
