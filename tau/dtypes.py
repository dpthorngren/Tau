from ctypes import c_int, c_double, c_bool
baseTypes = ["Real", "Int", "Bool"]
__arraysDefined__ = {}


class Real(object):
    name = 'Real'
    irname = 'double'
    ctype = c_double
    size = 8
    initStr = '0.0'
    casting = ["Real"]
    conversions = {
        "Int": [True, "{} = fptosi double {} to i32"],
        "Bool": [True, "{} = fcmp one double {}, 0.0"]}

    def __init__(self, addr):
        self.addr = addr
        return


class Int(object):
    name = 'Int'
    irname = 'i32'
    ctype = c_int
    size = 4
    initStr = '0'
    casting = ["Int", "Real"]
    conversions = {
        "Real": [False, "{} = sitofp i32 {} to double"],
        "Bool": [False, "{} = icmp ne i32 {}, 0"]}

    def __init__(self, addr):
        self.addr = addr
        return


class Bool(object):
    name = 'Bool'
    irname = 'i1'
    ctype = c_bool
    size = 1
    initStr = 'false'
    casting = ["Bool", "Int", "Real"]
    conversions = {
        "Real": [False, "{} = uitofp i1 {} to double"],
        "Int": [False, "{} = zext i1 {} to i32"]}

    def __init__(self, addr):
        self.addr = addr
        return


def Array(newSubtype):
    if newSubtype in __arraysDefined__.keys():
        return __arraysDefined__[newSubtype]

    class Array(object):
        conversions = {}
        ctype = None
        size = 8
        initStr = 'null'
        subtype = newSubtype
        name = 'Array:'+subtype.name
        irname = subtype.irname+'*'
        casting = [name]
        allocID = None

        def __init__(self, addr):
            self.addr = addr
            return
    __arraysDefined__[newSubtype] = Array
    return Array


def getType(name):
    if name.startswith("Array:"):
        return Array(getType(name[6:]))
    return {"Int": Int, "Real": Real, "Bool": Bool}[name]
