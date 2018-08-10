from dtypes import *
import re


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


def assignment(inputs,token,mod):
    name = token.data
    if not re.match(r"[a-zA-Z_]\w*",name):
        raise ValueError("ERROR: Cannot assign to invalid variable name {}.".format(name))
    var = mod.getVariable(name)
    if var is None:
        var = mod.newVariable(name,type(inputs[0]))
    elif inputs[0].name != var.name:
        raise ValueError("ERROR: variable type {} does not match right side type {}.\n".format(var[1],inputs[0].name))
    mod.out += ["store {} {}, {}* {}".format(inputs[0].irname,inputs[0].addr,var.irname,var.addr)]
    return None

def arrayAssignment(inputs,token,mod):
    inputs = inputs[0]
    sub = inputs.subtype
    name = token.data
    mod.ensureDeclared("malloc","declare i8* @malloc(i32)")
    mod.ensureDeclared("free","declare void @free(i8*)")
    if not re.match(r"[a-zA-Z_]\w*",name):
        raise ValueError("ERROR: Cannot assign to invalid variable name {}.".format(name))
    left = mod.getVariable(name)
    if left is None:
        left = mod.newVariable(name,type(inputs))
    else:
        tempFree = mod.newRegister()
        tempFree2 = mod.newRegister()
        mod.out += ["{} = load {}*, {}** {}".format(tempFree, sub.irname, sub.irname, left.addr)]
        mod.out += ["{} = bitcast {}* {} to i8*".format(tempFree2, sub.irname,tempFree)]
        mod.out += ["call void @free(i8* {})".format(tempFree2)]
    temp1 = mod.newRegister()
    temp2 = mod.newRegister()
    mod.out += ["{} = call i8* @malloc(i32 {})".format(temp1, sub.size*len(inputs.addr))]
    mod.out += ["{} = bitcast i8* {} to {}*".format(temp2, temp1,sub.irname)]
    mod.out += ["store {}* {}, {}** {}".format(sub.irname,temp2,sub.irname,left.addr)]
    for i, val in enumerate(inputs.addr):
        addr = mod.newRegister()
        mod.out += ["{} = getelementptr {}, {}* {}, i32 {}".format(addr, sub.irname, sub.irname, temp2, i)]
        mod.out += ["store {} {}, {}* {}".format(sub.irname,val.addr,sub.irname,addr)]
    return None


def createArray(inputs, token, mod):
    # TODO: Better memory management to allow for proper anonymous arrays
    return Array(type(inputs[0]))(inputs)


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
