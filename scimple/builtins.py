from ctypes import CFUNCTYPE, c_int, c_double, c_bool
import re

# Language definitions
conversions = {"RealInt":[True,"{} = fptosi double {} to i32"],
               "IntReal":[False,"{} = sitofp i32 {} to double"],
               "RealBool":[True,"{} = fcmp one double {}, 0.0"],
               "IntBool":[False,"{} = icmp ne i32 {}, 0"],
               "BoolReal":[False,"{} = uitofp i1 {} to double"],
               "BoolInt":[False,"{} = zext i1 {} to i32"]}
ctypemap = {"Real":c_double,'Int':c_int,'Bool':c_bool,"None":None}
# types = {'Real':'double','Int':'i32','Bool':'i1',"None":'void'}
# TODO better type manager
types = {'Real':'double','Int':'i32','Bool':'i1',"None":'void'}
bitsizes = {'Real':64,'Int':32,'Bool':8}
globalInit = {'Real':'1.0','Int':'1','Bool':'false'}
castingRules = {
    "Real":["Real"],
    "Int":["Int","Real"],
    "Bool":["Bool","Int","Real"],
    "array:Int":["array:Int"]
}


def callFunction(inputs, token, mod):
    addr = mod.newRegister()
    funcName, dtype = token.data
    argTypes = ", ".join([types[i[1]] for i in inputs])
    mod.ensureDeclared(funcName,'declare {} @{}({})'.format(types[dtype],funcName,argTypes))
    arguments = ", ".join([types[i[1]]+" "+str(i[0]) for i in inputs])
    mod.out += ["{} = call {} @{}({})".format(addr, types[dtype],funcName,arguments)]
    return addr, dtype


def literal(inputs, token, mod):
    return token.data[1], token.data[0]


def name(inputs, token, mod):
    addr = mod.newRegister()
    var = mod.getVariable(token.data)
    mod.out += ["{} = load {}, {}* {}".format(addr,types[var[1]], types[var[1]], var[0])]
    return addr, var[1]


def parentheses(inputs, token, mod):
    return inputs[0][0], inputs[0][1]


def convert(inputs, token, mod):
    addr = mod.newRegister()
    mod.out += [conversions[inputs[0][1]+token.data][1].format(addr,inputs[0][0])]
    return addr, token.data


def assignment(inputs,token,mod):
    name = token.data
    if not re.match(r"[a-zA-Z_]\w*",name):
        raise ValueError("ERROR: Cannot assign to invalid variable name {}.".format(name))
    left = mod.getVariable(name)
    if left is None:
        left = mod.newVariable(name,inputs[0][1])
    elif types[inputs[0][1]] != types[left[1]]:
        raise ValueError("ERROR: variable type {} does not match right side type {}.\n".format(left[1],inputs[0][1]))
    mod.out += left[2] + ["store {} {}, {}* {}".format(types[inputs[0][1]],inputs[0][0],types[left[1]],left[0])]
    return "", "None"

def arrayAssignment(inputs,token,mod):
    inputs = inputs[0][0]
    dtype = inputs[0][1]
    ctype = types[dtype]
    mod.ensureDeclared("malloc","declare i8* @malloc(i32)")
    mod.ensureDeclared("free","declare void @free(i8*)")
    name = token.data
    if not re.match(r"[a-zA-Z_]\w*",name):
        raise ValueError("ERROR: Cannot assign to invalid variable name {}.".format(name))
    left = mod.getVariable(name)
    if left is None:
        left = mod.newVariable(name,"array:"+inputs[0][1])
    else:
        tempFree = mod.newRegister()
        tempFree2 = mod.newRegister()
        mod.out += ["{} = load {}*, {}** {}".format(tempFree, ctype, ctype, left[0])]
        mod.out += ["{} = bitcast {}* {} to i8*".format(tempFree2, types[dtype],tempFree)]
        mod.out += ["call void @free(i8* {})".format(tempFree2)]
    temp1 = mod.newRegister()
    temp2 = mod.newRegister()
    mod.out += ["{} = call i8* @malloc(i32 {})".format(temp1, bitsizes[dtype]*len(inputs))]
    mod.out += ["{} = bitcast i8* {} to {}*".format(temp2, temp1,types[dtype])]
    mod.out += ["store {}* {}, {}** {}".format(types[dtype],temp2,types[dtype],left[0])]
    for i, val in enumerate(inputs):
        addr = mod.newRegister()
        mod.out += ["{} = getelementptr {}, {}* {}, i32 {}".format(addr, ctype, ctype, temp2, i)]
        mod.out += ["store {} {}, {}* {}".format(ctype,val[0],ctype,addr)]
    return "", "None"


