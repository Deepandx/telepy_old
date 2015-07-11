__author__ = 'agrigoryev'
import os
import struct
import json
import io
from numbers import Number

class TlConstructor:
    def __init__(self, json_dict):
        self.id = int(json_dict['id'])
        self.type = json_dict['type']
        self.predicate = json_dict['predicate']
        self.params = []
        # case of vector
        for param in json_dict['params']:
            if param['type'] == "Vector<long>":
                param['type'] = "Vector t"
                param['subtype'] = "long"
            elif param['type'] == "vector<%Message>":
                param['type'] = "vector"
                param['subtype'] = "message"
            elif param['type'] == "vector<future_salt>":
                param['type'] = "vector"
                param['subtype'] = "future_salt"
            else:
                param['subtype'] = None
            self.params.append(param)

class TlMethod:
    def __init__(self, json_dict):
        self.id = int(json_dict['id'])
        self.type = json_dict['type']
        self.method = json_dict['method']
        self.params = json_dict['params']

class TL:
    def __init__(self, filename):
        with open(filename, 'r') as f:
           TL_dict = json.load(f)

        # Read constructors

        self.constructors = TL_dict['constructors']
        self.constructor_id = {}
        self.constructor_type = {}
        for elem in self.constructors:
            z = TlConstructor(elem)
            self.constructor_id[z.id] = z
            self.constructor_type[z.predicate] = z

        self.methods = TL_dict['methods']
        self.method_id = {}
        self.method_name = {}
        for elem in self.methods:
            z = TlMethod(elem)
            self.method_id[z.id] = z
            self.method_name[z.method] = z


## Loading TL_schema (should be placed in the same directory as mtproto000.py
tl = TL(os.path.join(os.path.dirname(__file__), "TL_schema.JSON"))


def serialize_obj(type_, **kwargs):
    bytes_io = io.BytesIO()
    try:
        tl_constructor = tl.constructor_type[type_]
    except KeyError:
        raise Exception("Could not extract type: %s" % type_)
    bytes_io.write(struct.pack('<i', tl_constructor.id))
    for arg in tl_constructor.params:
        serialize_param(bytes_io, type_=arg['type'], subtype=arg['subtype'], value=kwargs[arg['name']])
    return bytes_io.getvalue()

def serialize_method(type_, **kwargs):
    bytes_io = io.BytesIO()
    try:
        tl_method = tl.method_name[type_]
    except KeyError:
        raise Exception("Could not extract type: %s" % type_)
    bytes_io.write(struct.pack('<i', tl_method.id))
    for arg in tl_method.params:
        serialize_param(bytes_io, arg['type'], None, value=kwargs[arg['name']])
    return bytes_io.getvalue()


def serialize_param(bytes_io, type_, subtype, value):
    if type_ == "int":
        assert isinstance(value, Number)
        assert value.bit_length() <= 32
        bytes_io.write(struct.pack('<i', value))
    elif type_ == "long":
        assert isinstance(value, Number)
        bytes_io.write(struct.pack('<q', value))
    elif type_ in ["int128", "int256"]:
        assert isinstance(value, bytes)
        bytes_io.write(value)
    elif type_ == 'string' or 'bytes':
        l = len(value)
        if l < 254: # short string format
            bytes_io.write(struct.pack('<b', l))  # 1 byte of string
            bytes_io.write(value)   # string
            bytes_io.write(b'\x00'*((-l-1) % 4))  # padding bytes
        else:
            bytes_io.write(b'\xfe')  # byte 254
            bytes_io.write(struct.pack('<i', l)[:3])  # 3 bytes of string
            bytes_io.write(value) # string
            bytes_io.write(b'\x00'*(-l % 4))  # padding bytes
    elif type_ == 'vector':
        assert isinstance(value, list)
        bytes_io.write(struct.pack('<l', len(value)))
        for element in value:
            serialize_param(bytes_io, subtype, None, element)

def deserialize(bytes_io, type_=None, subtype=None):
    """
    :type bytes_io: io.BytesIO object
    """
    assert isinstance(bytes_io, io.BytesIO)

    # Built-in bare types
    if type_ == 'int':
        return struct.unpack('<i', bytes_io.read(4))[0]
    elif type_ == '#':
        return struct.unpack('<I', bytes_io.read(4))[0]
    elif type_ == 'long':
        return struct.unpack('<q', bytes_io.read(8))[0]
    elif type_ == 'double':
        return struct.unpack('<d', bytes_io.read(8))[0]
    elif type_ == 'int128':
        return bytes_io.read(16)
    elif type_ == 'int256':
        return bytes_io.read(32)
    elif type_ == 'string' or type_ == 'bytes':
        l = struct.unpack('<B', bytes_io.read(1))[0]
        assert l <= 254  # In general, 0xFF byte is not allowed here
        if l == 254:
            # We have a long string
            long_len = struct.unpack('<I', bytes_io.read(3)+b'\x00')[0]
            x = bytes_io.read(long_len)
            bytes_io.read(-long_len % 4)  # skip padding bytes
            return x
        else:
            # We have a short string
            x = bytes_io.read(l)
            bytes_io.read(-(l+1) % 4)  # skip padding bytes
            return x
    elif type_ == 'vector':
        assert subtype is not None
        count = struct.unpack('<l', bytes_io.read(4))[0]
        return [deserialize(bytes_io, type_=subtype) for i in range(count)]
    else:
        try:
            # Bare types
            tl_elem = tl.constructor_type[type_]
        except KeyError:
            # Boxed types
            i = struct.unpack('<i', bytes_io.read(4))[0]  # read type ID
            try:
                tl_elem = tl.constructor_id[i]
            except KeyError:
                # Unknown type
                raise Exception("Could not extract type: %s" % type_)

        base_boxed_types = ["Vector t", "Int", "Long", "Double", "String", "Int128", "Int256"]
        if tl_elem.type in base_boxed_types:
            return deserialize(bytes_io, type_=tl_elem.predicate, subtype=subtype)
        else:  # other types
            parameters = {}
            for arg in tl_elem.params:
                parameters[arg['name']] = deserialize(bytes_io, type_=arg['type'], subtype=arg['subtype'])
            return Object(name=tl_elem.predicate, type_=tl_elem.type, parameters=parameters)


class Object:
    def __init__(self, name, type_, parameters):
        self.name = name
        self.type = type_
        self.params = parameters

    def serialize(self):
        return serialize_obj(self.name, **self.params)

    def __getitem__(self, item):
        return self.params[item]

class Method:
    def __init__(self, predicate, return_type, parameters):
        self.predicate = predicate
        self.return_type = return_type
        self.params = parameters

    def serialize(self):
        return serialize_method(self.predicate, **self.params)

    def __getitem__(self, item):
        return self.params[item]