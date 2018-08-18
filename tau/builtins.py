from dtypes import *
import re


def freeMemory(inputs, token, mod):
    if (len(token.data) != 1) or (token.data[0].name != "name"):
        raise ValueError("Free must be given exactly one variable name.")
    allocID = mod.getAllocID(token.data[0].data,True)
    var = name(inputs,token.data[0],mod)
    freeThis = mod.newRegister()
    mod.out += ["{} = bitcast {} {} to i8*".format(freeThis, var.irname, var.addr)]
    mod.freeMemory(allocID,freeThis)
    return None


def callFunction(inputs, token, mod):
    funcName, dtype = token.data
    result = dtype(mod.newRegister())
    argTypes = ", ".join([i.irname for i in inputs])
    mod.ensureDeclared(funcName,'declare {} @{}({})'.format(result.irname,funcName,argTypes))
    arguments = ", ".join([i.irname+" "+i.addr for i in inputs])
    mod.out += ["{} = call {} @{}({})".format(result.addr, result.irname, funcName, arguments)]
    return result


def literal(inputs, token, mod):
    return token.data[0](str(token.data[1]))


def name(inputs, token, mod):
    var = mod.getVariable(token.data,True)
    result = type(var)(mod.newRegister())
    mod.out += ["{} = load {}, {}* {}".format(result.addr,result.irname,result.irname, var.addr)]
    return result


def parentheses(inputs, token, mod):
    return inputs[0]


def convert(inputs, token, mod):
    result = token.data(mod.newRegister())
    mod.out += [inputs[0].conversions[result.name][1].format(result.addr,inputs[0].addr)]
    return result


def indexingAssignment(inputs, token, mod):
    arr, index, right = inputs
    sub = arr.subtype
    elem = mod.newRegister()
    mod.out += ["{} = getelementptr {}, {}* {}, i32 {}".format(elem, sub.irname, sub.irname, arr.addr, index.addr)]
    mod.out += ["store {} {}, {}* {}".format(right.irname,right.addr,sub.irname,elem)]
    return


def assignment(inputs,token,mod):
    name = token.data
    if not re.match(r"[a-zA-Z_]\w*",name):
        raise ValueError("ERROR: Cannot assign to invalid variable name {}.".format(name))
    allocID = None
    if hasattr(inputs[0],"allocID") and inputs[0].allocID in mod.allocations.keys():
        mod.markMemory(inputs[0].allocID,"userManaged")
        allocID = inputs[0].allocID
    var = mod.getVariable(name)
    if var is None:
        var = mod.newVariable(name,type(inputs[0]),allocID)
    elif inputs[0].name != var.name:
        raise ValueError("ERROR: variable type {} does not match right side type {}.\n".format(var[1],inputs[0].name))
    mod.out += ["store {} {}, {}* {}".format(inputs[0].irname,inputs[0].addr,var.irname,var.addr)]
    if hasattr(inputs[0],"allocID") and inputs[0].allocID in mod.allocations.keys():
        mod.markMemory(inputs[0].allocID,"userManaged")
    return None


def literalArray(inputs, token, mod):
    sub = type(inputs[0])
    addr, allocID = mod.allocate(type(inputs[0]),len(inputs))
    for i, val in enumerate(inputs):
        temp = mod.newRegister()
        mod.out += ["{} = getelementptr {}, {}* {}, i32 {}".format(temp, sub.irname, sub.irname, addr, i)]
        mod.out += ["store {} {}, {}* {}".format(sub.irname,val.addr,sub.irname,temp)]
    result = Array(type(inputs[0]))(addr)
    result.allocID = allocID
    return result


def createArray(inputs, token, mod):
    dtype = Array(getType(token.data[0]))
    addr, allocID = mod.allocate(dtype.subtype,inputs[0].addr)
    result = dtype(addr)
    result.allocID = allocID
    return result


def indexArray(inputs, token, mod):
    result = inputs[0].subtype(mod.newRegister())
    elemPtr = mod.newRegister()
    mod.out += ["{} = getelementptr {}, {}* {}, i32 {}".format(elemPtr,result.irname, result.irname, inputs[0].addr, inputs[1].addr)]
    mod.out += ["{} = load {}, {}* {}".format(result.addr,result.irname, result.irname, elemPtr)]
    return result


def printStatement(inputs,token,mod):
    mod.ensureDeclared("printf",'declare i32 @printf(i8* nocapture readonly, ...)')
    if isinstance(inputs[0],Real):
        mod.ensureDeclared("printFloat",'@printFloat = external global [4 x i8]')
        mod.out += ["call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printFloat, i32 0, i32 0), double {})".format(inputs[0].addr)]
    elif isinstance(inputs[0],Int):
        mod.ensureDeclared("printInt",'@printInt = external global [4 x i8]')
        mod.out += ["call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printInt, i32 0, i32 0), i32 {})".format(inputs[0].addr)]
    elif isinstance(inputs[0],Bool):
        mod.ensureDeclared("printInt",'@printInt = external global [4 x i8]')
        mod.out += ["call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printInt, i32 0, i32 0), i1 {})".format(inputs[0].addr)]
    return None


def simpleBinary(inputs, token, mod):
    left, right = inputs
    result = type(left)(mod.newRegister())
    function = {'+':"add","*":"mul","%":"rem",'/':'div',"//":"div","-":"sub"}[token.name]
    if isinstance(left,Real):
        function = 'f'+function
    elif token.name in ['%','//'] and isinstance(left,Int):
        function = 's'+function
    mod.out += ["{} = {} {} {}, {}".format(result.addr,function,left.irname,left.addr,right.addr)]
    return result


def power(inputs, token, mod):
    result = Real(mod.newRegister())
    mod.ensureDeclared("llvm.pow.f64","declare double @llvm.pow.f64(double, double)")
    mod.out += ["{} = call double @llvm.pow.f64(double {}, double {})".format(result.addr, inputs[0].addr, inputs[1].addr)]
    return result


def unaryPlusMinus(inputs, token, mod):
    if token.name == "unary +":
        return inputs[0]
    result = type(inputs[0])(mod.newRegister())
    if isinstance(inputs[0],Real):
        function = 'fmul'
        right = "-1."
    else:
        function = 'mul'
        right = "-1"
    mod.out += ["{} = {} {} {}, {}".format(result.addr,function,inputs[0].irname,inputs[0].addr,right)]
    return result


def comparison(inputs,token,mod):
    left, right = inputs
    if isinstance(left,Real):
        function = 'fcmp '+{'<=':'ole','>=':'oge','<':'olt','>':'ogt','!=':'one','==':'oeq'}[token.name]
    elif isinstance(left,Int):
        function = 'icmp '+{'<=':'sle','>=':'sge','<':'slt','>':'sgt','!=':'ne','==':'eq'}[token.name]
    elif isinstance(left,Bool):
        function = 'icmp '+{'<=':'ule','>=':'uge','<':'ult','>':'ugt','!=':'ne','==':'eq'}[token.name]
    else:
        raise ValueError("ERROR: Cannot {} types {} and {}".format(token.name,left.name,right.name))
    result = Bool(mod.newRegister())
    mod.out += ["{} = {} {} {}, {}".format(result.addr,function,left.irname,left.addr,right.addr)]
    return result


def boolOperators(inputs, token, mod):
    left, right = inputs
    result = Bool(mod.newRegister())
    mod.out += ["{} = {} i1 {}, {}".format(result.addr,token.name,left.addr,right.addr)]
    return result