def createArray(inputs, token, mod):
    dtype = inputs[0][1]
    return inputs, "array:"+dtype


def indexArray(inputs, token, mod):
    varAddr, varType, _ = mod.getVariable(token.data[0])
    if varType[6:] != inputs[0][1]:
        raise ValueError("INTERNAL ERROR: Expected array subtype {} and subtype found in memory {} don't match.".format(inputs[0][1],varType[6:]))
    ctype = types[inputs[0][1]]
    arrPtr = mod.newRegister()
    mod.out += ["{} = load {}*, {}** {}".format(arrPtr,ctype, ctype, varAddr)]
    subPtr = mod.newRegister()
    mod.out += ["{} = getelementptr {}, {}* {}, i32 {}".format(subPtr,ctype, ctype, arrPtr, inputs[0][0])]
    addr = mod.newRegister()
    mod.out += ["{} = load {}, {}* {}".format(addr,ctype, ctype, subPtr)]
    return addr, inputs[0][1]


def printStatement(inputs,token,mod):
    right = inputs[0]
    mod.ensureDeclared("printf",'declare i32 @printf(i8* nocapture readonly, ...)')
    if right[1] == "Real":
        mod.ensureDeclared("printFloat",'@printFloat = external global [4 x i8]')
        mod.out = ["call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printFloat, i32 0, i32 0), double {})".format(right[0])]
    elif right[1] == "Int":
        mod.ensureDeclared("printInt",'@printInt = external global [4 x i8]')
        mod.out = ["call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printInt, i32 0, i32 0), i32 {})".format(right[0])]
    elif right[1] == "Bool":
        mod.ensureDeclared("printInt",'@printInt = external global [4 x i8]')
        mod.out = ["call i32 (i8*, ...) @printf(i8* getelementptr inbounds ([4 x i8], [4 x i8]* @printInt, i32 0, i32 0), i1 {})".format(right[0])]
    return "", "None"


def simpleBinary(inputs, token, mod):
    addr = mod.newRegister()
    left, right = inputs
    if left[1] != right[1] or any([i not in types.keys() for i in [left[1], right[1]]]):
        raise ValueError("ERROR: Cannot {} types {} and {}".format(token.name,left[1],right[1]))
    dtype = left[1]
    function = {'+':"add","*":"mul","%":"rem",'/':'div',"//":"div","-":"sub"}[token.name]
    if dtype == "Real":
        function = 'f'+function
    if token.name in ['%','//'] and dtype is "Int":
        function = 's'+function
    mod.out += ["{} = {} {} {}, {}".format(addr,function,types[dtype],left[0],right[0])]
    return addr, dtype


def power(inputs, token, mod):
    addr = mod.newRegister()
    mod.ensureDeclared("llvm.pow.f64","declare double @llvm.pow.f64(double, double)")
    mod.out += ["{} = call double @llvm.pow.f64(double {}, double {})".format(addr, inputs[0][0], inputs[1][0])]
    return addr, "Real"


def comparison(inputs,token,mod):
    left, right = inputs
    addr = mod.newRegister()
    if left[1] != right[1] or any([i not in types.keys() for i in [left[1], right[1]]]):
        raise ValueError("ERROR: Cannot {} types {} and {}".format(op,left[1],right[1]))
    if left[1] == "Real":
        function = 'fcmp '+{'<=':'ole','>=':'oge','<':'olt','>':'ogt','!=':'one','==':'oeq'}[token.name]
    elif left[1] == "Int":
        function = 'icmp '+{'<=':'sle','>=':'sge','<':'slt','>':'sgt','!=':'ne','==':'eq'}[token.name]
    elif left[1] == "Bool":
        function = 'icmp '+{'<=':'ule','>=':'uge','<':'ult','>':'ugt','!=':'ne','==':'eq'}[token.name]
    mod.out += ["{} = {} {} {}, {}".format(addr,function,types[left[1]],left[0],right[0])]
    return addr, "Bool"


def boolOperators(inputs, token, mod):
    left, right = inputs
    addr = mod.newRegister()
    mod.out += ["{} = {} i1 {}, {}".format(addr,token.name,left[0],right[0])]
    return addr, "Bool"
